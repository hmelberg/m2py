"""Cross-engine equivalence: emulator (oracle) == pandas backend == polars backend.

For each microdata script we run it three ways and assert the resulting dataset
is the same data:
  A. the in-browser emulator (m2py.MicroInterpreter)         -- ground truth
  B. m2py_translate -> pandas script -> exec                 -- thin pandas export
  C. m2py_translate -> polars LazyFrame script -> collect    -- offline polars

Focus per project priorities: data shaping, statistics, and merging. Variable
import is out of scope (data is provided directly).
"""
import numpy as np
import pandas as pd
import polars as pl
import pytest

import m2py
import m2py_translate as T


# disclosure control would block tiny synthetic populations; off for this module
@pytest.fixture(autouse=True)
def _disclosure_off(monkeypatch):
    monkeypatch.setattr(m2py, "M2PY_DISCLOSURE_CONTROL", "0", raising=False)


# ── harness ──────────────────────────────────────────────────────────────────

def _emulate(script, datasets, active):
    it = m2py.MicroInterpreter(metadata_path=None)
    for k, v in datasets.items():
        it.datasets[k] = v.copy()
    it.active_name = active
    for ln in script.splitlines():
        if ln.strip():
            it._execute_instruction(it.parser.parse_line(ln))
    feil = [l for l in it.output_log if "FEIL" in str(l)]
    assert not feil, f"emulator errors:\n{script}\n{feil}"
    return it.datasets[active]


def _run_pandas(script, datasets, active):
    code = T.translate(script, backend="pandas", source_path=None)
    assert "UNTRANSLATED" not in code, code
    ns = {"df": datasets[active].copy(), "pd": pd, "datasets": datasets}
    exec(code, ns)
    return ns["df"]


def _run_polars(script, datasets, active):
    code = T.translate(script, backend="polars", source_path=None)
    assert "UNTRANSLATED" not in code, code
    pl_datasets = {k: pl.LazyFrame(v) for k, v in datasets.items()}
    ns = {"data": pl.LazyFrame(datasets[active]), "pl": pl, "datasets": pl_datasets}
    exec(code, ns)
    return ns["df"].to_pandas()


def _norm(df):
    df = df.copy()
    df.columns = [str(c) for c in df.columns]
    df = df[sorted(df.columns)]
    for c in df.columns:
        co = pd.to_numeric(df[c], errors="coerce")
        if co.notna().sum() >= df[c].notna().sum():
            df[c] = co.astype(float)
        else:
            df[c] = df[c].astype("string")
    return df.sort_values(list(df.columns), na_position="last").reset_index(drop=True)


def _assert_same(a, b, label, script):
    a, b = _norm(a), _norm(b)
    assert list(a.columns) == list(b.columns), (
        f"[{label}] columns {list(a.columns)} != {list(b.columns)}\n{script}")
    assert len(a) == len(b), f"[{label}] rows {len(a)} != {len(b)}\n{script}"
    for c in a.columns:
        sa, sb = a[c], b[c]
        if sa.dtype == float:
            ok = (sa.isna() & sb.isna()) | np.isclose(
                sa.fillna(0), sb.fillna(0), rtol=1e-9, atol=1e-6)
            assert bool(ok.all()), f"[{label}] '{c}':\n{list(sa)}\n{list(sb)}\n{script}"
        else:
            assert sa.fillna("").tolist() == sb.fillna("").tolist(), (
                f"[{label}] '{c}':\n{list(sa)}\n{list(sb)}\n{script}")


# ── cases: (id, script, datasets, active) ────────────────────────────────────

_G = {"a": [0, 1, 2, 3, 4, -1], "b": [4, 3, 2, 1, 0, 9], "g": [1, 1, 2, 2, 3, 1]}
_F = {"x": [10.0, 20.0, 5.0, 15.0, 100.0, 0.0], "g": [1, 1, 2, 2, 3, 3],
      "k": [1, 2, 3, 1, 2, 3]}
_MAIN = {"kommune": [1, 2, 3, 1, 2], "inntekt": [10.0, 20.0, 30.0, 40.0, 50.0]}
_LOOK = {"kommune": [1, 2, 3], "navn": ["Oslo", "Bergen", "Trondheim"]}

