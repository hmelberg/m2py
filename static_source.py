"""
static_source.py — serve `import` from the static dataset instead of generating.

When the app's "data source" switch is set to *static*, the m2py import handler
calls StaticDataSource.generate() instead of MockDataEngine.generate(). It returns
the SAME shape the engine returns ([key_col, (ref_col,) var]), so all downstream
merge / rename / label / status logic is unchanged.

Architecture (browser): DuckDB-WASM (JS) runs the routed SQL against the hosted
Parquet via HTTP range requests; results are injected here as a cache before the
(synchronous) interpreter run. This module owns the routing and the cache lookup;
it never blocks. Anything not materialised in the static files (a variable/date
we didn't export) returns None → the caller falls back to generation.

Flow:
    1. plan(import_specs, limit)  -> [query descriptors]   (Python, pre-run)
    2. <JS runs each descriptor in DuckDB-WASM, fills cache>
    3. set_cache(cache)
    4. generate(cmd, args, df)    -> DataFrame | None       (during the run)

Locally (CLI / tests) the same descriptors run through duckdb (Python) — identical
SQL — so the routing is fully testable without a browser.
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

# All static tables (for the app to fetch schemas once at init).
STATIC_TABLES = ["person", "person_year", "jobb", "kjoretoy", "kurs", "npr",
                 "malepunkt", "trafikkulykke", "person_i_trafikkulykke"]

_IMPORT_LINE_RE = re.compile(
    r'^\s*(import(?:-event|-panel)?)\s+(\S+)(?:\s+(\d{4}-\d{2}-\d{2}))?', re.IGNORECASE)


def extract_import_specs(script_text: str) -> list:
    """Pull {cmd, var, date1} from a script's import lines (for pre-fetch).
    import-panel lines are captured but served via fallback, so only var/date1
    of the first token matter here."""
    specs = []
    for line in (script_text or "").splitlines():
        m = _IMPORT_LINE_RE.match(line)
        if m:
            specs.append({"cmd": m.group(1).lower(), "var": m.group(2), "date1": m.group(3)})
    return specs


# enhetstype -> static table name
ENHETSTYPE_TABLE = {
    "Person": "person",
    "Jobb": "jobb",
    "Kjøretøy": "kjoretoy",
    "Kurs": "kurs",
    "Behandlingsopphold": "npr",
    "Målepunkt": "malepunkt",
    "Trafikkulykke": "trafikkulykke",
    "Person i trafikkulykke": "person_i_trafikkulykke",
}

# table -> (id_col, ref_col|None). id_col is what the engine returns as the key
# (the handler renames unit_id->PERSONID_1 itself, so person stays 'unit_id').
TABLE_KEYS = {
    "person": ("unit_id", None),
    "person_year": ("unit_id", None),
    "jobb": ("ARBEIDSFORHOLD_ID", "ARBEIDSFORHOLD_PERSON"),
    "kjoretoy": ("KJORETOY_ID", "KJORETOY_KJORETOYID_FNR"),
    "kurs": ("NUDB_KURS_LOEPENR", "NUDB_KURS_FNR"),
    "npr": ("AGGRSHOPPID", "unit_id"),
    "malepunkt": ("MALEPUNKT_ID", "ELHUB_PERS_MALEPUNKTID_FNR"),
    "trafikkulykke": ("TRAFULYK_ID", None),
    "person_i_trafikkulykke": ("TRAFULYK_PERS_ID", "TRAFULYK_PERS_FNR"),
}

_GRID_TEMPORALITET = {"akkumulert", "tverrsnitt"}


class StaticDataSource:
    """Routes imports to the static Parquet tables and serves cached results."""

    def __init__(self, catalog: dict, table_columns: dict):
        """
        catalog:        variable metadata (short_name -> meta dict).
        table_columns:  {table_name: set(column_names)} actually present in the
                        static files — used to decide static vs. fallback.
        """
        self.catalog = catalog or {}
        self.table_columns = {t: set(cols) for t, cols in (table_columns or {}).items()}
        self.cache: dict = {}

    # -- metadata helpers ---------------------------------------------------
    def _meta(self, short: str) -> dict:
        return (self.catalog.get(short)
                or next((v for k, v in self.catalog.items() if k.split("/")[-1] == short), {}))

    def _entity_table(self, meta: dict) -> str:
        ent = meta.get("enhetstype")
        return ENHETSTYPE_TABLE.get(ent, "person")

    def _has(self, table: str, col: str) -> bool:
        cols = self.table_columns.get(table)
        return col in cols if cols is not None else True  # unknown schema -> optimistic

    # -- routing ------------------------------------------------------------
    def route(self, short: str, date1: Optional[str]) -> Optional[dict]:
        """Return a query descriptor {key, table, select, where, limit-able}, or
        None when the variable/date isn't materialised (caller falls back)."""
        meta = self._meta(short)
        table = self._entity_table(meta)
        temporalitet = str(meta.get("temporalitet", "")).lower()

        if table == "person":
            if temporalitet in _GRID_TEMPORALITET and date1:
                year = int(str(date1)[:4])
                if self._has("person_year", short):
                    return {"key": f"person_year|{short}|{year}", "table": "person_year",
                            "select": ["unit_id", short], "where": f"year={year}",
                            "kind": "person"}
                return None  # time-varying var not in panel -> fallback to generate
            if not self._has("person", short):
                return None
            return {"key": f"person|{short}", "table": "person",
                    "select": ["unit_id", short], "where": None, "kind": "person"}

        # entity tables: return id + person-ref (implicit key) + the variable
        id_col, ref_col = TABLE_KEYS.get(table, ("unit_id", None))
        if not self._has(table, short):
            return None
        select = [id_col]
        if ref_col and ref_col != id_col:
            select.append(ref_col)
        select.append(short)
        return {"key": f"{table}|{short}", "table": table, "select": select,
                "where": None, "kind": "entity", "ref_col": ref_col}

    def plan(self, import_specs: list, limit: Optional[int] = None) -> list:
        """import_specs: [{var, date1}]. Returns de-duplicated query descriptors
        (with the population `limit` applied to person/entity row scans)."""
        seen, out = set(), []
        for spec in import_specs:
            short = (spec.get("var", "") or "").split("/")[-1]
            if not short:
                continue
            d = self.route(short, spec.get("date1"))
            if d is None or d["key"] in seen:
                continue
            seen.add(d["key"])
            if limit:
                if d.get("kind") == "person":
                    # Bound by id, not LIMIT: parquet row order is unguaranteed,
                    # so LIMIT n could pick a person set inconsistent with the
                    # entity tables (which filter ref_col <= n). WHERE id <= n
                    # makes the person universe exactly {1..n} by construction.
                    id_col = TABLE_KEYS.get(d["table"], ("unit_id", None))[0]
                    extra = f"{id_col} <= {int(limit)}"
                    d = dict(d, where=(f"{d['where']} AND {extra}" if d.get("where") else extra))
                elif d.get("kind") == "entity" and d.get("ref_col"):
                    # keep entity rows consistent with the limited person universe
                    extra = f"{d['ref_col']} <= {int(limit)}"
                    d = dict(d, where=(f"{d['where']} AND {extra}" if d.get("where") else extra))
            out.append(d)
        return out

    def plan_sql(self, script_text: str, base_url: str, limit: Optional[int] = None) -> list:
        """Pre-fetch plan as [{key, sql}] — full DuckDB SQL against the hosted
        Parquet. The app (JS) runs each in DuckDB-WASM and returns the columns
        keyed by `key`; the routing/SQL stays here in Python."""
        base = base_url if base_url.endswith("/") else base_url + "/"
        out = []
        for d in self.plan(extract_import_specs(script_text), limit):
            sel = ", ".join('"%s"' % c for c in d["select"])
            url = f"{base}static_data/{d['table']}.parquet"
            sql = f"SELECT {sel} FROM read_parquet('{url}')"
            if d.get("where"):
                sql += " WHERE " + d["where"]
            if d.get("limit"):
                sql += f" LIMIT {int(d['limit'])}"
            out.append({"key": d["key"], "sql": sql})
        return out

    # -- cache + serve ------------------------------------------------------
    def set_cache(self, cache: dict) -> None:
        """cache: {key: {column: [values]}} produced by DuckDB-WASM (or duckdb)."""
        self.cache = cache or {}

    def generate(self, cmd: str, args: dict, current_df) -> Optional[pd.DataFrame]:
        """Return a generate-shaped DataFrame for this import, or None to fall back."""
        if cmd == "import-panel":
            return None  # panels fall back to the engine for now
        short = (args.get("var", "") or "").split("/")[-1]
        if not short:
            return None
        d = self.route(short, args.get("date1"))
        if d is None:
            return None
        cols = self.cache.get(d["key"])
        if cols is None:
            return None
        df = pd.DataFrame({c: list(v) for c, v in (cols.items() if hasattr(cols, "items") else cols)})
        if df.empty:
            return None
        # Apply `as alias` to the variable column, exactly as the engine does.
        alias = args.get("alias") or short
        if alias != short and short in df.columns:
            df = df.rename(columns={short: alias})
        return df
