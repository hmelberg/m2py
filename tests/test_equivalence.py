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
# Scope it to this module via an autouse fixture so it does not leak into other
# test files (which rely on the default ON behaviour).
@pytest.fixture(autouse=True)
def _disclosure_off(monkeypatch):
    monkeypatch.setattr(m2py, "M2PY_DISCLOSURE_CONTROL", "0", raising=False)


# ── pipeline ────────────────────────────────────────────────────────────────

def _ground_truth(python: str, df_in: pd.DataFrame, result: str) -> pd.DataFrame:
    ns = {"df": df_in.copy(), "pd": pd, "np": np}
    exec(python, ns)
    return ns[result]


def _run_microdata(script: str, df_in: pd.DataFrame, result: str) -> pd.DataFrame:
    """Run a microdata script in the emulator against df_in; return the resulting
    dataset. Shared by the py2m and r2m backends."""
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
    return it.datasets[result]


def _emulator(python: str, df_in: pd.DataFrame, result: str):
    script = transform(python).script()
    return _run_microdata(script, df_in, result), script


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

    # ── broadened coverage (added 2026-06-13) ────────────────────────────────
    ("fillna_scalar",
     "df['x'] = df['a'].fillna(0)",
     {"a": [1.0, None, 3.0, None, 5.0]}, "df"),
    ("map_string_values",
     "df['lab'] = df['k'].map({1: 'low', 2: 'mid', 3: 'high'})",
     {"k": [1, 2, 3, 1, 2, 3]}, "df"),
    ("map_same_col_recode",
     "df['k'] = df['k'].map({1: 10, 2: 20, 3: 30})",
     {"k": [1, 2, 3, 1, 2, 3]}, "df"),
    ("where_other_scalar",
     "df['x'] = df['a'].where(df['a'] > 0, -1)",
     {"a": [-2, 3, -1, 5, 0, 7]}, "df"),
    ("mask_other_scalar",
     "df['x'] = df['a'].mask(df['a'] < 0, 0)",
     {"a": [-2, 3, -1, 5, 0, 7]}, "df"),
    ("np_where_three_branches",
     "df['g'] = np.where(df['a'] >= 20, 3, "
     "np.where(df['a'] >= 10, 2, np.where(df['a'] >= 5, 1, 0)))",
     {"a": [2, 5, 12, 25, 8, 30]}, "df"),
    ("str_cat_sep",
     "df['full'] = df['a'].str.cat(df['b'], sep='-')",
     {"a": ["x", "y", "z"], "b": ["1", "2", "3"]}, "df"),
    ("str_cat_nosep",
     "df['full'] = df['a'].str.cat(df['b'])",
     {"a": ["x", "y", "z"], "b": ["1", "2", "3"]}, "df"),
    ("qcut_labels_false",
     "df['q'] = pd.qcut(df['a'], 4, labels=False)",
     {"a": list(range(1, 13))}, "df"),
    ("rowmax_axis1",
     "df['mx'] = df[['a', 'b', 'c']].max(axis=1)",
     {"a": [1, 5, 2, 9], "b": [4, 1, 9, 0], "c": [3, 3, 3, 3]}, "df"),
    ("rowmin_axis1",
     "df['mn'] = df[['a', 'b', 'c']].min(axis=1)",
     {"a": [1, 5, 2, 9], "b": [4, 1, 9, 0], "c": [3, 3, 3, 3]}, "df"),
    ("rowmean_axis1",
     "df['avg'] = df[['a', 'b']].mean(axis=1)",
     {"a": [1.0, 5.0, 2.0], "b": [3.0, 1.0, 8.0]}, "df"),
    ("astype_str_new_col",
     "df['c'] = df['a'].astype(str)",
     {"a": [1, 2, 3, 42]}, "df"),
    ("filter_between",
     "df = df[df['a'].between(2, 5)]",
     {"a": [1, 2, 3, 4, 5, 6], "g": [1, 1, 2, 2, 3, 3]}, "df"),
    ("filter_isin",
     "df = df[df['k'].isin([1, 3])]",
     {"k": [1, 2, 3, 1, 2, 3], "v": [10, 20, 30, 40, 50, 60]}, "df"),
    ("cut_finite_bins",
     "df['lab'] = pd.cut(df['a'], bins=[0, 10, 20, 30], labels=[1, 2, 3])",
     {"a": [5, 15, 25, 8, 22, 30]}, "df"),
    ("multi_assign_filter_collapse",
     "df['x'] = df['a'] + 1\n"
     "df = df[df['x'] > 3]\n"
     "summary = df.groupby('g').agg(m=('x', 'mean'), s=('x', 'sum')).reset_index()",
     {"a": [1, 2, 3, 4, 5, 6], "g": [1, 1, 2, 2, 3, 3]}, "summary"),
]


