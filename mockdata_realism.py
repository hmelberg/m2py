"""
mockdata_realism.py — four-layer realism framework for synthetic data generation.

This module applies a declarative `realism` block (attached to a variable in
variable_metadata.json) to produce realistic synthetic values. It supports
numeric targets (lognormal wages, wealth, etc.) and categorical targets
(housing, municipality, etc.) through a single layered vocabulary:

    Layer 1 — hard_rules:   absolute constraints (set/multiply/cap/force_code/...)
    Layer 2 — effects:      verbs with default magnitudes, or explicit percentages
    Layer 3 — stratified:   explicit per-cell distributions
    Layer 4 — by_date /
              trend:        date-keyed regime changes and continuous drift

See the plan file (temporal-sleeping-flamingo.md) for full semantics.

Entry points (called from m2py.py):

    generate_numeric(realism, context_df, as_of, rng)     -> np.ndarray
    generate_categorical(realism, context_df, as_of, rng) -> np.ndarray

Pyodide note: stdlib + numpy + pandas only. No new external dependencies.
"""

from __future__ import annotations

import re
import math
from typing import Any, Optional, Union

import numpy as np
import pandas as pd

from mockdata_core import (
    _DEMO_REF_YEAR,
    latent_z,
    latent_z_vec,
    unit_seed,
    map_nus2000_to_level,
    EDUCATION_LEVEL_RANK,
    synth_education_vec,
)


# ---------------------------------------------------------------------------
# Verb library
# ---------------------------------------------------------------------------
#
# Each entry describes a verb's kind and its default magnitude. The magnitude
# is expressed as a fractional change (0.25 == +25%) applied per one-step
# driver increment (continuous driver: per std; ordinal categorical: per rank).
#
# For parametric verbs like "peak_at_45_60" or "zero_above_70", the parameters
# are parsed from the verb string at resolve time — they are NOT in this dict.

VERB_LIBRARY: dict[str, dict[str, Any]] = {
    # monotone verbs (both numeric and categorical targets)
    "weakly_increases":    {"kind": "monotone", "magnitude": +0.10},
    "increases":           {"kind": "monotone", "magnitude": +0.25},
    "strongly_increases":  {"kind": "monotone", "magnitude": +0.60},
    "weakly_decreases":    {"kind": "monotone", "magnitude": -0.10},
    "decreases":           {"kind": "monotone", "magnitude": -0.25},
    "strongly_decreases":  {"kind": "monotone", "magnitude": -0.50},
    "flat":                {"kind": "monotone", "magnitude": 0.0},

    # gender-specific (driver is KJOENN with codes 1=male, 2=female)
    "male_higher":            {"kind": "gender", "values": {1: +0.20, 2: -0.17}},
    "male_slightly_higher":   {"kind": "gender", "values": {1: +0.08, 2: -0.07}},
    "female_higher":          {"kind": "gender", "values": {1: -0.17, 2: +0.20}},
    "female_slightly_higher": {"kind": "gender", "values": {1: -0.07, 2: +0.08}},
    "gender_equal":           {"kind": "gender", "values": {1: 0.0, 2: 0.0}},

    # categorical target support — target code tracks driver level
    "co_moves_with":       {"kind": "monotone", "magnitude": +0.25},
    "anti_moves_with":     {"kind": "monotone", "magnitude": -0.25},
}

# Parametric verb patterns handled at parse time.
_PEAK_RE = re.compile(r"^peak_at_(\d+)_(\d+)$")
_USHAPE_RE = re.compile(r"^u_shaped(?:_(\d+)_(\d+))?$")
_ZERO_BELOW_RE = re.compile(r"^zero_below_(\d+)$")
_ZERO_ABOVE_RE = re.compile(r"^zero_above_(\d+)$")
_ZERO_OUTSIDE_RE = re.compile(r"^zero_outside_(\d+)_(\d+)$")
_ONLY_FOR_RE = re.compile(r"^only_for_(.+)$")
_PCT_RE = re.compile(r"^([+-]?\d+(?:\.\d+)?)%$")


# ---------------------------------------------------------------------------
# Magnitude / verb spec resolution
# ---------------------------------------------------------------------------

def resolve_magnitude(spec: Any) -> dict:
    """Normalise a verb/magnitude specification into a canonical effect dict.

    Accepted forms:
        "strongly_increases"                -> verb with default magnitude
        "+15%", "-50%"                      -> implicit monotone verb
        {"verb": "increases"}               -> verb with default magnitude
        {"verb": "increases", "by": "+20%"} -> verb with overridden magnitude
        "peak_at_45_60"                     -> parametric verb
        "zero_above_70"                     -> parametric verb
        0.25                                -> raw fractional magnitude (monotone)

    Returns a dict with shape:
        {"kind": "monotone" | "peak" | "u_shaped" | "hard_zero" | "gender" |
                 "mask" | "flat",
         "magnitude": float  (for monotone/co_moves/anti_moves),
         "peak_range": (lo, hi)  (for peak/u_shaped),
         "zero_range": (lo, hi)  (for hard_zero; values outside the range),
         "values": {code: delta}  (for gender),
         "mask_value": str  (for only_for_X)}
    """
    if spec is None:
        return {"kind": "flat", "magnitude": 0.0}

    # Numeric literal → raw monotone magnitude
    if isinstance(spec, (int, float)) and not isinstance(spec, bool):
        return {"kind": "monotone", "magnitude": float(spec)}

    # String form
    if isinstance(spec, str):
        return _resolve_string_spec(spec)

    # Dict form
    if isinstance(spec, dict):
        return _resolve_dict_spec(spec)

    raise ValueError(f"Cannot resolve verb/magnitude spec: {spec!r}")


