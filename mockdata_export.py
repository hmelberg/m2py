"""
mockdata_export.py — materialise the m2py generation engine into static tables.

This module is *additive*: it does not change how the app generates data on the
fly. It simply drives the existing `MockDataEngine` (m2py.py) the same way the
app's `import` command does, and collects the results into wide, reusable
DataFrames that can be written to Parquet / DuckDB / CSV.

Design (see docs/PLAN_static_data_export.md):

    person       — one row per person (constant `temporalitet=Fast` variables)
    person_year  — person × year (time-varying variables; age-at-year drives
                   realistic temporal variation through the realism framework)

Both tables are keyed on `unit_id`, the engine's stable person universe
(1..n_persons). Because every variable is generated deterministically per
unit_id (shared latent_z + per-purpose seeds), values stay internally
consistent across variables and across years.

Entry points:
    make_engine(n_persons, catalog)              -> MockDataEngine
    build_person(engine, var_names)              -> DataFrame
    build_person_year(engine, person_df, vars, years) -> DataFrame
    build_core(engine, years)                    -> dict[str, DataFrame]
    person_variable_split(engine)                -> (constant[], timevarying[])

Pyodide note: pure stdlib + numpy + pandas at import time. Parquet writing
(`df_to_parquet_bytes`) needs pyarrow, imported lazily only when called.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from m2py import (
    MockDataEngine,
    _ENHETSTYPE_TO_ENTITY,
    _ENTITY_ID_COL,
    _ENTITY_PERSON_REF_COL,
    _ENTITY_MULTI_RECORD_PROFILE,
    _NPR_ENTITY,
    _norway_classify_money_demo,
)


# ---------------------------------------------------------------------------
# Curated default variable sets (small + verifiable). The full catalog can be
# selected instead via person_variable_split(engine).
# ---------------------------------------------------------------------------

# Drivers materialised first so that age/gender/education feed downstream
# variables (and so person_year can recompute age-at-year from birth date).
DRIVER_VARS = ["BEFOLKNING_FOEDSELS_AAR_MND", "BEFOLKNING_KJOENN", "NUDB_BU"]

# Constant (Fast) person attributes -> `person` table.
CORE_CONSTANT = ["BEFOLKNING_FOEDSELS_AAR_MND", "BEFOLKNING_KJOENN", "NUDB_BU"]

# Time-varying attributes -> `person_year`. These carry realism specs whose
# age driver is recomputed from birth date at each as_of year, so values evolve
# as the person ages (income age-curve, wealth accumulation, 2020 municipality
# reform via by_date, ...).
CORE_TIMEVARYING = [
    "INNTEKT_WLONN",      # wage income (lognormal, age peak, gender gap, latent_z)
    "INNTEKT_WSAMINNT",   # total income
    "SKATT_NETTOFORMUE",  # net wealth
    "BOSATT_KOMMUNE",     # municipality of residence (by_date regimes)
]

# Years to materialise in person_year by default.
DEFAULT_YEARS = list(range(2015, 2024))

# Key column the engine uses for the person universe.
_UNIT_ID = "unit_id"


# ---------------------------------------------------------------------------
# Engine construction
# ---------------------------------------------------------------------------

def make_engine(n_persons: int, catalog: dict) -> MockDataEngine:
    """Build a MockDataEngine over a `n_persons` universe.

    `catalog` is the `variables` dict from variable_metadata.json (the same
    object the app passes in the browser).
    """
    return MockDataEngine(default_rows=int(n_persons), catalog=catalog)


# ---------------------------------------------------------------------------
# Catalog-driven variable selection
# ---------------------------------------------------------------------------

def _entity_of(meta: dict) -> str:
    if not isinstance(meta, dict):
        return "person"
    ent = meta.get("entity_type")
    if ent:
        return ent
    return _ENHETSTYPE_TO_ENTITY.get(meta.get("enhetstype"), "person")


def person_variable_split(engine: MockDataEngine) -> tuple[list[str], list[str]]:
    """Split Person variables into (constant, time-varying) by `temporalitet`.

        Fast                    -> constant   (person table)
        Akkumulert / Tverrsnitt -> time-varying (person_year table)
        Forløp                  -> skipped in v1 (spell/event data)

    Returns short variable names (no `db/` prefix), sorted and de-duplicated.
    """
    constant: set[str] = set()
    timevarying: set[str] = set()
    for name, meta in engine.catalog.items():
        if not isinstance(meta, dict):
            continue
        if _entity_of(meta) != "person":
            continue
        short = name.split("/")[-1]
        temporalitet = meta.get("temporalitet")
        if temporalitet == "Fast":
            constant.add(short)
        elif temporalitet in ("Akkumulert", "Tverrsnitt"):
            timevarying.add(short)
        # "Forløp" deliberately skipped for v1.
    return sorted(constant), sorted(timevarying)


# ---------------------------------------------------------------------------
# Single-variable import (mirrors the app's `import db/VAR [as alias]`)
# ---------------------------------------------------------------------------

def _result_key_col(res: pd.DataFrame) -> str:
    for c in (_UNIT_ID, "PERSONID_1"):
        if c in res.columns:
            return c
    return res.columns[0]


def import_variable(
    engine: MockDataEngine,
    current_df: pd.DataFrame,
    short_name: str,
    as_of: Optional[str] = None,
) -> Optional[pd.Series]:
    """Generate one variable for the rows in `current_df`.

    Returns a Series aligned to `current_df['unit_id']` (named `short_name`),
    or None if generation failed or produced no usable column.

    `as_of` (e.g. '2020-01-01') is passed through as the realism `date1` so
    that trend / by_date / age-at-year effects activate.
    """
    args = {"var": short_name}
    if as_of is not None:
        args["date1"] = as_of
    try:
        res = engine.generate("import", args, current_df)
    except Exception:
        return None
    if res is None or short_name not in res.columns:
        return None

    key = _result_key_col(res)
    out = res[[key, short_name]].copy()
    if key != _UNIT_ID:
        out = out.rename(columns={key: _UNIT_ID})
    # Align to current_df order via merge, then return just the value column.
    merged = current_df[[_UNIT_ID]].merge(out, on=_UNIT_ID, how="left")
    return merged[short_name]


# ---------------------------------------------------------------------------
# person table (constant attributes)
# ---------------------------------------------------------------------------

def build_person(
    engine: MockDataEngine,
    var_names: Iterable[str] = CORE_CONSTANT,
    drivers: Iterable[str] = DRIVER_VARS,
    on_skip=None,
) -> pd.DataFrame:
    """Build the person dimension: one row per person, constant attributes.

    Variables are imported in dependency order (drivers first) into an
    accumulating DataFrame keyed on `unit_id`, exactly as the app builds a
    dataset import-by-import. Failing variables are skipped (reported via
    `on_skip(name, reason)` if provided).
    """
    wanted = list(dict.fromkeys(var_names))
    ordered = [v for v in drivers if v in wanted] + [v for v in wanted if v not in drivers]

    cur = pd.DataFrame({_UNIT_ID: engine.person_universe})
    for v in ordered:
        col = import_variable(engine, cur, v)
        if col is None:
            if on_skip:
                on_skip(v, "no column produced")
            continue
        cur[v] = col.values
    return cur


def build_person_wide(
    engine: MockDataEngine,
    as_of: Optional[str] = None,
    latent_structure: bool = True,
    on_skip=None,
    on_report=None,
) -> pd.DataFrame:
    """Build a WIDE person snapshot: all Person-enhetstype variables (Fast +
    Akkumulert + Tverrsnitt; Forløp/spell data excluded) at a single reference
    date `as_of`.

    For speed each variable is generated against a slim driver-only context
    (unit_id + birth date + gender + education) rather than the full accumulating
    frame — the realism layer only needs the drivers, and this keeps every
    generate() call cheap. Columns are collected and assembled once. Variables
    that fail (e.g. rule_based needing absent dependencies, unresolved external
    metadata) are skipped and reported via `on_skip`.
    """
    if as_of is None:
        as_of = f"{max(DEFAULT_YEARS)}-01-01"
    const, tv = person_variable_split(engine)
    names = list(dict.fromkeys(list(const) + list(tv)))

    ctx = pd.DataFrame({_UNIT_ID: engine.person_universe})
    cols: dict = {_UNIT_ID: engine.person_universe}

    # Build drivers first, into both the context (so realism can read them) and
    # the output. Drivers use as_of=None — the same convention build_person()
    # and the entity/panel builders use — so birth date (which is as_of-
    # sensitive: birth_year = ref_year - age) stays identical across tables and
    # ages remain consistent everywhere.
    for d in DRIVER_VARS:
        s = import_variable(engine, ctx, d, as_of=None)
        if s is not None:
            ctx[d] = s.values
            cols[d] = s.values

    for v in names:
        if v in cols:
            continue
        s = import_variable(engine, ctx, v, as_of=as_of)
        if s is None:
            if on_skip:
                on_skip(v, "no column")
            continue
        cols[v] = s.values

    df = pd.DataFrame(cols)
    if latent_structure:
        _ry = int(str(as_of)[:4]) if as_of else None
        df = apply_latent_structure(df, engine, on_report=on_report, ref_year=_ry)
    return df


# ---------------------------------------------------------------------------
# person_year table (time-varying attributes)
# ---------------------------------------------------------------------------

def build_person_year(
    engine: MockDataEngine,
    person_df: pd.DataFrame,
    var_names: Iterable[str] = CORE_TIMEVARYING,
    years: Iterable[int] = DEFAULT_YEARS,
    driver_cols: Iterable[str] = DRIVER_VARS,
    on_skip=None,
) -> pd.DataFrame:
    """Build the person × year fact table.

    For each year, the driver columns (birth date, gender, education) from
    `person_df` are passed as context with `as_of = '{year}-01-01'`. The
    realism framework recomputes age-at-year from the birth date, so
    age-dependent variables (income peak, wealth) evolve as the person ages,
    and by_date/trend regimes switch on the right year.

    Returns a long DataFrame with columns [unit_id, year, <var_names...>].
    """
    wanted = list(dict.fromkeys(var_names))
    base_cols = [_UNIT_ID] + [c for c in driver_cols if c in person_df.columns]
    base = person_df[base_cols].copy()

    frames: list[pd.DataFrame] = []
    for year in years:
        as_of = f"{int(year)}-01-01"
        cur = base.copy()
        produced: list[str] = []
        for v in wanted:
            col = import_variable(engine, cur, v, as_of=as_of)
            if col is None:
                if on_skip:
                    on_skip(v, f"year {year}: no column")
                continue
            cur[v] = col.values
            produced.append(v)
        cur["year"] = int(year)
        frames.append(cur[[_UNIT_ID, "year"] + produced])

    if not frames:
        return pd.DataFrame(columns=[_UNIT_ID, "year"])
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Dynamic person_year — life-state microsimulation
#
# Each person walks a yearly state machine; income and benefits follow from the
# state, with persistent + AR(1) transitory wage dynamics. The engine's per-year
# wage (age curve + latent_z + gender) is reused as the person's POTENTIAL wage;
# the state machine gates it and layers transitory shocks, so the existing
# cross-sectional realism is preserved while real longitudinal behaviour appears
# (income autocorrelation, disability dropping wage and switching on uføretrygd,
# retirement, unemployment spells, mortality).
#
# States: utdanning -> sysselsatt <-> arbeidsledig -> ufor -> pensjonist -> dod
# (ufor/pensjonist/dod are absorbing forward). Hazards depend on age, the
# socioeconomic factor (latent_z) and a health factor.
# ---------------------------------------------------------------------------

DYNAMIC_STATES = ("utdanning", "sysselsatt", "arbeidsledig", "ufor", "pensjonist", "dod")
_AR1_RHO = 0.80      # wage transitory persistence
_AR1_SIGMA = 0.16    # transitory shock sd (log scale)


def simulate_life_states(person_df: pd.DataFrame, years: Iterable[int]) -> dict:
    """Run the per-person yearly life-state machine (no income).

    Returns {'states': (n, Y) object array, 'years': [...], 'uids', 'birth',
    'ses', 'health'} so both person_year and the entity builders consume one
    shared, deterministic state trajectory.
    """
    from mockdata_core import latent_z_vec

    years = sorted(int(y) for y in years)
    Y = len(years)
    n = len(person_df)
    uids = person_df["unit_id"].values.astype(np.int64)
    birth = (pd.to_numeric(person_df["BEFOLKNING_FOEDSELS_AAR_MND"], errors="coerce")
             .fillna(198001).astype(np.int64) // 100).values
    ses = latent_z_vec(uids)
    health = _factor_normal(uids, "health_factor_v1")

    rng = np.random.default_rng(20260608)
    states = np.empty((n, Y), dtype=object)

    a0 = years[0] - birth
    state = np.full(n, "sysselsatt", dtype=object)
    state[a0 < 19] = "utdanning"
    state[a0 >= 67] = "pensjonist"
    p_init_ufor = np.clip(0.004 * (a0 - 25), 0, 0.12) * np.exp(0.4 * health)
    state[(rng.random(n) < p_init_ufor) & (a0 >= 25) & (a0 < 67) & (state == "sysselsatt")] = "ufor"
    state[(rng.random(n) < 0.04) & (state == "sysselsatt")] = "arbeidsledig"

    for yi, y in enumerate(years):
        age = y - birth
        if yi > 0:
            working = np.isin(state, ("sysselsatt", "arbeidsledig"))
            grad = (state == "utdanning") & (age >= 19) & (rng.random(n) < np.clip((age - 18) / 6, 0, 1) * 0.7)
            to_unemp = (state == "sysselsatt") & (rng.random(n) < np.clip(0.04 * np.exp(-0.4 * ses), 0.01, 0.20))
            to_emp = (state == "arbeidsledig") & (rng.random(n) < 0.5)
            p_dis = np.clip(0.0012 * np.exp(0.07 * (age - 30)) * np.exp(0.5 * health) * np.exp(-0.3 * ses), 0, 0.06)
            to_ufor = working & (rng.random(n) < p_dis)
            p_ret = np.where(age >= 67, 0.85, np.where(age >= 62, 0.12, 0.0))
            to_ret = (np.isin(state, ("sysselsatt", "arbeidsledig", "ufor")) & (rng.random(n) < p_ret)) \
                     | (np.isin(state, ("sysselsatt", "arbeidsledig", "ufor", "utdanning")) & (age >= 70))
            p_death = np.clip(np.exp((age - 103) / 9.0) * np.exp(0.4 * health) * np.exp(-0.2 * ses), 0, 0.6)
            to_dead = (state != "dod") & (rng.random(n) < p_death)
            state = state.copy()
            state[grad] = "sysselsatt"
            state[to_emp] = "sysselsatt"
            state[to_unemp] = "arbeidsledig"
            state[to_ufor] = "ufor"
            state[to_ret] = "pensjonist"
            state[to_dead] = "dod"
        states[:, yi] = state

    return {"states": states, "years": years, "uids": uids,
            "birth": birth, "ses": ses, "health": health}


def build_person_year_dynamic(
    engine: MockDataEngine,
    person_df: pd.DataFrame,
    years: Iterable[int] = DEFAULT_YEARS,
    life: Optional[dict] = None,
    on_skip=None,
) -> pd.DataFrame:
    """Longitudinal person_year via the life-state machine.

    Columns: unit_id, year, alder, livsstatus, INNTEKT_WLONN, DAGPENGER,
    UFORETRYGD, ALDERSPENSJON, INNTEKT_WSAMINNT (=sum of the four), plus
    SKATT_NETTOFORMUE and BOSATT_KOMMUNE carried from the base generator.
    Pass a precomputed `life` (from simulate_life_states) to share the exact
    trajectory with the entity builders. Income is NaN when dead / not yet born.
    """
    years = sorted(int(y) for y in years)
    n = len(person_df)
    if life is None:
        life = simulate_life_states(person_df, years)
    uids = life["uids"]
    birth = life["birth"]
    states_mat = life["states"]

    base = build_person_year(engine, person_df,
                             ["INNTEKT_WLONN", "SKATT_NETTOFORMUE", "BOSATT_KOMMUNE"],
                             years, on_skip=on_skip)
    wage_base, wealth_base, komm_base = {}, {}, {}
    for y in years:
        sub = base[base["year"] == y].set_index("unit_id")
        wage_base[y] = pd.to_numeric(sub["INNTEKT_WLONN"], errors="coerce").reindex(uids).fillna(0).values
        wealth_base[y] = sub["SKATT_NETTOFORMUE"].reindex(uids).values
        komm_base[y] = sub["BOSATT_KOMMUNE"].reindex(uids).values

    rng = np.random.default_rng(99001122)
    tau = rng.normal(0, _AR1_SIGMA, n)
    last_emp_wage = wage_base[years[0]].copy()
    career_sum = np.zeros(n)
    career_cnt = np.zeros(n)

    frames = []
    for yi, y in enumerate(years):
        age = y - birth
        state = states_mat[:, yi]

        # --- income conditional on state ---
        bw = wage_base[y]
        tau = _AR1_RHO * tau + math.sqrt(1 - _AR1_RHO ** 2) * rng.normal(0, _AR1_SIGMA, n)
        wlonn = np.zeros(n); dag = np.zeros(n); uf = np.zeros(n); pens = np.zeros(n)

        emp = state == "sysselsatt"
        wlonn[emp] = bw[emp] * np.exp(tau[emp])
        last_emp_wage[emp] = wlonn[emp]
        career_sum[emp] += wlonn[emp]
        career_cnt[emp] += 1

        al = state == "arbeidsledig"
        wlonn[al] = bw[al] * 0.25 * np.exp(tau[al])
        dag[al] = 0.60 * last_emp_wage[al]

        ed = state == "utdanning"
        wlonn[ed] = bw[ed] * 0.10

        uff = state == "ufor"
        wlonn[uff] = bw[uff] * 0.05
        uf[uff] = 0.55 * np.maximum(last_emp_wage[uff], bw[uff] * 0.5)

        ret = state == "pensjonist"
        career_avg = np.where(career_cnt > 0, career_sum / np.maximum(career_cnt, 1), last_emp_wage)
        pens[ret] = 0.55 * career_avg[ret]

        total = wlonn + dag + uf + pens
        df_y = pd.DataFrame({
            "unit_id": uids, "year": y, "alder": age, "livsstatus": state,
            "INNTEKT_WLONN": np.rint(wlonn), "DAGPENGER": np.rint(dag),
            "UFORETRYGD": np.rint(uf), "ALDERSPENSJON": np.rint(pens),
            "INNTEKT_WSAMINNT": np.rint(total),
            "SKATT_NETTOFORMUE": wealth_base[y], "BOSATT_KOMMUNE": komm_base[y],
        })
        gone = (state == "dod") | (age < 0)
        # Registerlogikk: beløp er MISSING (ikke 0) for ikke-deltakere — lønn for
        # ikke-sysselsatte (barn, pensjonister), stønad for ikke-mottakere — i
        # tillegg til døde. Slik blir 0 aldri forvekslet med «ingen record».
        for c in ("INNTEKT_WLONN", "DAGPENGER", "UFORETRYGD", "ALDERSPENSJON", "INNTEKT_WSAMINNT"):
            df_y.loc[gone | (df_y[c] == 0), c] = np.nan
        # Døde / ikke-fødte har heller ikke formue eller bosted — registeret
        # returnerer ingen record etter dødsdato. Sett dem til MISSING i stedet
        # for å videreføre fjorårets verdi (ellers «bor» og «eier» døde personer).
        df_y.loc[gone, ["SKATT_NETTOFORMUE", "BOSATT_KOMMUNE"]] = np.nan
        frames.append(df_y)

    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Mortality / register scope — death dates and a deceased "stock"
#
# microdata's register returns everyone ever registered (incl. ~half dead); you
# filter to the living via a status / death-date variable. We mirror that on a
# small scale: BEFOLKNING_DOEDS_DATO is null for the living, set for the dead
# (panel deaths in-window; a configurable deceased stock died before the panel
# and has no person_year rows). Filter alive = DOEDS_DATO IS NULL.
# ---------------------------------------------------------------------------

def living_death_dates(life: dict, rng=None) -> np.ndarray:
    """DOEDS_DATO (YYYYMMDD float) for in-panel deaths, NaN for those alive at
    panel end."""
    states = life["states"]
    years = life["years"]
    n = states.shape[0]
    if rng is None:
        rng = np.random.default_rng(31415)
    out = np.full(n, np.nan)
    for yi, y in enumerate(years):
        died = states[:, yi] == "dod"
        if yi > 0:
            died = died & (states[:, yi - 1] != "dod")
        else:
            died = np.zeros(n, dtype=bool)
        newly = died & np.isnan(out)
        if newly.any():
            mm = rng.integers(1, 13, n)
            dd = rng.integers(1, 29, n)
            out[newly] = (y * 10000 + mm * 100 + dd)[newly]
    return out


def build_deceased_stock(person_columns, n_dead: int, n_living: int,
                         years: list) -> pd.DataFrame:
    """A light historical-dead cohort: older birth cohorts who died before the
    panel. Only a few demographic columns are populated (kjonn, birth, death);
    the rest are NaN — faithful to sparse historical records and cheap to store.
    Unit ids are offset past the living so they never collide or appear as FKs."""
    rng = np.random.default_rng(424242)
    uids = np.arange(n_living + 1, n_living + n_dead + 1, dtype=np.int64)
    birth_year = rng.integers(1920, 1961, n_dead)
    foeds = (birth_year * 100 + rng.integers(1, 13, n_dead)).astype(np.int64)
    death_year = np.clip(birth_year + rng.integers(55, 95, n_dead), birth_year + 1, years[0] - 1)
    doeds = (death_year * 10000 + rng.integers(1, 13, n_dead) * 100 + rng.integers(1, 29, n_dead)).astype(np.int64)
    kjonn = np.where(rng.random(n_dead) < 0.51, "1", "2").astype(object)

    data = {c: np.full(n_dead, np.nan, dtype=object) for c in person_columns}
    data["unit_id"] = uids
    if "BEFOLKNING_FOEDSELS_AAR_MND" in data:
        data["BEFOLKNING_FOEDSELS_AAR_MND"] = foeds
    if "BEFOLKNING_DOEDS_DATO" in data:
        data["BEFOLKNING_DOEDS_DATO"] = doeds
    if "BEFOLKNING_KJOENN" in data:
        data["BEFOLKNING_KJOENN"] = kjonn
    return pd.DataFrame(data)[list(person_columns)]


# ---------------------------------------------------------------------------
# Life-state-coupled entity spells — jobb (employment) and kjoretoy (ownership)
# ---------------------------------------------------------------------------

def _job_spells(states_row, years, rng) -> list:
    """Derive (start_year, end_year|None) job spells from one person's state row.

    Each contiguous 'sysselsatt' run becomes one or more job spells (split by
    ~5–6 year tenure to model job changes). A spell still active in the last
    panel year is ongoing (end=None)."""
    spells = []
    Y = len(years)
    i = 0
    while i < Y:
        if states_row[i] != "sysselsatt":
            i += 1
            continue
        j = i
        while j + 1 < Y and states_row[j + 1] == "sysselsatt":
            j += 1
        k = i
        while k <= j:
            length = 1 + int(rng.geometric(0.18))
            seg_end = min(k + length - 1, j)
            ongoing = (seg_end == j) and (j == Y - 1)
            spells.append((years[k], None if ongoing else years[seg_end]))
            k = seg_end + 1
        i = j + 1
    return spells


def build_jobb_coupled(engine: MockDataEngine, person_df: pd.DataFrame,
                       life: dict, on_skip=None) -> pd.DataFrame:
    """Build jobb where each row is a job spell coherent with the person's
    employed years; ARB_START / ARB_SLUTT reflect the spell (SLUTT NaN if
    ongoing), other attributes generated per person via the engine."""
    years = life["years"]
    states = life["states"]
    uids = life["uids"]
    rng_s = np.random.default_rng(70707)

    persons, starts, ends = [], [], []
    for i in range(len(uids)):
        for (st, en) in _job_spells(states[i], years, rng_s):
            persons.append(uids[i])
            starts.append(st * 100 + int(rng_s.integers(1, 13)))         # YYYYMM
            ends.append(np.nan if en is None else en * 100 + int(rng_s.integers(1, 13)))
    total = len(persons)
    persons = np.array(persons, dtype=np.int64)

    data = {
        "ARBEIDSFORHOLD_ID": np.arange(1, total + 1, dtype=np.int64),
        "ARBEIDSFORHOLD_PERSON": persons,
        "ARBLONN_ARB_START": np.array(starts, dtype=np.int64),
        "ARBLONN_ARB_SLUTT": np.array(ends, dtype=float),
    }
    rng = np.random.default_rng(70708)
    structural = {"ARBEIDSFORHOLD_ID", "ARBEIDSFORHOLD_PERSON",
                  "ARBLONN_ARB_START", "ARBLONN_ARB_SLUTT"}
    for v in entity_variable_names(engine, "jobb"):
        if v in structural:
            continue
        try:
            data[v] = engine._generate_variable_values(v, v, _meta_of(engine, v), total, rng, uids=persons)
        except Exception as exc:
            if on_skip:
                on_skip(v, f"jobb: {exc}")
    df = pd.DataFrame(data)
    # End reason only applies to ended spells.
    if "ARBLONN_ARB_SLUTTAARSAK" in df.columns:
        df.loc[df["ARBLONN_ARB_SLUTT"].isna(), "ARBLONN_ARB_SLUTTAARSAK"] = np.nan
    return df


def build_kjoretoy_temporal(engine: MockDataEngine, person_df: pd.DataFrame,
                            life: dict, on_skip=None) -> pd.DataFrame:
    """Build kjoretoy with ownership churn: each row is a car-ownership period
    (KJORETOY_EIER_FRA_AAR / _TIL_AAR) within the owner's adult, living years;
    higher-SES persons own more cars. Other attributes via the engine."""
    years = life["years"]
    states = life["states"]
    uids = life["uids"]
    birth = life["birth"]
    ses = life["ses"]
    rng_s = np.random.default_rng(80808)

    persons, fra, til = [], [], []
    for i in range(len(uids)):
        adult = [years[k] for k in range(len(years))
                 if (years[k] - birth[i]) >= 18 and states[i][k] != "dod"]
        if not adult:
            continue
        if rng_s.random() > float(np.clip(0.50 + 0.12 * ses[i], 0.10, 0.92)):
            continue
        n_cars = 1 + int(rng_s.random() < float(np.clip(0.25 + 0.10 * ses[i], 0, 0.6)))
        for _ in range(n_cars):
            t = adult[0] + int(rng_s.integers(0, max(1, len(adult))))
            while t <= adult[-1]:
                hold = 1 + int(rng_s.geometric(0.16))           # ~6-year tenure
                disp = t + hold - 1
                ongoing = disp >= adult[-1]
                persons.append(uids[i])
                fra.append(t)
                til.append(np.nan if ongoing else disp)
                t = disp + 1
    total = len(persons)
    persons = np.array(persons, dtype=np.int64)

    data = {
        "KJORETOY_ID": np.arange(1, total + 1, dtype=np.int64),
        "KJORETOY_KJORETOYID_FNR": persons,
        "KJORETOY_EIER_FRA_AAR": np.array(fra, dtype=np.int64),
        "KJORETOY_EIER_TIL_AAR": np.array(til, dtype=float),
    }
    rng = np.random.default_rng(80809)
    structural = {"KJORETOY_ID", "KJORETOY_KJORETOYID_FNR"}
    for v in entity_variable_names(engine, "kjoretoy"):
        if v in structural:
            continue
        try:
            data[v] = engine._generate_variable_values(v, v, _meta_of(engine, v), total, rng, uids=persons)
        except Exception as exc:
            if on_skip:
                on_skip(v, f"kjoretoy: {exc}")
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# Entity tables (1:N to person) — jobb, kjoretoy, kurs
# ---------------------------------------------------------------------------

# Deterministic dependency order for the NPR episode table (UTDATO needs INNDATO
# and OMSORGSNIVA present; AGGRSHOPPID first establishes the episode rows).
NPR_VAR_ORDER = [
    "AGGRSHOPPID", "NPRID", "OMSORGSNIVA", "NIVA",
    "HOVEDTILSTAND1", "HOVEDTILSTAND2",
    "INNDATO", "UTDATO", "INNTID", "UTTID",
]

# Entity types the engine genuinely models as a 1:N structure relative to person.
MULTI_RECORD_ENTITIES = list(_ENTITY_MULTI_RECORD_PROFILE.keys())  # jobb, kjoretoy, kurs


def entity_variable_names(engine: MockDataEngine, entity_type: str) -> list[str]:
    """All short variable names whose metadata maps to `entity_type`."""
    names: set[str] = set()
    for name, meta in engine.catalog.items():
        if isinstance(meta, dict) and _entity_of(meta) == entity_type:
            names.add(name.split("/")[-1])
    return sorted(names)


def build_entity_table(
    engine: MockDataEngine,
    entity_type: str,
    var_names: Optional[Iterable[str]] = None,
    on_skip=None,
) -> pd.DataFrame:
    """Build a multi-record entity table (jobb / kjoretoy / kurs).

    The first import on an empty frame builds the deterministic 1:N structure
    ([id_col, ref_col, first_var]); subsequent imports add columns merged on the
    entity id_col. ref_col is the foreign key back to person.unit_id.
    """
    if var_names is None:
        var_names = entity_variable_names(engine, entity_type)
    id_col = _ENTITY_ID_COL.get(entity_type, _UNIT_ID)
    ref_col = _ENTITY_PERSON_REF_COL.get(entity_type, "person_ref")
    # The id_col and ref_col are themselves catalog variables, but they are
    # created by the first structural import — importing them again collides
    # on merge. Drop them from the attribute loop.
    structural = {id_col, ref_col}
    var_names = [v for v in dict.fromkeys(var_names) if v not in structural]

    cur: Optional[pd.DataFrame] = None
    for v in var_names:
        try:
            res = engine.generate("import", {"var": v},
                                  cur if cur is not None else pd.DataFrame())
        except Exception as exc:
            if on_skip:
                on_skip(v, f"{entity_type}: {exc}")
            continue
        if res is None or res.empty:
            if on_skip:
                on_skip(v, f"{entity_type}: empty")
            continue
        if cur is None:
            cur = res  # [id_col, ref_col, v]
        else:
            if v not in res.columns or id_col not in res.columns:
                if on_skip:
                    on_skip(v, f"{entity_type}: missing {id_col}/{v}")
                continue
            cur = cur.merge(res[[id_col, v]], on=id_col, how="left")
    if cur is None:
        ref_col = _ENTITY_PERSON_REF_COL.get(entity_type, "person_ref")
        return pd.DataFrame(columns=[id_col, ref_col])
    return cur


def build_npr_table(
    engine: MockDataEngine,
    var_names: Iterable[str] = NPR_VAR_ORDER,
    on_skip=None,
) -> pd.DataFrame:
    """Build the NPR hospital-episode table (Behandlingsopphold).

    Every NPR variable routes through the engine's episode generator. The first
    import establishes episode rows ([unit_id, AGGRSHOPPID, var]); later imports
    merge on AGGRSHOPPID. unit_id is the foreign key back to person.unit_id.
    """
    cur: Optional[pd.DataFrame] = None
    for v in var_names:
        try:
            res = engine.generate("import", {"var": v},
                                  cur if cur is not None else pd.DataFrame())
        except Exception as exc:
            if on_skip:
                on_skip(v, f"npr: {exc}")
            continue
        if res is None or res.empty:
            if on_skip:
                on_skip(v, "npr: empty")
            continue
        if cur is None:
            cur = res  # [unit_id, AGGRSHOPPID, v]
        elif "AGGRSHOPPID" in res.columns and v in res.columns:
            cur = cur.merge(res[["AGGRSHOPPID", v]], on="AGGRSHOPPID", how="left")
        else:
            if on_skip:
                on_skip(v, "npr: missing AGGRSHOPPID/value")
    if cur is None:
        return pd.DataFrame(columns=[_UNIT_ID, "AGGRSHOPPID"])
    return cur


# ---------------------------------------------------------------------------
# Traffic accidents — a two-table register with a many-to-many bridge.
#
# Unlike jobb/kjoretoy/kurs (1:N person->entity), the engine does NOT model
# these, so we build them from metadata here:
#
#   trafikkulykke            one row per accident   (PK: TRAFULYK_ID)
#   person_i_trafikkulykke   one row per (accident, person) involvement
#                            FK TRAFULYK_PERS_TRAFULYK -> trafikkulykke.TRAFULYK_ID
#                            FK TRAFULYK_PERS_FNR      -> person.unit_id
# ---------------------------------------------------------------------------

TRAF_ACCIDENT_PK = "TRAFULYK_ID"       # minted accident primary key
TRAF_PERSON_PK = "TRAFULYK_PERS_ID"    # minted involvement primary key

# Accident-level columns we synthesise directly (not via the metadata sampler).
_TRAF_ACC_STRUCTURAL = {"TRAFULYK_AARMND", "TRAFULYK_ANTALL_PERS", "TRAFULYK_ANTALL_KJT"}
# Involvement columns derived from the linked person / accident.
_TRAF_PERS_STRUCTURAL = {
    "TRAFULYK_PERS_TRAFULYK", "TRAFULYK_PERS_FNR",
    "TRAFULYK_PERS_AARMND", "TRAFULYK_PERS_ALDER", "TRAFULYK_PERS_KJOENN",
}


def _traf_var_names(engine: MockDataEngine, enhetstype: str) -> list[str]:
    return sorted({
        name.split("/")[-1]
        for name, meta in engine.catalog.items()
        if isinstance(meta, dict)
        and meta.get("enhetstype") == enhetstype
        and name.split("/")[-1].startswith("TRAFULYK")
    })


def _meta_of(engine: MockDataEngine, short: str) -> dict:
    return (engine.catalog.get(short)
            or getattr(engine, "_catalog_by_short", {}).get(short)
            or {})


def build_trafikkulykke(
    engine: MockDataEngine,
    person_df: pd.DataFrame,
    years: Iterable[int] = DEFAULT_YEARS,
    accident_rate: float = 0.02,
    on_skip=None,
) -> dict:
    """Build the accident register and its person-involvement bridge.

    `accident_rate` is accidents per person over the whole period (0.02 =>
    2,000 accidents for 100,000 persons). Each accident involves a Poisson(1.5)
    number of distinct persons (>=1). Person age/gender are looked up from
    `person_df` so the bridge stays consistent with the person table.
    Returns {'trafikkulykke': df, 'person_i_trafikkulykke': df}.
    """
    rng = np.random.default_rng(int(hashlib.md5(b"trafikkulykke").hexdigest(), 16) % (2**31))
    persons = engine.person_universe
    n_persons = len(persons)
    years = list(years)
    y0, y1 = min(years), max(years)

    n_acc = max(1, int(n_persons * accident_rate))
    acc_ids = np.arange(1, n_acc + 1, dtype=np.int64)
    aarmnd = rng.integers(y0, y1 + 1, n_acc) * 100 + rng.integers(1, 13, n_acc)
    antall_pers = np.clip(rng.poisson(1.5, n_acc), 1, 6).astype(np.int64)
    antall_kjt = np.clip(rng.poisson(1.3, n_acc), 1, 4).astype(np.int64)

    acc: dict = {
        TRAF_ACCIDENT_PK: acc_ids,
        "TRAFULYK_AARMND": aarmnd,
        "TRAFULYK_ANTALL_PERS": antall_pers,
        "TRAFULYK_ANTALL_KJT": antall_kjt,
    }
    for v in _traf_var_names(engine, "Trafikkulykke"):
        if v in _TRAF_ACC_STRUCTURAL:
            continue
        try:
            acc[v] = engine._generate_variable_values(v, v, _meta_of(engine, v), n_acc, rng, uids=acc_ids)
        except Exception as exc:
            if on_skip:
                on_skip(v, f"trafikkulykke: {exc}")
    acc_df = pd.DataFrame(acc)

    # --- bridge: one row per (accident, involved person) ---
    total = int(antall_pers.sum())
    acc_for_row = np.repeat(acc_ids, antall_pers)
    aarmnd_for_row = np.repeat(aarmnd, antall_pers)

    person_fk = np.empty(total, dtype=np.int64)
    idx = 0
    for a in range(n_acc):
        k = int(antall_pers[a])
        person_fk[idx:idx + k] = rng.choice(persons, size=k, replace=False)
        idx += k

    # Look up gender/age from the person table for consistency.
    pdf = person_df.set_index("unit_id")
    gv = pd.to_numeric(pdf.get("BEFOLKNING_KJOENN"), errors="coerce").reindex(person_fk).fillna(1).astype(int).values
    birth_year = (pd.to_numeric(pdf.get("BEFOLKNING_FOEDSELS_AAR_MND"), errors="coerce")
                  .reindex(person_fk).fillna(198001) // 100).astype(int).values
    ages = np.clip((aarmnd_for_row // 100) - birth_year, 0, 110).astype(np.int64)

    bridge: dict = {
        TRAF_PERSON_PK: np.arange(1, total + 1, dtype=np.int64),
        "TRAFULYK_PERS_TRAFULYK": acc_for_row,
        "TRAFULYK_PERS_FNR": person_fk,
        "TRAFULYK_PERS_AARMND": aarmnd_for_row,
        "TRAFULYK_PERS_ALDER": ages,
        "TRAFULYK_PERS_KJOENN": gv.astype(str),
    }
    for v in _traf_var_names(engine, "Person i trafikkulykke"):
        if v in _TRAF_PERS_STRUCTURAL:
            continue
        try:
            bridge[v] = engine._generate_variable_values(v, v, _meta_of(engine, v), total, rng, uids=person_fk)
        except Exception as exc:
            if on_skip:
                on_skip(v, f"person_i_trafikkulykke: {exc}")
    bridge_df = pd.DataFrame(bridge)

    return {"trafikkulykke": acc_df, "person_i_trafikkulykke": bridge_df}


# ---------------------------------------------------------------------------
# Målepunkt (Elhub electricity metering points) — 1:N person -> metering point.
#
#   malepunkt   one row per metering point  (PK: MALEPUNKT_ID)
#               FK ELHUB_PERS_MALEPUNKTID_FNR -> person.unit_id
#
# The engine doesn't model this entity, and STROMFORBRUK/KRAFTPRODUKSJON are
# floats with only a `mean` (no std) -> the generic sampler would be wildly off,
# so we synthesise the amounts here (household consumption lognormal; production
# a hurdle: mostly zero, occasional solar).
# ---------------------------------------------------------------------------

MALEPUNKT_PK = "MALEPUNKT_ID"
MALEPUNKT_REF = "ELHUB_PERS_MALEPUNKTID_FNR"
# Share of persons with >=1 metering point, and the per-person count profile.
MALEPUNKT_PROFILE = {"p_has": 0.60, "mean": 1.15, "max": 3}


def _kommune_codes(engine: MockDataEngine) -> list[str]:
    """Valid 4-digit municipality codes from the BOSATT_KOMMUNE codelist."""
    meta = _meta_of(engine, "BOSATT_KOMMUNE")
    labels = meta.get("labels") or {}
    codes = [str(k) for k in labels if str(k).isdigit() and len(str(k)) == 4 and str(k) != "0000"]
    return codes or ["0301"]


def build_malepunkt(
    engine: MockDataEngine,
    person_df: pd.DataFrame,
    on_skip=None,
) -> pd.DataFrame:
    """Build the Elhub metering-point register (1:N to person)."""
    rng = np.random.default_rng(int(hashlib.md5(b"malepunkt").hexdigest(), 16) % (2**31))
    persons = engine.person_universe
    n_persons = len(persons)

    has = rng.random(n_persons) < MALEPUNKT_PROFILE["p_has"]
    persons_with = persons[has]
    counts = np.clip(rng.poisson(MALEPUNKT_PROFILE["mean"], len(persons_with)), 1, MALEPUNKT_PROFILE["max"])
    person_fk = np.repeat(persons_with, counts).astype(np.int64)
    total = int(len(person_fk))
    mp_ids = np.arange(1, total + 1, dtype=np.int64)

    # Categoricals with real distributions -> engine sampler.
    prisomrade = engine._generate_variable_values(
        "ELHUB_PERS_PRISOMRADE", "ELHUB_PERS_PRISOMRADE",
        _meta_of(engine, "ELHUB_PERS_PRISOMRADE"), total, rng, uids=person_fk)
    typ = np.asarray(engine._generate_variable_values(
        "ELHUB_PERS_TYPE_STROMFORBRUK", "ELHUB_PERS_TYPE_STROMFORBRUK",
        _meta_of(engine, "ELHUB_PERS_TYPE_STROMFORBRUK"), total, rng, uids=person_fk), dtype=object)

    # Municipality of the metering point (real kommune codes).
    kommune = rng.choice(_kommune_codes(engine), size=total)

    # Consumption (kWh/yr): lognormal ~18 MWh household; cabins (type 2) lower.
    cons = rng.lognormal(mean=np.log(18000.0), sigma=0.45, size=total)
    cons = np.where(typ.astype(str) == "2", cons * 0.35, cons)
    stromforbruk = np.round(cons, 1)

    # Production (kWh/yr): hurdle — ~92% zero, else lognormal (solar).
    has_prod = rng.random(total) < 0.08
    prod = np.where(has_prod, rng.lognormal(mean=np.log(3000.0), sigma=0.6, size=total), 0.0)
    kraftproduksjon = np.round(prod, 1)

    return pd.DataFrame({
        MALEPUNKT_PK: mp_ids,
        MALEPUNKT_REF: person_fk,
        "ELHUB_PERS_PRISOMRADE": [str(p) for p in prisomrade],
        "ELHUB_PERS_TYPE_STROMFORBRUK": [str(t) for t in typ],
        "ELHUB_PERS_MALEPUNKT_ADR_KOMMUNE": kommune,
        "ELHUB_PERS_STROMFORBRUK": stromforbruk,
        "ELHUB_PERS_KRAFTPRODUKSJON": kraftproduksjon,
    })


# ---------------------------------------------------------------------------
# Kommune dimension + KOSTRA fact table.
#
# The Kommune-enhetstype variables are KOSTRA municipal statistics (salary
# expenses by function + waste per capita), keyed by municipality, not person.
# The engine has no per-kommune generation, so we build:
#
#   kommune        one row per municipality (PK: kommune_nr)
#                  parent of person_year.BOSATT_KOMMUNE
#   kommune_year   kommune × year, KOSTRA values
#                  FK kommune_nr -> kommune.kommune_nr
#
# Metadata for these is thin (placeholder min/max), so values are MODEL-BASED,
# not calibrated to real KOSTRA: population is derived from where the synthetic
# persons live; salary totals scale with that population; per-capita metrics use
# the metadata mean. Realistic in structure, not in absolute level.
# ---------------------------------------------------------------------------

_NORWAY_POPULATION = 5_450_000  # for scaling synthetic residency to realistic sizes
_KOSTRA_ANNUAL_GROWTH = 0.03    # nominal year-over-year drift in expenses


def _kommune_vars(engine: MockDataEngine) -> list[str]:
    return sorted({
        name.split("/")[-1]
        for name, meta in engine.catalog.items()
        if isinstance(meta, dict) and meta.get("enhetstype") == "Kommune"
    })


def build_kommune(
    engine: MockDataEngine,
    person_year_df: pd.DataFrame,
    years: Iterable[int] = DEFAULT_YEARS,
    n_persons: Optional[int] = None,
    on_skip=None,
) -> dict:
    """Build the kommune dimension and the KOSTRA kommune_year fact table.

    Population per municipality is taken from synthetic residency in
    `person_year_df` (BOSATT_KOMMUNE) scaled to realistic Norwegian magnitude.
    Returns {'kommune': dim_df, 'kommune_year': fact_df}.
    """
    years = list(years)
    y0 = min(years)
    n_persons = n_persons if n_persons is not None else len(engine.person_universe)
    scale = _NORWAY_POPULATION / max(1, n_persons)

    labels = _meta_of(engine, "BOSATT_KOMMUNE").get("labels") or {}
    name_of = {int(k): str(v) for k, v in labels.items() if str(k).lstrip("-").isdigit() and int(k) > 0}

    # Codes that actually appear as residency (any year) -> dimension members.
    res = pd.to_numeric(person_year_df["BOSATT_KOMMUNE"], errors="coerce")
    ry = pd.DataFrame({"kommune_nr": res, "year": person_year_df["year"]}).dropna()
    ry = ry[ry["kommune_nr"] > 0]
    ry["kommune_nr"] = ry["kommune_nr"].astype(int)
    # Population proxy: max residents across years for that code, scaled.
    pop_count = ry.groupby(["kommune_nr", "year"]).size().groupby("kommune_nr").max()
    codes = sorted(pop_count.index.tolist())
    K = len(codes)

    befolkning = {c: int(round(int(pop_count[c]) * scale)) for c in codes}
    dim = pd.DataFrame({
        "kommune_nr": codes,
        "kommune_navn": [name_of.get(c, str(c)) for c in codes],
        "fylke_nr": [c // 100 for c in codes],
        "befolkning": [befolkning[c] for c in codes],
    })

    # --- kommune_year fact: cross product codes × years ---
    kom_idx = np.repeat(np.arange(K), len(years))
    year_for_row = np.tile(np.array(years), K)
    pop_for_row = np.array([befolkning[codes[i]] for i in kom_idx], dtype=float)
    n = len(kom_idx)

    fact: dict = {
        "kommune_nr": [codes[i] for i in kom_idx],
        "year": year_for_row,
    }

    for v in _kommune_vars(engine):
        meta = _meta_of(engine, v)
        rng = np.random.default_rng(int(hashlib.md5(v.encode()).hexdigest(), 16) % (2**31))
        is_per_capita = "INNBYGGER" in v
        if is_per_capita:
            base = float(meta.get("mean") or 100.0)
            col = base * np.exp(rng.normal(0.0, 0.12, n))
            fact[v] = np.round(col, 1)
        else:
            # Salary-expense total (1000 NOK): population × per-capita rate ×
            # kommune fixed effect × nominal growth × small transient noise.
            rate = float(np.exp(rng.normal(np.log(0.30), 1.1)))          # 1000 NOK per capita
            kom_eff = np.exp(rng.normal(0.0, 0.30, K))[kom_idx]
            growth = (1.0 + _KOSTRA_ANNUAL_GROWTH) ** (year_for_row - y0)
            transient = np.exp(rng.normal(0.0, 0.07, n))
            col = pop_for_row * rate * kom_eff * growth * transient
            fact[v] = np.maximum(0, np.rint(col)).astype(np.int64)

    fact_df = pd.DataFrame(fact)
    return {"kommune": dim, "kommune_year": fact_df}


# ---------------------------------------------------------------------------
# Broad latent structure — multi-factor Gaussian-copula reordering.
#
# Makes a person's "type" propagate across the register. Each person has a few
# deterministic latent factors (ses reuses the existing latent_z; plus health,
# urban, family, and real age). For each eligible quantity variable we reorder
# its values across persons to rank-align with a weighted sum of the factors.
#
# Two guarantees:
#   * Marginals preserved EXACTLY — reordering is a permutation of the existing
#     values, so every column's distribution is byte-identical.
#   * Realism anchors untouched — variables that already carry a realism spec
#     (income/wealth age curves) are NOT reordered; the independent quantity
#     variables are aligned to the SAME latent_z those anchors load on, so they
#     correlate with income/wealth without destroying existing structure.
#
# Only numeric, label-free quantity variables are reordered (reordering nominal
# codes like municipality/occupation would be meaningless); everything else
# stays independent. Coverage is reported, not hidden.
# ---------------------------------------------------------------------------

LATENT_FACTORS = ("ses", "health", "urban", "family", "age")


def _factor_normal(uids: np.ndarray, salt: str) -> np.ndarray:
    """Deterministic N(0,1) per unit_id for a named factor (same scheme as latent_z)."""
    out = np.empty(len(uids), dtype=float)
    for i, u in enumerate(uids):
        h = hashlib.md5(f"{salt}:{int(u)}".encode()).digest()
        u1 = max(1e-12, min(1 - 1e-12, int.from_bytes(h[:4], "big") / 2**32))
        u2 = max(1e-12, min(1 - 1e-12, int.from_bytes(h[4:8], "big") / 2**32))
        out[i] = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
    return out


def _standardize(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    sd = np.nanstd(x)
    return (x - np.nanmean(x)) / sd if sd > 0 else np.zeros_like(x)


# Name tokens that mark a column as a demographic/identifier attribute (age,
# year, date, sex, duration) rather than an economic quantity — left independent.
_NON_STRUCTURAL_TOKENS = ("_ALDER", "ALDER", "FODTAAR", "_AAR", "FOEDT", "FODT",
                          "_DATO", "DATO", "_MND", "BOTID", "KJOENN", "KJONN")


def _variable_loadings(short: str, title: str, is_money: bool) -> dict:
    """Assign {factor: signed_loading} for a variable.

    Uses the engine's money classification as the primary signal: monetary
    variables drive the SES / age / health structure (with sign from benefit vs
    earnings vs pension vs student). Non-money columns only load when clearly a
    family count or centrality measure. Returns {} (independent) otherwise.
    """
    s = short.upper()
    t = (title or "").lower()
    L: dict = {}

    def has(*subs):
        return any(x in s for x in subs) or any(x.lower() in t for x in subs)

    # Never structure pure demographic/id/date/duration fields.
    if any(tok in s for tok in _NON_STRUCTURAL_TOKENS):
        return {}

    if is_money:
        is_benefit = (s.startswith(("SOSHJELP", "SOSHJLP", "BOSTOTTE", "BARNEVERN", "INTRO"))
                      or "SOSIAL" in s or has("sosialhjelp", "bostøtte", "stønad", "dagpenger"))
        is_pension = (s.startswith(("PENSJ", "AFP", "ALDPENSJ", "ETLATEKT")) or has("pensjon"))
        is_student = (s.startswith("LAANEKASSEN") or has("stipend", "studielån", "studie"))
        is_health = (s.startswith(("REHAB", "UFORE", "UFOER")) or has("uføre", "sykepeng", "rehabilit", "arbeidsavklar"))

        if is_pension:
            L["age"] = 0.55
        elif is_student:
            L["age"] = -0.45
            L["ses"] = 0.1
        elif is_health:
            L["health"] = 0.45
            L["ses"] = -0.2
        elif is_benefit:
            L["ses"] = -0.5
        else:                       # earnings, wealth, tax base, capital income
            L["ses"] = 0.5
    else:
        if has("antall barn", "barnetrygd", "kontantstøtte") or "ANTALL_BARN" in s:
            L["family"] = 0.5
        elif has("husholdning", "familiefase", "sivilstand", "ektefelle", "samboer"):
            L["family"] = 0.4
        elif has("sentralitet", "tettsted"):
            L["urban"] = 0.5

    ss = sum(v * v for v in L.values())
    if ss >= 0.95:
        k = math.sqrt(0.95 / ss)
        L = {f: v * k for f, v in L.items()}
    return L


def apply_latent_structure(
    person_df: pd.DataFrame,
    engine: MockDataEngine,
    on_report=None,
    ref_year: Optional[int] = None,
) -> pd.DataFrame:
    """Reorder eligible quantity columns to induce broad cross-correlation while
    preserving every marginal exactly. Returns a new DataFrame.

    `on_report(dict)` receives a summary: which variables were loaded on which
    factors, and how many were left independent.
    """
    df = person_df.copy()
    n = len(df)
    uids = df[_UNIT_ID].values

    realism_vars = {
        k.split("/")[-1] for k, v in engine.catalog.items()
        if isinstance(v, dict) and v.get("realism")
    }

    # Per-person factor matrix.
    factors = {
        "ses": _factor_normal(uids, "norway_latent_v1"),  # == latent_z (anchors load this)
        "health": _factor_normal(uids, "health_factor_v1"),
        "urban": _factor_normal(uids, "urban_factor_v1"),
        "family": _factor_normal(uids, "family_factor_v1"),
    }
    if "BEFOLKNING_FOEDSELS_AAR_MND" in df.columns:
        # Referanseår for alders-latenten må følge bygginga, ikke være hardkodet
        # (ellers er alderen ~5–8 år for høy for bygg som dekker 2015–2018).
        _ref_y = ref_year if ref_year else max(DEFAULT_YEARS)
        age = _ref_y - (pd.to_numeric(df["BEFOLKNING_FOEDSELS_AAR_MND"], errors="coerce") // 100)
        factors["age"] = _standardize(age.fillna(age.median()).values)
    else:
        factors["age"] = np.zeros(n)

    loaded: dict = {}
    skipped_reasons = {"labeled_or_nominal": 0, "realism_anchor": 0, "no_loading": 0, "ref_or_id": 0, "low_card": 0}

    for col in df.columns:
        if col == _UNIT_ID:
            continue
        if col in realism_vars:
            skipped_reasons["realism_anchor"] += 1
            continue
        if col.endswith(("_FNR", "_ID")) or "PERSONID" in col:
            skipped_reasons["ref_or_id"] += 1
            continue
        if not pd.api.types.is_numeric_dtype(df[col]):
            skipped_reasons["labeled_or_nominal"] += 1
            continue
        meta = _meta_of(engine, col)
        if meta.get("labels"):  # coded/nominal — reordering codes is meaningless
            skipped_reasons["labeled_or_nominal"] += 1
            continue
        vals = df[col].values
        if pd.Series(vals).nunique(dropna=True) < 5:
            skipped_reasons["low_card"] += 1
            continue

        is_money = bool(_norway_classify_money_demo(meta, col))
        L = _variable_loadings(col, meta.get("short_title", ""), is_money)
        if not L:
            skipped_reasons["no_loading"] += 1
            continue

        # Target score = weighted factors + idiosyncratic remainder (var-seeded).
        rng = np.random.default_rng(int(hashlib.md5(("struct:" + col).encode()).hexdigest(), 16) % (2**31))
        score = np.zeros(n)
        for f, w in L.items():
            score = score + w * factors[f]
        rem = math.sqrt(max(0.0, 1.0 - sum(w * w for w in L.values())))
        score = score + rem * rng.standard_normal(n)

        # Rank-match: assign sorted values to persons in score order (NaNs last).
        order = np.argsort(np.where(np.isnan(score), np.inf, score), kind="stable")
        sorted_vals = np.sort(vals)  # NaNs sort to the end in numpy
        new = np.empty_like(vals)
        new[order] = sorted_vals
        df[col] = new
        loaded[col] = L

    report = {"n_loaded": len(loaded), "loaded": loaded, "skipped": skipped_reasons,
              "factors": list(factors.keys())}
    if on_report:
        on_report(report)
    return df


# ---------------------------------------------------------------------------
# Codebook — value labels + variable descriptions (self-describing dataset)
#
# Fact tables store CODES (matches microdata.no; compact). Labels are kept once
# in a lookup rather than denormalised into the data — essential for large
# codelists (BOSATT_KOMMUNE alone has 821). Two tables:
#
#   value_labels  [variable, code, code_num, label, codelist]  one row/(var,code)
#   variables     [name, short_title, data_type, enhetstype, temporalitet, ...]
#
# Join example:
#   SELECT p.unit_id, vl.label AS kjonn
#   FROM person p JOIN value_labels vl
#     ON vl.variable='BEFOLKNING_KJOENN' AND vl.code_num=p.BEFOLKNING_KJOENN
# ---------------------------------------------------------------------------

_VALIDITY_FULL_RE = re.compile(r"Gyldighetsperiode:\s*(\d{4}-\d{2}-\d{2})\s*[–—-]\s*(\d{4}-\d{2}-\d{2})")
_VALIDITY_START_RE = re.compile(r"Gyldighetsperiode:\s*(\d{4}-\d{2}-\d{2})")


def _parse_validity(desc: Optional[str]) -> tuple:
    """Return (valid_from, valid_to) ISO dates from a description, or (None, None).

    Handles both bounded windows and open-ended ones ('… – ∞')."""
    if not desc:
        return (None, None)
    m = _VALIDITY_FULL_RE.search(desc)
    if m:
        return (m.group(1), m.group(2))
    m = _VALIDITY_START_RE.search(desc)
    if m:
        return (m.group(1), None)
    return (None, None)


# temporalitet values that are imported at a single date and follow a yearly
# grid (income snapshots, cross-sections). Forløp = event-based, Fast = constant.
_GRID_TEMPORALITET = {"Akkumulert", "Tverrsnitt"}


def valid_import_dates(valid_from: Optional[str], valid_to: Optional[str],
                       temporalitet: Optional[str]) -> list:
    """Enumerate legal import dates: each year from valid_from..valid_to at
    valid_from's month-day (reproduces microdata's yearly grid, e.g.
    INNTEKT_WLONN -> 2010-01-01, 2011-01-01, ...).

    Akkumulert = value accrued UP TO the date, so the period-END month-day each
    year is also legal (full-year income on ÅR-12-31, not just ÅR-01-01) — these
    are appended. Tverrsnitt is a single-month-day snapshot (start only).

    Returns [] for Forløp/Fast or when the window is missing — those aren't
    imported on a yearly date grid (Fast = constant; check the window instead).
    """
    if not valid_from or not valid_to or temporalitet not in _GRID_TEMPORALITET:
        return []
    fy, fm, fd = valid_from.split("-")
    ty_s, tm, td = valid_to.split("-")
    fy_i, ty_i = int(fy), int(ty_s)
    dates = [f"{y:04d}-{fm}-{fd}" for y in range(fy_i, ty_i + 1)]
    if temporalitet == "Akkumulert" and (tm, td) != (fm, fd):
        dates += [f"{y:04d}-{tm}-{td}" for y in range(fy_i, ty_i + 1)]
    # Clamp to the validity window: the last year's start-month-day can fall
    # AFTER valid_to (and an Akkumulert end-month-day in the first year can fall
    # BEFORE valid_from). A discontinued variable must not offer such dates.
    return [d for d in dates if valid_from <= d <= valid_to]


def is_valid_import_date(date: str, valid_from: Optional[str], valid_to: Optional[str],
                         temporalitet: Optional[str]) -> bool:
    """True if `date` (YYYY-MM-DD) is a legal import date for the variable.

    Grid variables: date must be on the yearly grid. Fast/Forløp: date must fall
    within the validity window.
    """
    if temporalitet in _GRID_TEMPORALITET:
        return date in valid_import_dates(valid_from, valid_to, temporalitet)
    if valid_from and valid_to:
        return valid_from <= date <= valid_to
    return False


def build_codebook(engine: MockDataEngine) -> dict:
    """Build {'variables': df, 'value_labels': df, 'valid_dates': df} from the catalog.

    External codelists (NUS/NACE/STYRK08/KOMM) are resolved via the engine's
    ensure_variable_resolved so their labels are included. `code_num` is the
    integer form of `code` when it is integer-like (else <NA>), to make joins to
    numeric columns (e.g. kommune 301 vs label key '0301') straightforward.
    """
    var_rows: list = []
    lab_rows: list = []
    seen_vars: set = set()

    for full, meta in list(engine.catalog.items()):
        if not isinstance(meta, dict):
            continue
        short = full.split("/")[-1]
        if short in seen_vars:
            continue

        # Resolve external labels (codelists/*.json) if not already inline.
        if meta.get("external_metadata") and not meta.get("labels"):
            try:
                engine.ensure_variable_resolved(short)
                meta = engine.catalog.get(short) or _meta_of(engine, short) or meta
            except Exception:
                pass

        labels = meta.get("labels")
        n_labels = len(labels) if isinstance(labels, dict) else 0
        seen_vars.add(short)
        valid_from, valid_to = _parse_validity(meta.get("description"))
        var_rows.append({
            "name": short,
            "short_title": meta.get("short_title"),
            "data_type": meta.get("data_type"),
            "microdata_datatype": meta.get("microdata_datatype"),
            "enhetstype": meta.get("enhetstype"),
            "temporalitet": meta.get("temporalitet"),
            "valid_from": valid_from,
            "valid_to": valid_to,
            "databank": meta.get("databank"),
            "n_labels": n_labels,
        })
        if isinstance(labels, dict):
            codelist = "external" if meta.get("external_metadata") else "inline"
            for code, label in labels.items():
                cs = str(code)
                try:
                    cn = int(cs)
                except (TypeError, ValueError):
                    cn = None
                lab_rows.append({
                    "variable": short, "code": cs, "code_num": cn,
                    "label": str(label), "codelist": codelist,
                })

    variables = pd.DataFrame(var_rows).drop_duplicates("name").reset_index(drop=True)
    value_labels = pd.DataFrame(lab_rows).drop_duplicates(["variable", "code"]).reset_index(drop=True)
    if len(value_labels):
        value_labels["code_num"] = value_labels["code_num"].astype("Int64")

    # valid_dates: enumerated legal import dates per variable (the yearly grid).
    date_rows = []
    for r in var_rows:
        for d in valid_import_dates(r["valid_from"], r["valid_to"], r["temporalitet"]):
            date_rows.append({"variable": r["name"], "valid_date": d})
    valid_dates = (pd.DataFrame(date_rows).drop_duplicates().reset_index(drop=True)
                   if date_rows else pd.DataFrame(columns=["variable", "valid_date"]))

    return {"variables": variables, "value_labels": value_labels, "valid_dates": valid_dates}


# ---------------------------------------------------------------------------
# Derived reference codebooks — small lookups for common transforms.
# Pattern: each is a plain (code -> label) or (source -> target) table sitting
# beside value_labels. Add more by copying the shape; no generic framework.
# ---------------------------------------------------------------------------

# Norwegian counties across reform eras (pre-2020 01–20, 2020–2023 merges,
# 2024+ re-splits). Union — numbers don't collide across eras.
_FYLKE_NAVN = {
    1: "Østfold", 2: "Akershus", 3: "Oslo", 4: "Hedmark", 5: "Oppland",
    6: "Buskerud", 7: "Vestfold", 8: "Telemark", 9: "Aust-Agder", 10: "Vest-Agder",
    11: "Rogaland", 12: "Hordaland", 14: "Sogn og Fjordane", 15: "Møre og Romsdal",
    16: "Sør-Trøndelag", 17: "Nord-Trøndelag", 18: "Nordland", 19: "Troms", 20: "Finnmark",
    30: "Viken", 34: "Innlandet", 38: "Vestfold og Telemark", 42: "Agder",
    46: "Vestland", 50: "Trøndelag", 54: "Troms og Finnmark",
    31: "Østfold", 32: "Akershus", 33: "Buskerud", 39: "Vestfold", 40: "Telemark",
    55: "Troms", 56: "Finnmark",
}

# ICD-10 chapter by first letter (single-letter rollup the user asked for).
# Simplification: letters spanning two chapters (D, H) map to the primary one.
_ICD10_KAPITTEL = {
    "A": "I Visse infeksjonssykdommer", "B": "I Visse infeksjonssykdommer",
    "C": "II Svulster", "D": "II Svulster / III Blod og immunsystem",
    "E": "IV Endokrine og metabolske sykdommer", "F": "V Psykiske lidelser",
    "G": "VI Nervesystemet", "H": "VII Øyet / VIII Øret",
    "I": "IX Sirkulasjonssystemet", "J": "X Åndedrettssystemet",
    "K": "XI Fordøyelsessystemet", "L": "XII Hud og underhud",
    "M": "XIII Muskel-skjelett og bindevev", "N": "XIV Urin- og kjønnsorganer",
    "O": "XV Svangerskap, fødsel og barseltid", "P": "XVI Perinatale tilstander",
    "Q": "XVII Medfødte misdannelser", "R": "XVIII Symptomer og unormale funn",
    "S": "XIX Skader og forgiftninger", "T": "XIX Skader og forgiftninger",
    "V": "XX Ytre årsaker", "W": "XX Ytre årsaker", "X": "XX Ytre årsaker",
    "Y": "XX Ytre årsaker", "Z": "XXI Kontakt med helsetjenesten",
    "U": "XXII Koder for spesielle formål",
}


def build_reference_codebooks() -> dict:
    """Return derived lookups: {'fylke', 'icd10_kapittel', 'kommune_crosswalk'}."""
    fylke = pd.DataFrame(
        {"fylke_nr": list(_FYLKE_NAVN.keys()), "fylke_navn": list(_FYLKE_NAVN.values())}
    ).drop_duplicates("fylke_nr").sort_values("fylke_nr").reset_index(drop=True)

    icd = pd.DataFrame(
        {"icd_bokstav": list(_ICD10_KAPITTEL.keys()),
         "kapittel": list(_ICD10_KAPITTEL.values())}
    )

    # kommune reform crosswalk from build_kommune_eras (pre2020 -> 2020 -> 2024).
    rows = []
    try:
        import build_kommune_eras as bke
        triples = bke.parse_recode_table(bke.RECODE_2019_TO_2020)
        map2024 = bke.MAP_2020_TO_2024
        seen = set()
        for pre, post2020, label in triples:
            post2024 = map2024.get(post2020, post2020)
            key = (pre, post2020, post2024)
            if key in seen:
                continue
            seen.add(key)
            rows.append({"kommune_pre2020": pre, "kommune_2020": post2020,
                         "kommune_2024": post2024, "kommune_navn": label})
    except Exception:
        pass
    crosswalk = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["kommune_pre2020", "kommune_2020", "kommune_2024", "kommune_navn"])

    return {"fylke": fylke, "icd10_kapittel": icd, "kommune_crosswalk": crosswalk}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def build_core(
    engine: MockDataEngine,
    years: Iterable[int] = DEFAULT_YEARS,
    constant_vars: Iterable[str] = CORE_CONSTANT,
    timevarying_vars: Iterable[str] = CORE_TIMEVARYING,
    on_skip=None,
) -> dict:
    """Build the F1 core tables and return {'person': df, 'person_year': df}."""
    person = build_person(engine, constant_vars, on_skip=on_skip)
    person_year = build_person_year(
        engine, person, timevarying_vars, years, on_skip=on_skip
    )
    return {"person": person, "person_year": person_year}


def build_all(
    engine: MockDataEngine,
    years: Iterable[int] = DEFAULT_YEARS,
    constant_vars: Iterable[str] = CORE_CONSTANT,
    timevarying_vars: Iterable[str] = CORE_TIMEVARYING,
    wide_person: bool = False,
    latent_structure: bool = True,
    dynamic_person_year: bool = False,
    dead_fraction: float = 0.0,
    entities: Iterable[str] = MULTI_RECORD_ENTITIES,
    include_npr: bool = True,
    include_trafikkulykke: bool = True,
    include_malepunkt: bool = True,
    include_kommune: bool = True,
    include_codebook: bool = True,
    on_skip=None,
    on_progress=None,
) -> dict:
    """Build the full relational set: person, person_year, entity tables, npr.

    `on_progress(table_name)` is called before each table starts (for logging).
    Returns an ordered dict of {table_name: DataFrame}. Foreign keys:
        person_year.unit_id              -> person.unit_id
        <entity>.<ref_col>               -> person.unit_id
        npr.unit_id                      -> person.unit_id
        person_i_trafikkulykke.TRAFULYK_PERS_FNR      -> person.unit_id
        person_i_trafikkulykke.TRAFULYK_PERS_TRAFULYK -> trafikkulykke.TRAFULYK_ID
    """
    tables: dict = {}

    if on_progress:
        on_progress("person")
    if wide_person:
        tables["person"] = build_person_wide(engine, latent_structure=latent_structure, on_skip=on_skip)
    else:
        tables["person"] = build_person(engine, constant_vars, on_skip=on_skip)
        if latent_structure:
            tables["person"] = apply_latent_structure(
                tables["person"], engine, ref_year=max(years))

    if on_progress:
        on_progress("person_year")
    life = None
    if dynamic_person_year:
        life = simulate_life_states(tables["person"], years)
        tables["person_year"] = build_person_year_dynamic(
            engine, tables["person"], years, life=life, on_skip=on_skip
        )
        # Keep the cross-sectional snapshot consistent with the panel's reference
        # year for the overlapping time-varying columns.
        ref = max(years)
        sl = tables["person_year"][tables["person_year"]["year"] == ref].set_index("unit_id")
        for c in ("INNTEKT_WLONN", "INNTEKT_WSAMINNT", "SKATT_NETTOFORMUE", "BOSATT_KOMMUNE"):
            if c in tables["person"].columns and c in sl.columns:
                tables["person"][c] = tables["person"]["unit_id"].map(sl[c]).values
    else:
        tables["person_year"] = build_person_year(
            engine, tables["person"], timevarying_vars, years, on_skip=on_skip
        )

    for ent in entities:
        if on_progress:
            on_progress(ent)
        if life is not None and ent == "jobb":
            tables[ent] = build_jobb_coupled(engine, tables["person"], life, on_skip=on_skip)
        elif life is not None and ent == "kjoretoy":
            tables[ent] = build_kjoretoy_temporal(engine, tables["person"], life, on_skip=on_skip)
        else:
            tables[ent] = build_entity_table(engine, ent, on_skip=on_skip)

    if include_npr:
        if on_progress:
            on_progress("npr")
        tables["npr"] = build_npr_table(engine, on_skip=on_skip)

    if include_trafikkulykke:
        if on_progress:
            on_progress("trafikkulykke")
        tables.update(build_trafikkulykke(engine, tables["person"], years=years, on_skip=on_skip))

    if include_malepunkt:
        if on_progress:
            on_progress("malepunkt")
        tables["malepunkt"] = build_malepunkt(engine, tables["person"], on_skip=on_skip)

    if include_kommune:
        if on_progress:
            on_progress("kommune")
        tables.update(build_kommune(engine, tables["person_year"], years=years, on_skip=on_skip))

    # Mortality / register scope: fix death dates and (optionally) add a
    # deceased stock so `import kjonn` returns everyone and you filter to alive.
    if life is not None:
        if on_progress:
            on_progress("mortality")
        person = tables["person"]
        if "BEFOLKNING_DOEDS_DATO" in person.columns:
            person["BEFOLKNING_DOEDS_DATO"] = living_death_dates(life)
        if dead_fraction and 0.0 < dead_fraction < 0.95:
            n_living = len(person)
            n_dead = int(round(n_living * dead_fraction / (1.0 - dead_fraction)))
            dead = build_deceased_stock(person.columns, n_dead, n_living, life["years"])
            tables["person"] = pd.concat([person, dead], ignore_index=True)

    if include_codebook:
        if on_progress:
            on_progress("codebook")
        tables.update(build_codebook(engine))
        tables.update(build_reference_codebooks())

    return tables


# ---------------------------------------------------------------------------
# microdata-faithful dtype normalisation (codes as strings, numbers downcast)
#
# microdata.no stores alfanumeriske variables as STRING codes with leading zeros
# (kommune '0301', kjonn '1', invkat 'A'); only true numbers are numeric. We:
#   * coerce any column that has a codelist to its canonical string code
#     (restoring leading zeros via the codebook) — incl. kommune keys/refs, so
#     the kommune FK becomes a clean string join;
#   * downcast genuinely-numeric columns to the smallest int/float dtype.
# Identity/foreign-key columns (unit_id, *_FNR, *_PERSON, minted entity ids) are
# left as integers so cross-table joins keep working.
# ---------------------------------------------------------------------------

# Columns that are pseudonymised person ids or minted surrogate keys — keep int.
_ID_KEEP_INT = {
    "unit_id", "ARBEIDSFORHOLD_ID", "KJORETOY_ID", "NUDB_KURS_LOEPENR",
    "AGGRSHOPPID", "NPRID", "TRAFULYK_ID", "TRAFULYK_PERS_ID", "MALEPUNKT_ID",
    "year",
}


def _is_kommune_col(col: str) -> bool:
    cu = col.upper()
    return col == "kommune_nr" or cu.endswith("KOMMUNE") or cu.endswith("KOMMNR")


def _coerce_code_string(s: pd.Series, code_map: dict, pad: int = 0) -> pd.Series:
    def conv(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        if isinstance(v, str):
            vs = v.strip()
            try:
                iv = int(float(vs))
            except ValueError:
                return vs            # genuine alpha code (e.g. 'FAM', 'A')
        else:
            try:
                iv = int(v)
            except (TypeError, ValueError):
                return str(v)
        if code_map and iv in code_map:
            return code_map[iv]      # canonical code with leading zeros
        if pad and iv >= 0:
            return str(iv).zfill(pad)
        return str(iv)
    return s.map(conv).astype("object")


def _downcast_numeric(s: pd.Series) -> pd.Series:
    if s.isna().any():
        nn = s.dropna()
        if len(nn) and (nn % 1 == 0).all():
            mx = nn.abs().max()
            dt = "Int16" if mx < 32767 else ("Int32" if mx < 2_147_483_647 else "Int64")
            return s.astype(dt)
        return pd.to_numeric(s, downcast="float")
    if pd.api.types.is_integer_dtype(s) or (s % 1 == 0).all():
        return pd.to_numeric(s, downcast="integer")
    return pd.to_numeric(s, downcast="float")


def normalize_for_microdata(tables: dict, engine: MockDataEngine) -> dict:
    """Return tables with codes as canonical strings and numbers downcast."""
    cb = build_codebook(engine)
    vl, vinfo = cb["value_labels"], cb["variables"]
    code_map: dict = {}
    for var, grp in vl.groupby("variable"):
        code_map[var] = {int(c): str(s) for c, s in zip(grp["code_num"], grp["code"]) if pd.notna(c)}
    coded = set(vinfo.loc[vinfo["n_labels"] > 0, "name"])
    komm_map = code_map.get("BOSATT_KOMMUNE", {})

    out: dict = {}
    for name, df in tables.items():
        df = df.copy()
        for col in df.columns:
            if col in _ID_KEEP_INT or col.endswith("_FNR") or col.endswith("_PERSON"):
                continue
            if _is_kommune_col(col):
                df[col] = _coerce_code_string(df[col], komm_map, pad=4)
            elif col in coded:
                df[col] = _coerce_code_string(df[col], code_map.get(col, {}), pad=0)
            elif pd.api.types.is_numeric_dtype(df[col]):
                df[col] = _downcast_numeric(df[col])
        out[name] = df
    return out


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def df_to_parquet_bytes(df: pd.DataFrame) -> bytes:
    """Serialise a DataFrame to Parquet bytes (requires pyarrow)."""
    import io

    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    return buf.getvalue()


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Serialise a DataFrame to UTF-8 CSV bytes."""
    return df.to_csv(index=False).encode("utf-8")


def summarize(df: pd.DataFrame) -> str:
    """Compact text summary (shape + numeric describe) for verification."""
    lines = [f"rows={len(df)}, cols={len(df.columns)}", f"columns: {list(df.columns)}"]
    num = df.select_dtypes(include="number")
    if len(num.columns):
        lines.append(num.describe().round(2).to_string())
    return "\n".join(lines)
