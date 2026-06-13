#!/usr/bin/env python
"""
build_static_data.py — CLI that materialises the m2py engine into static files.

Builds the full relational set (person, person_year, jobb, kjoretoy, kurs, npr)
and writes:

    static_data/<table>.parquet     typed columnar (primary)
    static_data/microdata.duckdb    one database bundling all tables (foreign keys)
    static_data/person.csv          CSV copies of small/core tables (eyeballing)
    static_data/kommune.csv         (only if such tables exist)
    static_data/manifest.json       provenance: counts, years, params

Usage (Anaconda Python on this machine):
    "C:/ProgramData/anaconda3/python.exe" build_static_data.py
    "C:/ProgramData/anaconda3/python.exe" build_static_data.py --persons 100000 --from 2010 --to 2023

Run from the repo root (needs variable_metadata.json + the m2py/mockdata modules).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import mockdata_export as mx

# Tables small enough to also emit as CSV (person is far too wide for CSV).
_CSV_TABLES = {"trafikkulykke", "person_i_trafikkulykke", "kommune",
               "variables", "value_labels", "valid_dates", "fylke",
               "icd10_kapittel", "kommune_crosswalk"}


def main() -> None:
    ap = argparse.ArgumentParser(description="Build static microdata files from the m2py engine.")
    ap.add_argument("--persons", type=int, default=100_000, help="size of the person universe")
    ap.add_argument("--from", dest="year_from", type=int, default=2015, help="first year (inclusive)")
    ap.add_argument("--to", dest="year_to", type=int, default=2023, help="last year (inclusive)")
    ap.add_argument("--out", type=Path, default=Path("static_data"), help="output directory")
    ap.add_argument("--metadata", type=Path, default=Path("variable_metadata.json"))
    ap.add_argument("--no-duckdb", action="store_true", help="skip the DuckDB bundle")
    ap.add_argument("--no-entities", action="store_true", help="person + person_year only")
    ap.add_argument("--person-scope", choices=["core", "all"], default="core",
                    help="'core' = curated person columns; 'all' = full ~438 Person variables (wide, slower)")
    ap.add_argument("--no-latent-structure", action="store_true",
                    help="disable the multi-factor copula that cross-correlates person quantities")
    ap.add_argument("--dynamic-panel", action="store_true",
                    help="person_year via life-state microsimulation (income dynamics + uføre/retirement/death events)")
    ap.add_argument("--no-normalize", action="store_true",
                    help="skip microdata-faithful dtype normalisation (codes as strings, numbers downcast)")
    ap.add_argument("--dead-fraction", type=float, default=0.0,
                    help="share of the person register that is deceased (DOEDS_DATO set, no panel rows); e.g. 0.4. Needs --dynamic-panel")
    args = ap.parse_args()

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    # Clean stale generated artifacts first. Writes are otherwise additive, so a
    # smaller rebuild (e.g. --no-entities, or fewer persons) would leave parquet
    # tables from a previous, larger person universe on disk — served with
    # dangling unit_ids that don't exist in the new person table.
    for _pattern in ("*.parquet", "*.csv", "*.duckdb"):
        for _f in out.glob(_pattern):
            try:
                _f.unlink()
            except OSError:
                pass
    years = list(range(args.year_from, args.year_to + 1))

    catalog = json.loads(args.metadata.read_text(encoding="utf-8"))["variables"]
    engine = mx.make_engine(args.persons, catalog)

    skips: list[str] = []
    t_start = time.time()

    def on_skip(name, reason):
        skips.append(f"{name}: {reason}")

    def on_progress(table):
        print(f"  [{time.time() - t_start:6.1f}s] building {table} ...", flush=True)

    print(f"Building {args.persons:,} persons, years {years[0]}-{years[-1]} -> {out}/")
    tables = mx.build_all(
        engine,
        years=years,
        wide_person=(args.person_scope == "all"),
        latent_structure=not args.no_latent_structure,
        dynamic_person_year=args.dynamic_panel,
        dead_fraction=args.dead_fraction,
        entities=[] if args.no_entities else mx.MULTI_RECORD_ENTITIES,
        include_npr=not args.no_entities,
        include_trafikkulykke=not args.no_entities,
        on_skip=on_skip,
        on_progress=on_progress,
    )

    # microdata-faithful dtypes: codes as strings, numbers downcast.
    if not args.no_normalize:
        print("Normalising dtypes (codes as strings, numbers downcast) ...", flush=True)
        tables = mx.normalize_for_microdata(tables, engine)

    # Parquet (primary, zstd) + CSV for core tables.
    print("Writing Parquet ...", flush=True)
    for name, df in tables.items():
        df.to_parquet(out / f"{name}.parquet", index=False, compression="zstd")
        if name in _CSV_TABLES:
            df.to_csv(out / f"{name}.csv", index=False)

    # DuckDB bundle.
    if not args.no_duckdb:
        print("Bundling DuckDB ...", flush=True)
        _write_duckdb(out, tables)

    manifest = {
        "n_persons": args.persons,
        "years": years,
        "tables": {name: {"rows": len(df), "cols": len(df.columns)} for name, df in tables.items()},
        "metadata_file": str(args.metadata),
        "skips": sorted(set(skips)),
        # Full provenance: every CLI argument that produced this build, so a
        # served bundle can be reproduced and its scope is unambiguous.
        "build_args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    elapsed = time.time() - t_start
    print(f"\nDone in {elapsed:.1f}s. Tables:")
    for name, df in tables.items():
        print(f"  {name:12s} {len(df):>9,} rows x {len(df.columns):>3} cols")
    if skips:
        print(f"  ({len(set(skips))} skipped variables — see manifest.json)")


def _write_duckdb(out: Path, tables: dict) -> None:
    """Build the DuckDB bundle by reading the already-written Parquet files.

    Reading Parquet (which carries an explicit typed schema) avoids DuckDB's
    pandas type inference, which mis-narrows mixed/object columns to INT32 and
    then overflows ("Value out of range for type INT").
    """
    import duckdb

    db_path = out / "microdata.duckdb"
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    try:
        for name in tables:
            pq = (out / f"{name}.parquet").as_posix()
            con.execute(f'CREATE TABLE "{name}" AS SELECT * FROM read_parquet(\'{pq}\')')
    finally:
        con.close()


if __name__ == "__main__":
    main()