def _resolve_string_spec(s: str) -> dict:
    s = s.strip()

    # "+15%" / "-50%"
    m = _PCT_RE.match(s)
    if m:
        return {"kind": "monotone", "magnitude": float(m.group(1)) / 100.0}

    # Named verb in the static library
    if s in VERB_LIBRARY:
        entry = VERB_LIBRARY[s]
        return dict(entry)  # copy so callers can mutate freely

    # Parametric verbs
    m = _PEAK_RE.match(s)
    if m:
        return {"kind": "peak", "peak_range": (int(m.group(1)), int(m.group(2)))}

    m = _USHAPE_RE.match(s)
    if m:
        if m.group(1) and m.group(2):
            return {"kind": "u_shaped", "peak_range": (int(m.group(1)), int(m.group(2)))}
        return {"kind": "u_shaped", "peak_range": None}

    m = _ZERO_BELOW_RE.match(s)
    if m:
        return {"kind": "hard_zero", "zero_range": (-math.inf, int(m.group(1)) - 1)}

    m = _ZERO_ABOVE_RE.match(s)
    if m:
        return {"kind": "hard_zero", "zero_range": (int(m.group(1)) + 1, math.inf)}

    m = _ZERO_OUTSIDE_RE.match(s)
    if m:
        return {"kind": "hard_zero_outside", "keep_range": (int(m.group(1)), int(m.group(2)))}

    m = _ONLY_FOR_RE.match(s)
    if m:
        return {"kind": "mask", "mask_value": m.group(1)}

    raise ValueError(f"Unknown verb: {s!r}")


def _resolve_dict_spec(d: dict) -> dict:
    # Form: {"verb": "increases", "by": "+20%", ...extra params...}
    if "verb" in d:
        base = _resolve_string_spec(d["verb"])
        if "by" in d and d["by"] is not None:
            override = resolve_magnitude(d["by"])
            if "magnitude" in override:
                base["magnitude"] = override["magnitude"]
        # Carry forward optional anchors (used by numeric target composition)
        for key in ("anchor_low", "anchor_high", "driver"):
            if key in d:
                base[key] = d[key]
        return base

    # Form: {"male": "+8%", "female": "-6%"}  — direct gender dict
    if "male" in d or "female" in d:
        values = {}
        if "male" in d:
            values[1] = resolve_magnitude(d["male"]).get("magnitude", 0.0)
        if "female" in d:
            values[2] = resolve_magnitude(d["female"]).get("magnitude", 0.0)
        return {"kind": "gender", "values": values}

    # Form: {"on_codes": {"1": "+40%", ...}}  — categorical-target per-code effect
    if "on_codes" in d:
        on_codes = {}
        for code, v in d["on_codes"].items():
            on_codes[str(code)] = resolve_magnitude(v)
        return {"kind": "on_codes", "on_codes": on_codes}

    # Form: {"when_low": {...}, "when_high": {...}}  — categorical-driver dispatch
    when_keys = [k for k in d.keys() if k.startswith("when_")]
    if when_keys:
        branches = {k[len("when_"):]: resolve_magnitude(d[k]) for k in when_keys}
        return {"kind": "when_branches", "branches": branches}

    raise ValueError(f"Cannot resolve dict verb/magnitude spec: {d!r}")


# ---------------------------------------------------------------------------
# Layer 4a — by_date regime selection
# ---------------------------------------------------------------------------

def _parse_date_to_year(s: Any) -> int:
    """Accept '2020-01-01' or 2020 or '2020' → int year."""
    if s is None:
        return _DEMO_REF_YEAR
    if isinstance(s, (int, np.integer)):
        return int(s)
    if isinstance(s, str):
        s = s.strip()
        if len(s) >= 4:
            try:
                return int(s[:4])
            except ValueError:
                pass
    raise ValueError(f"Cannot parse as_of date: {s!r}")


def resolve_active_regime(realism: dict, as_of: Any) -> Optional[dict]:
    """Return the first by_date window whose [from, to] contains as_of, else None.

    Windows may omit `from` (interpreted as -inf) or `to` (interpreted as +inf).
    If `by_date` is not present in the realism block, returns None.
    """
    windows = realism.get("by_date")
    if not windows:
        return None
    year = _parse_date_to_year(as_of)
    for w in windows:
        lo = _parse_date_to_year(w["from"]) if "from" in w and w["from"] is not None else -10**9
        hi = _parse_date_to_year(w["to"]) if "to" in w and w["to"] is not None else 10**9
        if lo <= year <= hi:
            return w
    return None


# ---------------------------------------------------------------------------
# Layer 4b — trend application
# ---------------------------------------------------------------------------

def _trend_annual_rate(trend_entry: dict) -> float:
    """Parse '+3%' or 0.03 from a trend entry's `annual_change` into a float."""
    v = trend_entry.get("annual_change")
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = _PCT_RE.match(v.strip())
        if m:
            return float(m.group(1)) / 100.0
    raise ValueError(f"Cannot parse trend annual_change: {v!r}")


def apply_trend_to_log_mean(log_mean: float, realism: dict, as_of: Any) -> float:
    """Shift a log-mean by the cumulative trend drift from reference year to as_of.

    Handles both the single-entry form:
        "trend": {"annual_change": "+3%", "reference_year": 2025}
    and the piecewise-list form:
        "trend": [{"from": 2010, "to": 2019, "annual_change": "+2%"}, ...]
    """
    trend = realism.get("trend")
    if not trend:
        return log_mean

    year = _parse_date_to_year(as_of)

    # Single entry
    if isinstance(trend, dict):
        rate = _trend_annual_rate(trend)
        ref_year = int(trend.get("reference_year", _DEMO_REF_YEAR))
        return log_mean + math.log(1.0 + rate) * (year - ref_year)

    # Piecewise list: integrate annual growth across windows up to `year`
    if isinstance(trend, list):
        # Choose a reference: use the first window's `from` as the anchor (value=1.0 there).
        # Integrate log-growth across each window until we reach `year`.
        drift = 0.0
        for w in trend:
            lo = int(w.get("from", -10**9))
            hi = int(w.get("to", 10**9))
            rate = _trend_annual_rate(w)
            if year <= lo:
                break
            span = min(year, hi) - lo
            if span > 0:
                drift += math.log(1.0 + rate) * span
        return log_mean + drift

    return log_mean