CASES = [
    ("generate_arith", "generate y = a + b * 2", {"df": pd.DataFrame(_G)}, "df"),
    ("generate_div",   "generate y = a / (b + 1)", {"df": pd.DataFrame(_G)}, "df"),
    ("generate_if",    "generate pos = 1 if a > 0", {"df": pd.DataFrame(_G)}, "df"),
    ("generate_pow",   "generate y = a ** 2", {"df": pd.DataFrame(_G)}, "df"),
    ("replace_if",     "replace a = 0 if a < 0", {"df": pd.DataFrame(_G)}, "df"),
    ("keep_rows",      "keep if a > 1", {"df": pd.DataFrame(_G)}, "df"),
    ("keep_cols",      "keep a b", {"df": pd.DataFrame(_G)}, "df"),
    ("drop_cols",      "drop b", {"df": pd.DataFrame(_G)}, "df"),
    ("drop_rows",      "drop if a < 2", {"df": pd.DataFrame(_G)}, "df"),
    ("recode",         "recode k (1=10)(2=20)(3=30)", {"df": pd.DataFrame(_F)}, "df"),
    ("collapse_mean",  "collapse (mean) x -> mx, by(g)", {"df": pd.DataFrame(_F)}, "df"),
    ("collapse_multi", "collapse (mean) x -> mx (sum) x -> sx (min) x -> lo (max) x -> hi, by(g)",
     {"df": pd.DataFrame(_F)}, "df"),
    ("collapse_median", "collapse (median) x -> md, by(g)", {"df": pd.DataFrame(_F)}, "df"),
    ("collapse_global", "collapse (mean) x -> mx (sum) x -> sx", {"df": pd.DataFrame(_F)}, "df"),
    ("aggregate",      "aggregate (mean) x -> gm, by(g)", {"df": pd.DataFrame(_F)}, "df"),
    ("merge",          "merge look on kommune",
     {"main": pd.DataFrame(_MAIN), "look": pd.DataFrame(_LOOK)}, "main"),
    ("pipeline_shaping",
     "generate y = a + b\nreplace y = 0 if y < 0\nkeep if a >= 0\ncollapse (mean) y -> my (count) y -> n, by(g)",
     {"df": pd.DataFrame(_G)}, "df"),
    ("merge_then_collapse",
     "merge look on kommune\ncollapse (sum) inntekt -> total (mean) inntekt -> snitt, by(navn)",
     {"main": pd.DataFrame(_MAIN), "look": pd.DataFrame(_LOOK)}, "main"),
    # real-world shaping idioms (region code -> fylke; birth-year -> age; missing)
    ("substr_fylke", "generate fylke = substr(bosted,1,2)",
     {"df": pd.DataFrame({"bosted": ["0301", "1103", "5001"]})}, "df"),
    ("int_truncate", "generate alder = 2017 - int(faarmnd/100)",
     {"df": pd.DataFrame({"faarmnd": [195003.0, 200011.0, 198506.0]})}, "df"),
    ("bool_arith", "generate hoy = 1 * (a > 1)", {"df": pd.DataFrame(_G)}, "df"),
    ("rename", "rename a alpha", {"df": pd.DataFrame(_G)}, "df"),
    ("destring_force", "destring s, force",
     {"df": pd.DataFrame({"s": ["1", "2", "x", "4"]})}, "df"),
    ("destring_clean", "destring s",
     {"df": pd.DataFrame({"s": ["1", "2", "3", "4"]})}, "df"),
    ("shaping_chain",
     "generate fylke = substr(bosted,1,2)\nkeep if fylke == \"03\"",
     {"df": pd.DataFrame({"bosted": ["0301", "0302", "1103", "5001"]})}, "df"),
]


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_pandas_backend_matches_emulator(case):
    _id, script, datasets, active = case
    _assert_same(_emulate(script, datasets, active),
                 _run_pandas(script, datasets, active), "pandas", script)


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_polars_backend_matches_emulator(case):
    _id, script, datasets, active = case
    _assert_same(_emulate(script, datasets, active),
                 _run_polars(script, datasets, active), "polars", script)


# ── analysis verbs (side outputs; working frame unchanged) ───────────────────

_ANALYSIS_DF = pd.DataFrame({
    "y": [1.0, 3, 2, 5, 4, 6, 2, 7],
    "x": [1.0, 2, 3, 4, 5, 6, 7, 8],
    "g": [1, 1, 1, 2, 2, 2, 3, 3],
})


def _run_analysis(script, df, backend):
    """Translate+exec; return the result_1 frame (as pandas) and the final df."""
    code = T.translate(script, backend=backend, source_path=None)
    assert "UNTRANSLATED" not in code, code
    if backend == "polars":
        ns = {"data": pl.LazyFrame(df), "pl": pl, "datasets": None}
        exec(code, ns)
        return ns["result_1"].to_pandas(), ns["df"].to_pandas()
    ns = {"df": df.copy(), "pd": pd, "datasets": None}
    exec(code, ns)
    return ns["result_1"], ns["df"]


@pytest.mark.parametrize("script", [
    "summarize y x",
    "summarize y x, by(g)",
    "tabulate g",
    "correlate y x",
])
def test_analysis_pandas_polars_agree(script):
    rp, _ = _run_analysis(script, _ANALYSIS_DF, "pandas")
    rl, _ = _run_analysis(script, _ANALYSIS_DF, "polars")
    _assert_same(rp, rl, "analysis", script)


def test_analysis_does_not_change_working_frame():
    # summarize between two transforms must not clobber the dataset
    script = "generate z = x * 2\nsummarize y\ncollapse (mean) z -> mz, by(g)"
    _, final = _run_analysis(script, _ANALYSIS_DF, "polars")
    assert sorted(final.columns) == ["g", "mz"]
    assert len(final) == 3  # 3 groups, not the summary rows


def test_regress_matches_statsmodels():
    sm = pytest.importorskip("statsmodels.api")
    for backend in ("pandas", "polars"):
        res, _ = _run_analysis("regress y x", _ANALYSIS_DF, backend)
        X = sm.add_constant(_ANALYSIS_DF[["x"]])
        truth = sm.OLS(_ANALYSIS_DF["y"], X).fit()
        got = dict(zip(res["term"], res["coef"]))
        assert np.isclose(got["const"], truth.params["const"], rtol=1e-9)
        assert np.isclose(got["x"], truth.params["x"], rtol=1e-9)


def test_unsupported_expression_is_marked_not_silently_wrong():
    # a microdata function the polars compiler doesn't implement -> UNTRANSLATED,
    # never emitted as incorrect polars.
    script = "generate w = wordcount(a)"
    code = T.translate(script, backend="polars", source_path=None)
    assert "UNTRANSLATED" in code
    assert T.unsupported(script) == ["generate w = wordcount(a)"]
