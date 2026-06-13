"""Translation equivalence harness (behavioral verification).

For each case: run the original Python in real pandas (ground truth A), translate
it to microdata with py2m, run that script in the m2py emulator (B), and assert
A and B are the same data. This catches translations that are string-plausible
but behaviorally wrong — which golden/string tests cannot.

Scope v1: data-transform idioms only (generate/replace/keep/drop/recode/
aggregate/collapse), synthetic fixtures, py2m backend. See
docs/superpowers/specs/2026-06-13-translation-equivalence-harness-design.md.
"""
import numpy as np
import pandas as pd
import pytest

import m2py
from m2py import MicroInterpreter
from py2m import transform


# Disclosure control would block small synthetic populations (T1/T6 thresholds).
m2py.M2PY_DISCLOSURE_CONTROL = "0"


# ── pipeline ────────────────────────────────────────────────────────────────

def _ground_truth(python: str, df_in: pd.DataFrame, result: str) -> pd.DataFrame:
    ns = {"df": df_in.copy(), "pd": pd, "np": np}
    exec(python, ns)
    return ns[result]


def _emulator(python: str, df_in: pd.DataFrame, result: str):
    script = transform(python).script()
    assert "UNTRANSLATED" not in script, f"did not translate:\n{script}"
    it = MicroInterpreter(metadata_path=None)
    it.datasets["df"] = df_in.copy()
    it.active_name = "df"
    for line in script.splitlines():
        if line.strip():
            it._execute_instruction(it.parser.parse_line(line))
    feil = [l for l in it.output_log if "FEIL" in str(l)]
    assert not feil, f"emulator errors for script:\n{script}\n{feil}"
    assert result in it.datasets, (
        f"emulator produced no dataset '{result}'; have {list(it.datasets)}\n{script}")
    return it.datasets[result], script


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Canonical form: sorted columns, numeric→float, sorted rows, reset index."""
    df = df.copy()
    df.columns = [str(c) for c in df.columns]
    df = df[sorted(df.columns)]
    for c in df.columns:
        coerced = pd.to_numeric(df[c], errors="coerce")
        # treat a column as numeric only if coercion lost no non-missing values
        if coerced.notna().sum() >= df[c].notna().sum():
            df[c] = coerced.astype(float)
        else:
            df[c] = df[c].astype("string")
    df = df.sort_values(list(df.columns), na_position="last").reset_index(drop=True)
    return df


def assert_equivalent(df_a: pd.DataFrame, df_b: pd.DataFrame, script: str):
    a, b = _normalize(df_a), _normalize(df_b)
    assert list(a.columns) == list(b.columns), (
        f"column mismatch: pandas={list(a.columns)} vs emulator={list(b.columns)}\n{script}")
    assert len(a) == len(b), (
        f"row count mismatch: pandas={len(a)} vs emulator={len(b)}\n{script}")
    for c in a.columns:
        sa, sb = a[c], b[c]
        if sa.dtype == float:
            both_na = sa.isna() & sb.isna()
            close = np.isclose(sa.fillna(0), sb.fillna(0), rtol=1e-9, atol=1e-9)
            assert bool((both_na | close).all()), (
                f"value mismatch in '{c}':\npandas={list(sa)}\nemul ={list(sb)}\n{script}")
        else:
            assert sa.fillna("").tolist() == sb.fillna("").tolist(), (
                f"value mismatch in '{c}':\npandas={list(sa)}\nemul ={list(sb)}\n{script}")


# ── cases: (id, python, data, result_var) ───────────────────────────────────

_N = 12  # small but >0; disclosure control is off

CASES = [
    ("generate_arith",
     "df['x'] = df['a'] + df['b'] * 2",
     {"a": list(range(_N)), "b": list(range(_N, 0, -1))}, "df"),
    ("generate_nplog",
     "df['lx'] = np.log(df['a'])",
     {"a": [1.0, 2.0, 3.0, 10.0, 100.0]}, "df"),
    ("generate_where",
     "df['x'] = df['a'].where(df['a'] > 0, 0)",
     {"a": [-2, -1, 0, 1, 2, 3]}, "df"),
    ("generate_mask",
     "df['x'] = df['a'].mask(df['a'] < 0, 0)",
     {"a": [-2, -1, 0, 1, 2, 3]}, "df"),
    ("np_where",
     "df['g'] = np.where(df['age'] >= 18, 1, 0)",
     {"age": [5, 17, 18, 40, 67, 90]}, "df"),
    ("replace_loc",
     "df.loc[df['a'] > 5, 'a'] = 5",
     {"a": [1, 4, 6, 8, 10, 2]}, "df"),
    ("keep_filter",
     "df = df[df['age'] > 18]",
     {"age": [10, 20, 30, 18, 40, 5], "inc": [1, 2, 3, 4, 5, 6]}, "df"),
    ("keep_query",
     "df = df.query('a > 2 & b < 9')",
     {"a": [1, 3, 5, 2, 4], "b": [10, 8, 7, 6, 9]}, "df"),
    ("keep_columns",
     "df = df[['a', 'b']]",
     {"a": [1, 2, 3], "b": [4, 5, 6], "c": [7, 8, 9]}, "df"),
    ("drop_columns",
     "df = df.drop(columns=['c'])",
     {"a": [1, 2, 3], "b": [4, 5, 6], "c": [7, 8, 9]}, "df"),
    ("map_recode",
     "df['lab'] = df['k'].map({1: 10, 2: 20, 3: 30})",
     {"k": [1, 2, 3, 1, 2, 3]}, "df"),
    ("aggregate_transform",
     "df['gm'] = df.groupby('g')['x'].transform('mean')",
     {"g": [1, 1, 2, 2, 3, 3], "x": [10.0, 20.0, 5.0, 15.0, 100.0, 0.0]}, "df"),
    ("collapse_mean",
     "summary = df.groupby('g').agg(m=('x', 'mean')).reset_index()",
     {"g": [1, 1, 2, 2, 3], "x": [10.0, 20.0, 5.0, 15.0, 100.0]}, "summary"),
    ("collapse_two_stats",
     "summary = df.groupby('g').agg(m=('x', 'mean'), s=('x', 'sum')).reset_index()",
     {"g": [1, 1, 2, 2], "x": [10.0, 20.0, 5.0, 15.0]}, "summary"),
]


@pytest.mark.parametrize("name,python,data,result", CASES, ids=[c[0] for c in CASES])
def test_equivalent(name, python, data, result):
    df_in = pd.DataFrame(data)
    df_a = _ground_truth(python, df_in, result)
    df_b, script = _emulator(python, df_in, result)
    assert_equivalent(df_a, df_b, script)


# ── allow-list: genuine, documented microdata-vs-pandas semantic differences ──
# (xfail with a reason so they stay visible without blocking CI). Empty for now.