@pytest.mark.parametrize("name,python,data,result", CASES, ids=[c[0] for c in CASES])
def test_equivalent(name, python, data, result):
    df_in = pd.DataFrame(data)
    df_a = _ground_truth(python, df_in, result)
    df_b, script = _emulator(python, df_in, result)
    assert_equivalent(df_a, df_b, script)


# ── allow-list: genuine, documented microdata-vs-pandas semantic differences ──
# (xfail with a reason so they stay visible without blocking CI).
#
# Each entry: (id, python, data, result_var, reason). The translation is
# correct microdata; the harness simply cannot model the representation
# difference with a single synthetic fixture.
XFAIL_CASES = [
    ("date_diff_days",
     "df['d'] = (df['d2'] - df['d1']).dt.days",
     {"d1": ["2020-01-01", "2020-03-01"], "d2": ["2020-01-11", "2020-03-15"]},
     "df",
     "Microdata stores dates as integer days, so '(d2 - d1)' yields an integer "
     "day count directly — the correct translation of (d2-d1).dt.days. The "
     "emulator keeps the fixture's pandas Timestamps and subtracts them to a "
     "Timedelta (nanoseconds under to_numeric), which cannot equal pandas' "
     "integer .dt.days in a single fixture representation."),
]


def _to_dates(data):
    """Convert any ISO-date string columns to pandas datetime for the fixture."""
    df = pd.DataFrame(data)
    for c in df.columns:
        if df[c].dtype == object:
            try:
                df[c] = pd.to_datetime(df[c])
            except (ValueError, TypeError):
                pass
    return df


@pytest.mark.parametrize(
    "name,python,data,result,reason",
    XFAIL_CASES,
    ids=[c[0] for c in XFAIL_CASES],
)
def test_xfail_semantic_difference(name, python, data, result, reason):
    """Documented genuine microdata-vs-pandas differences. xfail with a reason."""
    pytest.xfail(reason)
    df_in = _to_dates(data)
    df_a = _ground_truth(python, df_in, result)
    df_b, script = _emulator(python, df_in, result)
    assert_equivalent(df_a, df_b, script)


# ── r2m backend ──────────────────────────────────────────────────────────────
# Same pipeline, R side: run the R snippet in base R (ground truth A), translate
# it with r2m, run that microdata in the emulator (B), compare. Scoped to base-R
# idioms so no R packages are needed (dplyr/tidyverse cases need dplyr installed).
import shutil
import subprocess
import tempfile
from pathlib import Path

_RSCRIPT = shutil.which("Rscript")
_REPO = Path(__file__).resolve().parent.parent
_R2M_DIR = _REPO / "r2m" / "r2m"
_R_HELPER = Path(__file__).resolve().parent / "r_equiv_helper.R"