# ---------------------------------------------------------------------------
# Driver resolution (education, age, gender, latent_z, ...)
# ---------------------------------------------------------------------------

CANONICAL_DRIVERS = frozenset({"age", "gender", "education", "education_level", "latent_z"})


def _unit_ids_of(context_df: pd.DataFrame) -> np.ndarray:
    """Extract unit_id column, or synthesise 1..n when missing."""
    if "unit_id" in context_df.columns:
        return context_df["unit_id"].values
    return np.arange(1, len(context_df) + 1, dtype=np.int64)


def _ages_from_column_values(
    context_df: pd.DataFrame, col_name: str, as_of_year: int
) -> Optional[np.ndarray]:
    """Return age-in-years array from `col_name`, or None if values don't look
    like age or birth-year data. Auto-detects format:
      - values in [0, 120]         -> treat as age-in-years directly
      - values in [100000, 999912] -> treat as YYYYMM birth year
    """
    col = pd.to_numeric(context_df[col_name], errors="coerce")
    nn = col.dropna()
    if len(nn) == 0:
        return None
    vmin, vmax = float(nn.min()), float(nn.max())
    if 0 <= vmin and vmax <= 120:
        return col.fillna(44).clip(0, 110).astype(float).values
    if 100000 <= vmin and vmax <= 999912:
        bym = col.fillna(198505).astype(np.int64)
        return (as_of_year - (bym // 100)).clip(0, 110).astype(float).values
    return None


def _gender_from_column_values(
    context_df: pd.DataFrame, col_name: str
) -> Optional[np.ndarray]:
    """Return gender int array (1=male, 2=female) from `col_name`, or None
    if values don't look like gender data. Auto-detects format:
      - integer values all in {1, 2} -> returned directly
      - integer values all in {0, 1} -> mapped (0->2, 1->1)
      - string values M/Mann/Male -> 1, K/F/Kvinne/Female -> 2
    """
    raw = context_df[col_name]
    # Try numeric interpretation first
    num = pd.to_numeric(raw, errors="coerce")
    nn = num.dropna()
    if len(nn) > 0 and len(nn) == len(raw.dropna()):
        uniq = set(int(v) for v in nn.unique())
        if uniq.issubset({1, 2}):
            return num.fillna(1).astype(int).values
        if uniq.issubset({0, 1}):
            return np.where(num.fillna(1).astype(int) == 1, 1, 2)
        return None
    # Try string interpretation
    male_tokens = {"m", "mann", "male", "man", "h"}  # h=hann (Norwegian)
    female_tokens = {"k", "f", "kvinne", "female", "woman", "w"}
    out = np.empty(len(raw), dtype=int)
    ok = 0
    for i, v in enumerate(raw.values):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            out[i] = 1
            continue
        s = str(v).strip().lower()
        if s in male_tokens:
            out[i] = 1
            ok += 1
        elif s in female_tokens:
            out[i] = 2
            ok += 1
        else:
            return None
    if ok == 0:
        return None
    return out


def _education_level_from_column_values(
    context_df: pd.DataFrame, col_name: str
) -> Optional[np.ndarray]:
    """Return education-level string array ('low'/'medium'/'high') from
    `col_name`, or None if values don't look like education data.
    Auto-detects:
      - strings already in {low, medium, high} (case-insensitive)
      - NUS2000 codes (strings/ints) -> mapped via map_nus2000_to_level
    """
    raw = context_df[col_name]
    nonnull = [v for v in raw.values if not (v is None or (isinstance(v, float) and pd.isna(v)))]
    if len(nonnull) == 0:
        return None
    level_set = {"low", "medium", "high"}
    first = str(nonnull[0]).strip().lower()
    # Case 1: already-mapped level strings
    if first in level_set:
        all_levels = all(str(v).strip().lower() in level_set
                         for v in nonnull)
        if all_levels:
            return np.array(
                [str(v).strip().lower() if not (v is None or (isinstance(v, float) and pd.isna(v)))
                 else "medium" for v in raw.values],
                dtype=object,
            )
        return None
    # Case 2: NUS2000 codes — first char must be a digit for every non-null row
    all_digit_leading = all(str(v).strip()[:1].isdigit() for v in nonnull)
    if not all_digit_leading:
        return None
    return np.array([map_nus2000_to_level(c) for c in raw.values], dtype=object)


def resolve_driver_vector(
    driver_name: str,
    context_df: pd.DataFrame,
    as_of: Any = None,
) -> np.ndarray:
    """Return a per-row driver vector for `driver_name`, synthesising when missing.

    Recognised canonical names:
        "age"              -> from BEFOLKNING_FOEDSELS_AAR_MND or synthetic
        "gender"           -> from BEFOLKNING_KJOENN or synthetic (1/2)
        "education" /
        "education_level"  -> from NUDB_BU or synthetic ("low"/"medium"/"high")
        "latent_z"         -> deterministic N(0,1) from unit_id

    Any other name is looked up as a column in `context_df`.
    """
    n = len(context_df)
    if n == 0:
        return np.array([])

    unit_ids = _unit_ids_of(context_df)
    as_of_year = _parse_date_to_year(as_of) if as_of is not None else _DEMO_REF_YEAR
    name = driver_name.lower() if isinstance(driver_name, str) else driver_name

    if name == "age":
        # 1) Canonical birth-year column
        if "BEFOLKNING_FOEDSELS_AAR_MND" in context_df.columns:
            ages = _ages_from_column_values(
                context_df, "BEFOLKNING_FOEDSELS_AAR_MND", as_of_year
            )
            if ages is not None:
                return ages
        # 2) Common alias names (case-insensitive). Covers user imports like
        #    `import db/BEFOLKNING_FOEDSELS_AAR_MND as alder` and derived
        #    age-in-years columns from `replace`/`generate`.
        lower_cols = {c.lower(): c for c in context_df.columns}
        for candidate in ("alder", "age", "arbeidssoker_alder"):
            if candidate in lower_cols:
                ages = _ages_from_column_values(
                    context_df, lower_cols[candidate], as_of_year
                )
                if ages is not None:
                    return ages
        # 3) Synthetic: N(44, 14) clipped to working-age 18..67
        out = np.empty(n, dtype=float)
        for i, uid in enumerate(unit_ids):
            r = np.random.default_rng(unit_seed(uid, "alder"))
            a = int(round(r.normal(44.0, 14.0)))
            out[i] = max(18, min(67, a))
        return out

    if name == "gender":
        # 1) Canonical column
        if "BEFOLKNING_KJOENN" in context_df.columns:
            g = _gender_from_column_values(context_df, "BEFOLKNING_KJOENN")
            if g is not None:
                return g
        # 2) Common alias names (case-insensitive)
        lower_cols = {c.lower(): c for c in context_df.columns}
        for candidate in ("kjonn", "kjoenn", "gender", "sex", "arbeidssoker_kjoenn"):
            if candidate in lower_cols:
                g = _gender_from_column_values(context_df, lower_cols[candidate])
                if g is not None:
                    return g
        # 3) Synthetic: 51% male (mirrors m2py._norway_synth_kjonn_from_uid)
        out = np.empty(n, dtype=int)
        for i, uid in enumerate(unit_ids):
            r = np.random.default_rng(unit_seed(uid, "kjonn"))
            out[i] = 1 if r.random() < 0.51 else 2
        return out

    if name in ("education", "education_level"):
        # 1) Canonical column
        if "NUDB_BU" in context_df.columns:
            ed = _education_level_from_column_values(context_df, "NUDB_BU")
            if ed is not None:
                return ed
        # 2) Common alias names (case-insensitive)
        lower_cols = {c.lower(): c for c in context_df.columns}
        for candidate in ("utdanning", "utdanningsniva", "utdanningsnivå",
                          "education", "education_level", "nudb_bu_level"):
            if candidate in lower_cols:
                ed = _education_level_from_column_values(context_df, lower_cols[candidate])
                if ed is not None:
                    return ed
        # 3) Synthetic: age-cohort-conditional prior (reuse age resolver so it
        #    benefits from alias detection on age/alder columns).
        ages = resolve_driver_vector("age", context_df, as_of).astype(int)
        return synth_education_vec(unit_ids, ages=ages, as_of_year=as_of_year)

    if name == "latent_z":
        return latent_z_vec(unit_ids)

    # Not a canonical driver — look up as a column directly.
    if driver_name in context_df.columns:
        return context_df[driver_name].values

    raise KeyError(
        f"Unknown driver {driver_name!r}: not in context_df columns "
        f"({list(context_df.columns)}) and not a recognised synthetic driver."
    )


# ---------------------------------------------------------------------------
# Condition matching (used by hard_rules and stratified lookups)
# ---------------------------------------------------------------------------

def _loose_equal(value: Any, expected: Any) -> bool:
    """Equality tolerant of int/float/str mismatches (e.g. '1' == 1)."""
    if value is None:
        return expected is None
    try:
        if isinstance(expected, bool):
            return bool(value) == expected
        if isinstance(expected, (int, float, np.integer, np.floating)):
            return float(value) == float(expected)
    except (TypeError, ValueError):
        pass
    try:
        return str(value).strip() == str(expected).strip()
    except Exception:
        return False


def _match_when(when: dict, context_df: pd.DataFrame, as_of: Any = None) -> np.ndarray:
    """Return a boolean mask of rows where ALL conditions in `when` hold.

    Each condition value can be:
        [lo, hi]       -> numeric range match, inclusive
        scalar         -> equality match (loose int/str comparison)
    """
    n = len(context_df)
    mask = np.ones(n, dtype=bool)
    for key, expected in (when or {}).items():
        try:
            driver_vals = resolve_driver_vector(key, context_df, as_of) if key in CANONICAL_DRIVERS \
                          else (context_df[key].values if key in context_df.columns
                                else resolve_driver_vector(key, context_df, as_of))
        except KeyError:
            # Missing driver → no rows match
            return np.zeros(n, dtype=bool)

        if isinstance(expected, list) and len(expected) == 2 and not isinstance(expected[0], str):
            lo, hi = expected
            numeric = pd.to_numeric(pd.Series(driver_vals), errors="coerce")
            cond = (numeric >= lo) & (numeric <= hi)
            mask &= np.asarray(cond.fillna(False))
        else:
            mask &= np.array([_loose_equal(v, expected) for v in driver_vals], dtype=bool)
    return mask


# ---------------------------------------------------------------------------
# Layer 1 — hard rules
# ---------------------------------------------------------------------------

def apply_hard_rules_numeric(
    values: np.ndarray,
    hard_rules: list,
    context_df: pd.DataFrame,
    as_of: Any = None,
    rng: Optional[np.random.Generator] = None,
) -> np.ndarray:
    """Apply numeric hard_rules in order.

    Supported operators: `set`, `multiply_by`, `add`, `cap_at`, `floor_at`.
    Each rule has a `when` dict of conditions; omitted `when` matches all rows.
    Later rules override earlier rules on overlapping rows.

    Optional `probability` field (float in [0, 1]) restricts the rule to a
    random Bernoulli-sampled subset of matched rows. Used e.g. to model that
    only a fraction of young adults have zero wage income.
    """
    out = np.asarray(values, dtype=float).copy()
    for rule in hard_rules or []:
        when = rule.get("when") or {}
        mask = _match_when(when, context_df, as_of) if when else np.ones(len(out), dtype=bool)
        if not mask.any():
            continue
        if "probability" in rule:
            p = float(rule["probability"])
            if p <= 0.0:
                continue
            if p < 1.0:
                if rng is None:
                    rng = np.random.default_rng()
                coin = rng.random(len(out)) < p
                mask = mask & coin
                if not mask.any():
                    continue
        if "set" in rule:
            val = rule["set"]
            out[mask] = float('nan') if val is None else float(val)
        elif "multiply_by" in rule:
            out[mask] = out[mask] * float(rule["multiply_by"])
        elif "add" in rule:
            out[mask] = out[mask] + float(rule["add"])
        elif "cap_at" in rule:
            out[mask] = np.minimum(out[mask], float(rule["cap_at"]))
        elif "floor_at" in rule:
            out[mask] = np.maximum(out[mask], float(rule["floor_at"]))
    return out


def apply_hard_rules_categorical(
    codes: np.ndarray,
    hard_rules: list,
    context_df: pd.DataFrame,
    base_dist: Optional[dict] = None,
    rng: Optional[np.random.Generator] = None,
    as_of: Any = None,
) -> np.ndarray:
    """Apply categorical hard_rules in order.

    Supported operators:
        `force_code`:    overwrite matched rows with the given code
        `exclude_codes`: rows matching `when` AND currently holding an excluded
                         code are resampled from the complement of `base_dist`
        `only_codes`:    rows matching `when` AND currently holding a code
                         outside `only_codes` are resampled from the
                         intersection of `only_codes` and `base_dist`

    `base_dist` is the distribution currently active for this import (after
    layer 4a regime selection); it's used to weight the resampling. If
    unavailable, resampling falls back to uniform over the valid set.
    """
    out = np.asarray(codes, dtype=object).copy()
    if rng is None:
        rng = np.random.default_rng()

    for rule in hard_rules or []:
        when = rule.get("when") or {}
        mask = _match_when(when, context_df, as_of) if when else np.ones(len(out), dtype=bool)
        if not mask.any():
            continue

        if "force_code" in rule:
            out[mask] = str(rule["force_code"])

        elif "exclude_codes" in rule:
            excluded = {str(c) for c in rule["exclude_codes"]}
            bad = mask & np.array([str(c) in excluded for c in out], dtype=bool)
            if bad.any():
                alts = {str(k): float(v) for k, v in (base_dist or {}).items() if str(k) not in excluded}
                out[bad] = _sample_from_dist(alts, int(bad.sum()), rng)

        elif "only_codes" in rule:
            allowed = {str(c) for c in rule["only_codes"]}
            bad = mask & np.array([str(c) not in allowed for c in out], dtype=bool)
            if bad.any():
                alts = {str(k): float(v) for k, v in (base_dist or {}).items() if str(k) in allowed}
                if not alts and allowed:
                    # base_dist doesn't cover allowed set → uniform over allowed
                    alts = {c: 1.0 for c in allowed}
                out[bad] = _sample_from_dist(alts, int(bad.sum()), rng)
    return out


def _sample_from_dist(dist: dict, n: int, rng: np.random.Generator) -> np.ndarray:
    """Draw n codes from a {code: weight} dict (weights need not be normalised)."""
    if not dist or n <= 0:
        return np.array([], dtype=object)
    keys = list(dist.keys())
    weights = np.array([dist[k] for k in keys], dtype=float)
    total = weights.sum()
    if total <= 0:
        return np.array([keys[0]] * n, dtype=object)
    probs = weights / total
    return rng.choice(keys, size=n, p=probs).astype(object)


# ---------------------------------------------------------------------------
# Layer 3 — stratified table lookup
# ---------------------------------------------------------------------------

def _parse_bracket(token: str):
    """Parse 'X-Y' into (int, int); returns None if not a bracket token."""
    if not isinstance(token, str) or "-" not in token:
        return None
    try:
        lo_s, hi_s = token.split("-", 1)
        return (int(lo_s), int(hi_s))
    except ValueError:
        return None


def _bracket_containing(value: Any, brackets: dict) -> Optional[str]:
    """Find the bracket token whose range contains `value`."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    for token, (lo, hi) in brackets.items():
        if lo <= v <= hi:
            return token
    return None


def _bracket_base_driver(dim_name: str) -> str:
    """Strip the '_bracket' suffix from a dimension name."""
    if dim_name.endswith("_bracket"):
        return dim_name[: -len("_bracket")]
    return dim_name


def apply_stratified_lookup(
    stratified: dict,
    context_df: pd.DataFrame,
    as_of: Any = None,
) -> tuple:
    """For each row, look up the matching cell in `stratified.cells`.

    Returns (matched_mask, params_per_row): a boolean mask of length n_rows
    plus a list where matched rows hold the cell spec and unmatched rows hold
    None (to be filled by the verb layer or base distribution).

    Cell keys are 'token1|token2|...' in the order of `stratified.by`.
    Tokens matching 'X-Y' are treated as numeric ranges (for age_bracket etc.);
    all other tokens are exact-match (for gender, education_level, etc.).
    """
    by = stratified.get("by") or []
    cells = stratified.get("cells") or {}
    n = len(context_df)

    if not by or not cells:
        return np.zeros(n, dtype=bool), [None] * n

    # Collect tokens seen per dimension; decide bracket vs. exact per dimension.
    dim_tokens: list[set] = [set() for _ in by]
    for key in cells.keys():
        parts = key.split("|")
        if len(parts) != len(by):
            continue
        for i, p in enumerate(parts):
            dim_tokens[i].add(p)

    dim_brackets: list = []
    for tokens in dim_tokens:
        brackets = {}
        for t in tokens:
            br = _parse_bracket(t)
            if br is not None:
                brackets[t] = br
        dim_brackets.append(brackets if brackets else None)

    # Resolve driver vector per dimension (strip '_bracket' suffix if present).
    driver_vecs = []
    for dim_name in by:
        base = _bracket_base_driver(dim_name)
        driver_vecs.append(resolve_driver_vector(base, context_df, as_of))

    mask = np.zeros(n, dtype=bool)
    params: list = [None] * n

    for i in range(n):
        tokens = []
        ok = True
        for dim_idx in range(len(by)):
            val = driver_vecs[dim_idx][i]
            brackets = dim_brackets[dim_idx]
            if brackets is not None:
                tok = _bracket_containing(val, brackets)
                if tok is None:
                    ok = False
                    break
                tokens.append(tok)
            else:
                tokens.append(str(val).strip())
        if not ok:
            continue
        key = "|".join(tokens)
        if key in cells:
            mask[i] = True
            params[i] = cells[key]

    return mask, params


# ---------------------------------------------------------------------------
# Layer 2 — verb effects composition
# ---------------------------------------------------------------------------

# Standardisation stats for continuous drivers. Used by monotone verbs so that
# "+25% per step" means "per one standard deviation of the driver".
_DRIVER_STATS = {
    "age": (44.0, 14.0),      # matches m2py synth-age: N(44, 14)
    "latent_z": (0.0, 1.0),
}

# Ordinal rank maps. Drivers in this dict use the rank (centred at midpoint)
# as the number of driver-steps for monotone verbs.
_ORDINAL_DRIVERS = {
    "education": EDUCATION_LEVEL_RANK,
    "education_level": EDUCATION_LEVEL_RANK,
}


def _driver_steps_monotone(driver_name: str, driver_vec: np.ndarray) -> np.ndarray:
    """Convert a driver vector into 'steps from centre' for monotone verbs."""
    name = driver_name.lower() if isinstance(driver_name, str) else driver_name
    n = len(driver_vec)

    if name in _ORDINAL_DRIVERS:
        rank_map = _ORDINAL_DRIVERS[name]
        max_rank = max(rank_map.values())
        centre = max_rank / 2.0
        out = np.zeros(n, dtype=float)
        for i, v in enumerate(driver_vec):
            r = rank_map.get(str(v), centre)
            out[i] = r - centre
        return out

    if name in _DRIVER_STATS:
        mean, std = _DRIVER_STATS[name]
        vals = pd.to_numeric(pd.Series(driver_vec), errors="coerce").fillna(mean).values
        return (vals.astype(float) - mean) / std

    # Fallback: empirical z-score of the vector.
    vals = pd.to_numeric(pd.Series(driver_vec), errors="coerce").fillna(0.0).values.astype(float)
    mean = float(np.nanmean(vals)) if len(vals) else 0.0
    std = float(np.nanstd(vals)) or 1.0
    return (vals - mean) / std


def _log_shift_per_step(magnitude: float) -> float:
    """Convert a fractional magnitude (+0.25 = +25%) into an additive log shift."""
    m = float(magnitude)
    if m <= -0.99:
        return -10.0  # effectively zero
    return math.log(1.0 + m)


def _apply_monotone(driver_name: str, driver_vec: np.ndarray, magnitude: float) -> np.ndarray:
    steps = _driver_steps_monotone(driver_name, driver_vec)
    return steps * _log_shift_per_step(magnitude)


def _apply_anchored_ordinal(
    driver_name: str,
    driver_vec: np.ndarray,
    anchor_low: float,
    anchor_high: float,
) -> np.ndarray:
    """Linear interpolation on log-scale from anchor_low (lowest rank) to anchor_high."""
    name = driver_name.lower() if isinstance(driver_name, str) else driver_name
    if name not in _ORDINAL_DRIVERS:
        return np.zeros(len(driver_vec))
    rank_map = _ORDINAL_DRIVERS[name]
    max_rank = max(rank_map.values())
    log_low = math.log(float(anchor_low))
    log_high = math.log(float(anchor_high))
    centre_log = (log_low + log_high) / 2.0
    out = np.zeros(len(driver_vec), dtype=float)
    for i, v in enumerate(driver_vec):
        r = rank_map.get(str(v), max_rank / 2.0)
        raw = log_low + (log_high - log_low) * (r / max_rank)
        out[i] = raw - centre_log
    return out


def _apply_peak(driver_vec: np.ndarray, peak_range: tuple) -> np.ndarray:
    """Inverted-U: +log(2) at centre of [lo,hi], 0 at edges and beyond."""
    lo, hi = peak_range
    if hi <= lo:
        return np.zeros(len(driver_vec))
    centre = (lo + hi) / 2.0
    span = (hi - lo) / 2.0
    amplitude = math.log(2.0)
    vals = pd.to_numeric(pd.Series(driver_vec), errors="coerce").fillna(centre).values.astype(float)
    factor = 1.0 - ((vals - centre) / span) ** 2
    return amplitude * np.maximum(0.0, factor)


def _apply_gender_verb(driver_vec: np.ndarray, values: dict) -> np.ndarray:
    """Map gender codes (1, 2) to log-mean deltas via the verb's `values` dict."""
    out = np.zeros(len(driver_vec), dtype=float)
    for i, g in enumerate(driver_vec):
        try:
            key = int(g)
        except (TypeError, ValueError):
            key = 0
        out[i] = float(values.get(key, 0.0))
    return out


def _apply_verb_to_series(
    sub_eff: dict,
    driver_name: str,
    driver_vec: np.ndarray,
) -> np.ndarray:
    """Apply a single sub-effect to produce a per-row numeric log-shift."""
    kind = sub_eff.get("kind")
    if kind == "monotone":
        mag = sub_eff.get("magnitude", 0.0)
        return _apply_monotone(driver_name, driver_vec, mag)
    if kind == "peak":
        return _apply_peak(driver_vec, sub_eff["peak_range"])
    if kind == "u_shaped" and sub_eff.get("peak_range"):
        return -_apply_peak(driver_vec, sub_eff["peak_range"])
    if kind == "gender":
        return _apply_gender_verb(driver_vec, sub_eff.get("values", {}))
    if kind == "flat":
        return np.zeros(len(driver_vec))
    return np.zeros(len(driver_vec))


def apply_verb_effects_numeric(
    effects: dict,
    context_df: pd.DataFrame,
    as_of: Any = None,
) -> tuple:
    """Compose verb effects for a numeric target.

    Returns (log_shift, force_zero_mask):
        log_shift     -> per-row additive shift on log(target)
        force_zero_mask -> per-row mask of rows that must be set to zero
                           (from hard_zero / zero_below / zero_above / only_for verbs)
    """
    n = len(context_df)
    log_shift = np.zeros(n, dtype=float)
    force_zero = np.zeros(n, dtype=bool)

    for driver_name, spec in (effects or {}).items():
        try:
            eff = resolve_magnitude(spec)
        except ValueError:
            continue
        try:
            driver_vec = resolve_driver_vector(driver_name, context_df, as_of)
        except KeyError:
            continue

        kind = eff.get("kind")

        if kind == "monotone":
            anchor_low = eff.get("anchor_low")
            anchor_high = eff.get("anchor_high")
            name_l = driver_name.lower() if isinstance(driver_name, str) else driver_name
            if anchor_low is not None and anchor_high is not None and name_l in _ORDINAL_DRIVERS:
                log_shift += _apply_anchored_ordinal(driver_name, driver_vec, anchor_low, anchor_high)
            else:
                log_shift += _apply_monotone(driver_name, driver_vec, eff.get("magnitude", 0.0))

        elif kind == "peak":
            log_shift += _apply_peak(driver_vec, eff["peak_range"])

        elif kind == "u_shaped" and eff.get("peak_range"):
            log_shift -= _apply_peak(driver_vec, eff["peak_range"])

        elif kind == "gender":
            log_shift += _apply_gender_verb(driver_vec, eff.get("values", {}))

        elif kind == "hard_zero":
            lo, hi = eff["zero_range"]
            vals = pd.to_numeric(pd.Series(driver_vec), errors="coerce").fillna(0.0).values
            force_zero |= (vals >= lo) & (vals <= hi)

        elif kind == "hard_zero_outside":
            lo, hi = eff["keep_range"]
            vals = pd.to_numeric(pd.Series(driver_vec), errors="coerce").fillna(0.0).values
            force_zero |= (vals < lo) | (vals > hi)

        elif kind == "mask":
            target = str(eff.get("mask_value"))
            force_zero |= np.array([str(v).strip() != target for v in driver_vec], dtype=bool)

        # kind in ('flat', 'on_codes', 'when_branches') -> no effect on numeric targets

    return log_shift, force_zero


def apply_verb_effects_categorical(
    log_odds: np.ndarray,  # shape (n_codes, n_rows)
    codes: list,
    effects: dict,
    context_df: pd.DataFrame,
    as_of: Any = None,
) -> np.ndarray:
    """Accumulate verb-based log-odds shifts per (code, row) from each driver.

    Two effect shapes are supported per driver:
        "driver": {"on_codes": {code: <verb_spec>}}        per-code shift
        "driver": {"when_<branch>": {"on_codes": {...}}}   categorical dispatch
    """
    for driver_name, spec in (effects or {}).items():
        try:
            eff = resolve_magnitude(spec)
        except ValueError:
            continue
        try:
            driver_vec = resolve_driver_vector(driver_name, context_df, as_of)
        except KeyError:
            continue

        kind = eff.get("kind")

        if kind == "on_codes":
            on_codes = eff.get("on_codes") or {}
            for code_idx, code in enumerate(codes):
                sub_eff = on_codes.get(str(code))
                if sub_eff is None:
                    continue
                delta = _apply_verb_to_series(sub_eff, driver_name, driver_vec)
                log_odds[code_idx, :] += delta

        elif kind == "when_branches":
            branches = eff.get("branches") or {}
            for branch_key, sub_eff in branches.items():
                mask = np.array(
                    [str(v).strip().lower() == str(branch_key).strip().lower() for v in driver_vec],
                    dtype=bool,
                )
                if not mask.any():
                    continue
                if sub_eff.get("kind") == "on_codes":
                    sub_on_codes = sub_eff.get("on_codes") or {}
                    for code_idx, code in enumerate(codes):
                        cc_eff = sub_on_codes.get(str(code))
                        if cc_eff is None:
                            continue
                        if cc_eff.get("kind") == "monotone":
                            log_odds[code_idx, mask] += _log_shift_per_step(cc_eff.get("magnitude", 0.0))

        # Other kinds (monotone/peak/gender at top-level) would apply the same
        # verb to every code's log-odds, which is rarely what the author wants.
        # Left unimplemented for now — authors should use on_codes explicitly.

    return log_odds


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def _effective_base_numeric(realism: dict, regime: Optional[dict]) -> dict:
    """Merge regime-level overrides on top of the realism block's `base`."""
    base = dict(realism.get("base") or {})
    if regime:
        for key in ("mean", "sigma", "std", "lognormal", "normal"):
            if key in regime:
                base[key] = regime[key]
    return base


def generate_numeric(
    realism: dict,
    context_df: pd.DataFrame,
    as_of: Any = None,
    rng: Optional[np.random.Generator] = None,
) -> np.ndarray:
    """Generate numeric values for a variable with a `realism` spec.

    Pipeline:
        1. Resolve active by_date regime (layer 4a) -> effective base params
        2. Stratified cell lookup (layer 3) where matches exist
        3. Verb effects (layer 2) for unmatched rows
        4. Trend drift (layer 4b)
        5. Latent-z loading
        6. Sample
        7. Apply hard_zero/mask from verbs; apply hard_rules (layer 1)
        8. Cast to int / clip to [min, max] if specified
    """
    n = len(context_df)
    if n == 0:
        return np.array([])
    if rng is None:
        rng = np.random.default_rng()

    family = (realism.get("family") or "lognormal").lower()
    regime = resolve_active_regime(realism, as_of)
    base = _effective_base_numeric(realism, regime)

    base_mean = float(base.get("mean", 0.0))
    base_sigma = float(base.get("sigma", base.get("std", 1.0)))
    latent_coef = float(realism.get("latent_z_coefficient", 0.0) or 0.0)

    # Per-row log-mean and sigma; start from base and override from stratified cells.
    row_mean = np.full(n, base_mean, dtype=float)
    row_sigma = np.full(n, base_sigma, dtype=float)

    # Layer 3: stratified lookup
    if realism.get("stratified"):
        matched, cells = apply_stratified_lookup(realism["stratified"], context_df, as_of=as_of)
        for i in range(n):
            if matched[i] and cells[i] is not None:
                c = cells[i]
                if family == "lognormal" and "lognormal" in c:
                    row_mean[i] = float(c["lognormal"].get("mean", base_mean))
                    row_sigma[i] = float(c["lognormal"].get("sigma", base_sigma))
                elif family == "normal" and "normal" in c:
                    row_mean[i] = float(c["normal"].get("mean", base_mean))
                    row_sigma[i] = float(c["normal"].get("std", base_sigma))
                else:
                    if "mean" in c:
                        row_mean[i] = float(c["mean"])
                    if "sigma" in c:
                        row_sigma[i] = float(c["sigma"])
                    elif "std" in c:
                        row_sigma[i] = float(c["std"])
    else:
        matched = np.zeros(n, dtype=bool)

    # Layer 2: verb effects on unmatched rows
    log_shift = np.zeros(n, dtype=float)
    force_zero = np.zeros(n, dtype=bool)
    effects = realism.get("effects")
    if effects:
        shift, fzero = apply_verb_effects_numeric(effects, context_df, as_of=as_of)
        # Apply verb shifts only where no stratified cell took over
        unmatched = ~matched
        log_shift[unmatched] = shift[unmatched]
        force_zero |= fzero  # force_zero applies regardless of stratification

    row_mean = row_mean + log_shift

    # Layer 4b: trend drift (applies everywhere, including stratified cells)
    if realism.get("trend"):
        drift = apply_trend_to_log_mean(0.0, realism, as_of) if as_of is not None else 0.0
        row_mean = row_mean + drift

    # Latent-z loading
    if latent_coef != 0.0:
        z = resolve_driver_vector("latent_z", context_df, as_of=as_of)
        row_mean = row_mean + latent_coef * z

    # Sample
    eps = rng.standard_normal(n)
    raw = row_mean + row_sigma * eps
    if family == "lognormal":
        values = np.exp(raw)
    else:
        values = raw

    # Apply verb-level force_zero (hard_zero / mask verbs)
    if force_zero.any():
        values[force_zero] = 0.0

    # Layer 1: hard rules
    if realism.get("hard_rules"):
        values = apply_hard_rules_numeric(values, realism["hard_rules"], context_df, as_of=as_of, rng=rng)

    # Clipping first (preserves float dtype for arithmetic), then integer cast.
    lo = realism.get("min")
    hi = realism.get("max")
    if lo is not None:
        values = np.maximum(values, float(lo))
    if hi is not None:
        values = np.minimum(values, float(hi))

    if realism.get("as_int"):
        values = np.rint(values).astype(np.int64)
        if lo is not None:
            values = np.maximum(values, int(lo))

    return values


def _effective_base_distribution(realism: dict, regime: Optional[dict]) -> dict:
    """Return the distribution dict active for this import (regime overrides base)."""
    if regime and "distribution" in regime:
        return dict(regime["distribution"])
    base = realism.get("base") or {}
    if "distribution" in base:
        return dict(base["distribution"])
    return dict(realism.get("distribution") or {})


def generate_categorical(
    realism: dict,
    context_df: pd.DataFrame,
    as_of: Any = None,
    rng: Optional[np.random.Generator] = None,
) -> np.ndarray:
    """Generate categorical codes for a variable with a `realism` spec.

    Pipeline:
        1. Resolve active by_date regime (layer 4a) -> effective base distribution
        2. Stratified cell lookup (layer 3) where matches exist
        3. Verb effects (layer 2) accumulated as log-odds shifts per (code, row)
        4. Sample from softmax of accumulated log-odds
        5. Hard rules (layer 1) — force_code / exclude_codes / only_codes
    """
    n = len(context_df)
    if n == 0:
        return np.array([], dtype=object)
    if rng is None:
        rng = np.random.default_rng()

    regime = resolve_active_regime(realism, as_of)
    base_dist = _effective_base_distribution(realism, regime)
    if not base_dist:
        raise ValueError("generate_categorical: no base distribution found in realism spec")

    codes = list(base_dist.keys())
    n_codes = len(codes)

    # Per-row log-odds matrix, initialised to log(base_probs) broadcast across rows.
    probs = np.array([float(base_dist[c]) for c in codes], dtype=float)
    total = probs.sum()
    probs = probs / total if total > 0 else probs
    log_base = np.log(np.maximum(probs, 1e-12))
    log_odds = np.tile(log_base[:, None], (1, n)).astype(float)

    # Layer 3: stratified override
    if realism.get("stratified"):
        matched, cells = apply_stratified_lookup(realism["stratified"], context_df, as_of=as_of)
        for i in range(n):
            if matched[i] and cells[i] is not None:
                cell_dist = cells[i].get("distribution") if isinstance(cells[i], dict) else None
                if cell_dist:
                    cp = np.array([float(cell_dist.get(c, 0.0)) for c in codes], dtype=float)
                    s = cp.sum()
                    if s > 0:
                        cp = cp / s
                        log_odds[:, i] = np.log(np.maximum(cp, 1e-12))
    else:
        matched = np.zeros(n, dtype=bool)

    # Layer 2: verb effects (only on unmatched rows to avoid double-counting)
    effects = realism.get("effects")
    if effects:
        scratch = np.zeros_like(log_odds)
        scratch = apply_verb_effects_categorical(scratch, codes, effects, context_df, as_of=as_of)
        unmatched = ~matched
        log_odds[:, unmatched] += scratch[:, unmatched]

    # Sample via softmax
    log_odds -= log_odds.max(axis=0, keepdims=True)
    w = np.exp(log_odds)
    w /= w.sum(axis=0, keepdims=True)
    u = rng.random(n)
    cum = np.cumsum(w, axis=0)
    idx = (cum < u[None, :]).sum(axis=0)
    idx = np.clip(idx, 0, n_codes - 1)
    out = np.array([codes[i] for i in idx], dtype=object)

    # Layer 1: hard rules
    if realism.get("hard_rules"):
        out = apply_hard_rules_categorical(
            out, realism["hard_rules"], context_df,
            base_dist=base_dist, rng=rng, as_of=as_of,
        )

    return out