def _r2m_pipeline(r_snippet: str, data: dict, result: str):
    """Run R ground truth + r2m translation via Rscript; return (df_a, df_b, script)."""
    df_in = pd.DataFrame(data)
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        in_csv = d / "in.csv"
        df_in.to_csv(in_csv, index=False)
        snip = d / "snippet.R"
        snip.write_text(r_snippet)
        out_csv = d / "out.csv"
        proc = subprocess.run(
            [_RSCRIPT, str(_R_HELPER), str(_R2M_DIR), str(in_csv),
             str(snip), result, str(out_csv)],
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, f"R helper failed:\n{proc.stderr}"
        script = proc.stdout.strip()
        df_a = pd.read_csv(out_csv)
    df_b = _run_microdata(script, df_in, result)
    return df_a, df_b, script


# (id, r_snippet, data, result_var) — base-R idioms only
R_CASES = [
    ("r_assign_arith",
     "df$x <- df$a + df$b * 2",
     {"a": [1, 2, 3, 4], "b": [10, 20, 30, 40]}, "df"),
    ("r_assign_log",
     "df$lx <- log(df$x)",
     {"x": [1.0, 2.0, 3.0, 10.0]}, "df"),
    ("r_ifelse",
     "df$adult <- ifelse(df$age >= 18, 1, 0)",
     {"age": [5, 17, 18, 40, 67]}, "df"),
    ("r_ifelse_inlist",
     "df$hi <- ifelse(df$k %in% c(1, 3), 1, 0)",
     {"k": [1, 2, 3, 1, 2, 3]}, "df"),
    ("r_pmax",
     "df$mx <- pmax(df$a, df$b)",
     {"a": [1, 5, 2, 9], "b": [4, 1, 9, 0]}, "df"),
    ("r_subset",
     "sub <- subset(df, age > 18)",
     {"age": [10, 20, 30, 18, 40], "inc": [1, 2, 3, 4, 5]}, "sub"),
    ("r_bracket_filter",
     "sub <- df[df$age > 18, ]",
     {"age": [10, 20, 30, 18, 40], "inc": [1, 2, 3, 4, 5]}, "sub"),
    ("r_transform",
     "df <- transform(df, x2 = a * 2)",
     {"a": [1, 2, 3, 4]}, "df"),
    ("r_aggregate_mean",
     "agg <- aggregate(x ~ g, data = df, FUN = mean)",
     {"g": [1, 1, 2, 2, 3], "x": [10.0, 20.0, 5.0, 15.0, 100.0]}, "agg"),
    ("r_aggregate_sum",
     "agg <- aggregate(x ~ g, data = df, FUN = sum)",
     {"g": [1, 1, 2, 2], "x": [10.0, 20.0, 5.0, 15.0]}, "agg"),
]


@pytest.mark.skipif(_RSCRIPT is None, reason="Rscript not available")
@pytest.mark.parametrize("name,r_snippet,data,result", R_CASES,
                         ids=[c[0] for c in R_CASES])
def test_r2m_equivalent(name, r_snippet, data, result):
    df_a, df_b, script = _r2m_pipeline(r_snippet, data, result)
    assert_equivalent(df_a, df_b, script)


# ── r2m dplyr/tidyverse cases (need dplyr installed) ─────────────────────────
def _has_dplyr():
    if _RSCRIPT is None:
        return False
    try:
        r = subprocess.run([_RSCRIPT, "-e", 'cat(requireNamespace("dplyr", quietly=TRUE))'],
                           capture_output=True, text=True, timeout=30)
        return r.stdout.strip() == "TRUE"
    except Exception:
        return False


_HAS_DPLYR = _has_dplyr()

# Snippets load dplyr so base-R execution (ground truth) works; r2m drops the
# library() call in translation.
R_DPLYR_CASES = [
    ("r_dplyr_mutate",
     "library(dplyr)\ndf <- df |> mutate(x = a + b * 2)",
     {"a": [1, 2, 3, 4], "b": [10, 20, 30, 40]}, "df"),
    ("r_dplyr_filter",
     "library(dplyr)\ndf <- df |> filter(age > 18)",
     {"age": [10, 20, 30, 18, 40], "inc": [1, 2, 3, 4, 5]}, "df"),
    ("r_dplyr_filter_two_conds",
     "library(dplyr)\ndf <- df |> filter(a > 2, b < 9)",
     {"a": [1, 3, 5, 2, 4], "b": [10, 8, 7, 6, 9]}, "df"),
    ("r_dplyr_case_when_first_match",
     "library(dplyr)\n"
     "df <- df |> mutate(grp = case_when(age < 30 ~ 1, age < 60 ~ 2, TRUE ~ 3))",
     {"age": [25, 45, 70, 18, 60]}, "df"),   # 25 matches both → first-match must give 1
    ("r_dplyr_ifelse",
     "library(dplyr)\ndf <- df |> mutate(adult = if_else(age >= 18, 1, 0))",
     {"age": [5, 17, 18, 40, 67]}, "df"),
    ("r_dplyr_mutate_chain",
     "library(dplyr)\ndf <- df |> filter(income > 0) |> mutate(log_inc = log(income))",
     {"income": [100.0, 0.0, 500.0, 250.0, 0.0]}, "df"),
    ("r_dplyr_groupby_summarise",
     "library(dplyr)\nout <- df |> group_by(g) |> summarise(m = mean(x))",
     {"g": [1, 1, 2, 2, 3], "x": [10.0, 20.0, 5.0, 15.0, 100.0]}, "out"),
    ("r_dplyr_groupby_two_stats",
     "library(dplyr)\nout <- df |> group_by(g) |> summarise(m = mean(x), s = sum(x))",
     {"g": [1, 1, 2, 2], "x": [10.0, 20.0, 5.0, 15.0]}, "out"),
]


@pytest.mark.skipif(not _HAS_DPLYR, reason="dplyr not installed")
@pytest.mark.parametrize("name,r_snippet,data,result", R_DPLYR_CASES,
                         ids=[c[0] for c in R_DPLYR_CASES])
def test_r2m_dplyr_equivalent(name, r_snippet, data, result):
    df_a, df_b, script = _r2m_pipeline(r_snippet, data, result)
    assert_equivalent(df_a, df_b, script)
