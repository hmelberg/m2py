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
    for ln in it.parser.preprocess_script(script).splitlines():   # join `\` continuations
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
    ("recode_multivalue", "recode k (1 2 = 1)(3 = 2)", {"df": pd.DataFrame(_F)}, "df"),
    ("recode_range",   "recode x (0/15 = 1)(16/max = 2)", {"df": pd.DataFrame(_F)}, "df"),
    ("generate_boolprec", "generate hi = (a >= 0 & a < 3)", {"df": pd.DataFrame(_G)}, "df"),
    ("generate_boolor", "generate flag = a == 0 | a == 4", {"df": pd.DataFrame(_G)}, "df"),
    ("generate_linecont", "generate s = rowtotal(a, \\\n   b)", {"df": pd.DataFrame(_G)}, "df"),
    ("collapse_mean",  "collapse (mean) x -> mx, by(g)", {"df": pd.DataFrame(_F)}, "df"),
    ("collapse_multi", "collapse (mean) x -> mx (sum) x -> sx (min) x -> lo (max) x -> hi, by(g)",
     {"df": pd.DataFrame(_F)}, "df"),
    ("collapse_median", "collapse (median) x -> md, by(g)", {"df": pd.DataFrame(_F)}, "df"),
    ("collapse_global", "collapse (mean) x -> mx (sum) x -> sx", {"df": pd.DataFrame(_F)}, "df"),
    ("aggregate",      "aggregate (mean) x -> gm, by(g)", {"df": pd.DataFrame(_F)}, "df"),
    ("merge",          "merge look on kommune",
     {"main": pd.DataFrame(_MAIN), "look": pd.DataFrame(_LOOK)}, "main"),
    # non-overlapping keys so left vs outer differ: main has 1,2,4; look has 1,2,3
    ("merge_left_nonoverlap", "merge look on kommune",
     {"main": pd.DataFrame({"kommune": [1, 2, 4], "x": [10.0, 20, 40]}),
      "look": pd.DataFrame(_LOOK)}, "main"),
    ("merge_outer_join", "merge look on kommune, outer_join",
     {"main": pd.DataFrame({"kommune": [1, 2, 4], "x": [10.0, 20, 40]}),
      "look": pd.DataFrame(_LOOK)}, "main"),
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
    "summarize y x, gini iqr",
    "summarize y if x > 3",          # analysis with an if-condition
    "tabulate g if y > 2",
    "tabulate g",
    "tabulate g y",          # two-way cross-tab
    "tabulate g y, cellpct",
    "tabulate g y, rowpct",
    "tabulate g y, colpct",
    "tabulate g y, freq rowpct",
    "tabulate g y, chi2",
    "tabulate g, top(2)",
    "tabulate g, bottom(1)",
    "tabulate g y, chi2 top(3)",
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


# ── plots (terminal; build a plotly figure, frame unchanged) ─────────────────

_PLOT_DF = pd.DataFrame({
    "inntekt": (list(range(100, 1100, 10)) + [None]),    # 100 numeric + 1 missing
    "kommune": (([1, 2, 3] * 34)[:101]),                 # 3 levels
    "kjonn": (([1, 2] * 51)[:101]),                      # 2 levels (grouping)
    "alder": list(range(20, 121)),
})


def _run_fig(script, df, backend):
    code = T.translate(script, backend=backend, source_path=None)
    assert "UNTRANSLATED" not in code, code
    if backend == "polars":
        ns = {"data": pl.LazyFrame(df), "pl": pl, "datasets": None}
    else:
        ns = {"df": df.copy(), "pd": pd, "datasets": None}
    exec(code, ns)
    return ns["fig_1"]


def _axis_eq(a, b):
    if a is None or b is None:
        return a is b
    if len(a) != len(b):
        return False
    try:                                  # numeric: NaN-aware
        return np.array_equal(np.asarray(a, float), np.asarray(b, float), equal_nan=True)
    except (TypeError, ValueError):
        return list(a) == list(b)         # categorical / strings


def _trace_key(t):
    # normalise empty/None trace name (plotly express uses '' where go uses None)
    # and orientation ('v' is the default, equivalent to None)
    orient = getattr(t, "orientation", None)
    orient = None if orient in (None, "v") else orient
    return (t.name or None, type(t).__name__, getattr(t, "nbinsx", None),
            getattr(t, "histnorm", None) or None, orient)


def _fig_equal(f1, f2):
    if len(f1.data) != len(f2.data):
        return False
    for d1, d2 in zip(f1.data, f2.data):
        if _trace_key(d1) != _trace_key(d2):
            return False
        kind = type(d1).__name__
        if kind == "Pie":
            if list(d1.labels or []) != list(d2.labels or []):
                return False
            if list(d1.values or []) != list(d2.values or []):
                return False
        elif kind == "Sankey":
            if list(d1.node.label or []) != list(d2.node.label or []):
                return False
            for side in ("source", "target", "value"):
                if list(getattr(d1.link, side) or []) != list(getattr(d2.link, side) or []):
                    return False
        elif not (_axis_eq(d1.x, d2.x) and _axis_eq(d1.y, d2.y)):
            return False
    return True


@pytest.mark.parametrize("script,cmd,args,opts", [
    ("histogram inntekt", "histogram", {"vars": ["inntekt"]}, {}),
    ("histogram inntekt, bin(15)", "histogram", {"vars": ["inntekt"]}, {"bin": "15"}),
    ("histogram inntekt, percent", "histogram", {"vars": ["inntekt"]}, {"percent": True}),
    ("histogram inntekt, density", "histogram", {"vars": ["inntekt"]}, {"density": True}),
    ("histogram kommune, discrete", "histogram", {"vars": ["kommune"]}, {"discrete": True}),
    ("histogram inntekt, normal", "histogram", {"vars": ["inntekt"]}, {"normal": True}),
    ("histogram inntekt, percent normal", "histogram",
     {"vars": ["inntekt"]}, {"percent": True, "normal": True}),
    ("barchart kommune", "barchart", {"stat": "count", "vars": ["kommune"]}, {}),
    ("barchart kommune, horizontal", "barchart",
     {"stat": "count", "vars": ["kommune"]}, {"horizontal": True}),
    ("barchart kommune kjonn", "barchart",
     {"stat": "count", "vars": ["kommune", "kjonn"]}, {}),
    ("barchart kommune, over(kjonn) stack", "barchart",
     {"stat": "count", "vars": ["kommune"]}, {"over": "kjonn", "stack": True}),
    ("barchart kommune, over(kjonn)", "barchart",
     {"stat": "count", "vars": ["kommune"]}, {"over": "kjonn"}),
    ("barchart (mean) inntekt, over(kommune)", "barchart",
     {"stat": "mean", "vars": ["inntekt"]}, {"over": "kommune"}),
    ("scatter alder inntekt", "scatter", {"vars": ["alder", "inntekt"]}, {}),
    ("scatter alder inntekt, by(kjonn)", "scatter",
     {"vars": ["alder", "inntekt"]}, {"by": "kjonn"}),
    ("boxplot inntekt", "boxplot", {"vars": ["inntekt"]}, {}),
    ("boxplot inntekt, over(kjonn)", "boxplot", {"vars": ["inntekt"]}, {"over": "kjonn"}),
    ("piechart kommune", "piechart", {"stat": "count", "vars": ["kommune"]}, {}),
    ("piechart (percent) kommune", "piechart", {"stat": "percent", "vars": ["kommune"]}, {}),
    ("hexbin alder inntekt", "hexbin", {"vars": ["alder", "inntekt"]}, {}),
    ("hexbin alder inntekt, bin(12)", "hexbin", {"vars": ["alder", "inntekt"]}, {"bin": "12"}),
    ("sankey kommune kjonn", "sankey", {"vars": ["kommune", "kjonn"]}, {}),
])
def test_plot_trace_matches_emulator_and_backends_agree(script, cmd, args, opts):
    pytest.importorskip("plotly")
    import m2py as _m
    _m.M2PY_DISCLOSURE_CONTROL = "0"
    emu = _m.PlotHandler().execute(cmd, _PLOT_DF, args, opts)
    fpd = _run_fig(script, _PLOT_DF, "pandas")
    fpl = _run_fig(script, _PLOT_DF, "polars")
    assert _fig_equal(fpd, emu), f"{script}: differs from emulator"
    assert _fig_equal(fpd, fpl), f"{script}: pandas vs polars differ"


@pytest.mark.parametrize("reg,dep", [
    ("regress", "y"), ("logit", "binv"), ("probit", "binv"), ("poisson", "cnt"),
])
def _emu_reg_coefs(cmd, df, vars):
    """Extract {term: coef} from the emulator's regression summary text."""
    import re
    m2py.M2PY_DISCLOSURE_CONTROL = "0"
    out = m2py.MicroInterpreter(metadata_path=None).reg_engine.execute(cmd, df, vars, {})
    summary = out[0] if isinstance(out, tuple) else str(out)
    coefs = {}
    for line in summary.splitlines():
        mobj = re.match(r"^\s*(const|x\d+|alpha)\s+(-?\d+\.\d+)\s", line)
        if mobj:
            coefs[mobj.group(1)] = float(mobj.group(2))
    return coefs


@pytest.mark.parametrize("cmd,dep,op", [
    ("logit", "binv", "logit"), ("probit", "binv", "probit"),
    ("poisson", "cnt", "poisson"), ("negative-binomial", "cnt", "negative_binomial"),
])
def test_regression_family_matches_emulator(cmd, dep, op):
    pytest.importorskip("statsmodels.api")
    from m2py_runtime import pandas_ops as po
    rng = np.random.default_rng(1)
    n = 300
    x1, x2 = rng.normal(0, 1, n), rng.normal(0, 1, n)
    df = pd.DataFrame({"x1": x1, "x2": x2,
                       "binv": (0.5 * x1 + rng.normal(0, 1, n) > 0).astype(int),
                       "cnt": rng.poisson(np.exp(0.3 + 0.2 * x1 - 0.1 * x2))})
    emu = _emu_reg_coefs(cmd, df, [dep, "x1", "x2"])
    mine = getattr(po, op)(df, dep, ["x1", "x2"]).set_index("term")["coef"]
    res_pl, _ = _run_analysis(f"{cmd} {dep} x1 x2", df, "polars")
    minep = res_pl.set_index("term")["coef"]
    assert emu, "no coefs parsed from emulator summary"
    for term, c in emu.items():
        assert np.isclose(mine[term], c, atol=1e-3), (cmd, term, mine[term], c)
    assert np.allclose(mine.values, minep.values)      # backend parity


def _predict_df():
    rng = np.random.default_rng(0)
    n = 80
    x1, x2 = rng.normal(0, 1, n), rng.normal(0, 1, n)
    return pd.DataFrame({
        "x1": x1, "x2": x2,
        "y": 2 + 1.5 * x1 + rng.normal(0, 1, n),
        "yb": (0.5 * x1 + rng.normal(0, 1, n) > 0).astype(int),
        "cnt": rng.poisson(np.exp(0.2 * x1)),
    })


def _emu_after(script, df):
    m2py.M2PY_DISCLOSURE_CONTROL = "0"
    it = m2py.MicroInterpreter(metadata_path=None)
    it.datasets["df"] = df.copy()
    it.active_name = "df"
    it._execute_instruction(it.parser.parse_line(script))
    return it.datasets["df"]


@pytest.mark.parametrize("script", [
    "regress-predict y x1 x2, predicted(yhat) residuals(res)",
    "logit-predict yb x1, predicted(xb) probabilities(p) residuals(r)",
    "probit-predict yb x1, probabilities(p)",
    "negative-binomial-predict cnt x1, predicted(mu)",
    "logit-predict yb x1",                      # default -> predicted_prob
])
def test_predict_variants_match_emulator(script):
    pytest.importorskip("statsmodels.api")
    df = _predict_df()
    emu = _emu_after(script, df)
    new = [c for c in emu.columns if c not in df.columns]
    out_pd = T.run(script, {"df": df}, "pandas")
    out_pl = T.run(script, {"df": df}, "polars").to_pandas()
    assert [c for c in out_pd.columns if c not in df.columns] == new   # same columns
    for c in new:
        assert np.allclose(out_pd[c].dropna(), emu[c].dropna(), atol=1e-6), c
        assert np.allclose(out_pd[c].dropna(), out_pl[c].dropna(), atol=1e-6), c


def _reshape_norm(df):
    df = df.copy()
    df.columns = [str(c) for c in df.columns]
    df = df[sorted(df.columns)]
    return df.sort_values(sorted(df.columns)).reset_index(drop=True)


def test_reshape_to_and_from_panel_match_emulator():
    from m2py_runtime import pandas_ops as po
    wide = pd.DataFrame({"unit_id": [1, 2, 3], "lonn2018": [10.0, 20, 30],
                         "lonn2019": [11.0, 21, 31], "lonn2020": [12.0, 22, 32],
                         "kjonn": [1, 2, 1]})

    def emu(df, script):
        m2py.M2PY_DISCLOSURE_CONTROL = "0"
        it = m2py.MicroInterpreter(metadata_path=None)
        it.datasets["df"] = df.copy()
        it.active_name = "df"
        for ln in script.splitlines():
            if ln.strip():
                it._execute_instruction(it.parser.parse_line(ln))
        return it.datasets["df"]

    # wide -> long
    emu_long = emu(wide, "reshape-to-panel lonn")
    mine_long = po.reshape_to_panel(wide, ["lonn"])
    pl_long = T.run("reshape-to-panel lonn", {"df": wide}, "polars").to_pandas()
    assert list(mine_long.columns) == ["unit_id", "tid", "panel@date", "lonn", "kjonn"]
    assert len(mine_long) == 9                                  # 3 entities × 3 times
    assert _reshape_norm(emu_long).equals(_reshape_norm(mine_long))
    assert _reshape_norm(mine_long).equals(_reshape_norm(pl_long))   # parity

    # long -> wide
    emu_wide = emu(emu_long, "reshape-from-panel")
    mine_wide = po.reshape_from_panel(mine_long)
    pl_wide = T.run("reshape-from-panel", {"df": mine_long}, "polars").to_pandas()
    assert _reshape_norm(emu_wide).equals(_reshape_norm(mine_wide))
    assert _reshape_norm(mine_wide).equals(_reshape_norm(pl_wide))


def test_poisson_predict_is_flagged():
    # not a real microdata command (the emulator rejects it)
    assert T.unsupported("poisson-predict cnt x1") == ["poisson-predict cnt x1"]


def test_predict_augments_frame_pipeline_continues():
    df = _predict_df()
    out = T.run("regress-predict y x1, predicted(yhat)\nkeep if yhat > 2",
                {"df": df}, "polars").to_pandas()
    assert "yhat" in out.columns and (out["yhat"] > 2).all()


def test_mlogit_matches_emulator():
    pytest.importorskip("statsmodels.api")
    import re
    from m2py_runtime import pandas_ops as po
    rng = np.random.default_rng(0)
    n = 400
    x1, x2 = rng.normal(0, 1, n), rng.normal(0, 1, n)
    eta = np.column_stack([np.zeros(n), 0.5 + 0.8 * x1, -0.3 + 0.5 * x2])
    probs = np.exp(eta) / np.exp(eta).sum(1, keepdims=True)
    cat = np.array([rng.choice(3, p=probs[i]) for i in range(n)])
    df = pd.DataFrame({"cat": cat, "x1": x1, "x2": x2})
    m2py.M2PY_DISCLOSURE_CONTROL = "0"
    out = m2py.MicroInterpreter(metadata_path=None).reg_engine.execute(
        "mlogit", df, ["cat", "x1", "x2"], {})
    summary = out[0] if isinstance(out, tuple) else str(out)
    emu_x1 = sorted(float(m.group(1)) for m in re.finditer(r"x1\s+(-?\d+\.\d+)\s", summary))
    mine = po.mlogit(df, "cat", ["x1", "x2"])
    res_pl, _ = _run_analysis("mlogit cat x1 x2", df, "polars")
    assert sorted(mine["category"].unique()) == [1, 2]          # non-reference cats
    assert np.allclose(sorted(mine[mine["term"] == "x1"]["coef"]), emu_x1, atol=1e-3)
    assert np.allclose(mine["coef"].to_numpy(), res_pl["coef"].to_numpy())  # parity


def _emu_rdd_estimates(args, opts, df):
    """{method: (estimate, se)} from the emulator's rdrobust rdd output."""
    import re
    m2py.M2PY_DISCLOSURE_CONTROL = "0"
    out = m2py.MicroInterpreter(metadata_path=None).reg_engine.execute("rdd", df, args, opts)
    s = out[0] if isinstance(out, tuple) else str(out)
    res = {}
    for l in s.splitlines():
        m = re.match(r"^(Conventional|Bias-Corrected|Robust)\s+(-?\d+\.\d+)\s+(\d+\.\d+)", l)
        if m:
            res[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    return res


def test_rdd_matches_emulator_rdrobust():
    pytest.importorskip("rdrobust")
    from m2py_runtime import pandas_ops as po
    rng = np.random.default_rng(0)
    n = 400
    R = rng.uniform(-1, 1, n)
    Tt = (R >= 0).astype(int)
    df = pd.DataFrame({"y": 1 + 2.5 * Tt + 0.7 * R + rng.normal(0, 0.5, n), "run": R})
    emu = _emu_rdd_estimates({"dep": "y", "runvar": "run", "exog": []}, {"cutoff": "0"}, df)
    mine = po.rdd(df, "y", "run", cutoff=0.0).set_index("method")
    res_pl, _ = _run_analysis("rdd y run, cutoff(0)", df, "polars")
    assert set(emu) == {"Conventional", "Bias-Corrected", "Robust"}
    for meth, (est, se) in emu.items():
        assert round(float(mine.loc[meth, "estimate"]), 2) == est
        assert round(float(mine.loc[meth, "se"]), 2) == se
    assert np.allclose(res_pl.set_index("method")["estimate"], mine["estimate"])  # parity


def test_rdd_fuzzy_matches_emulator():
    pytest.importorskip("rdrobust")
    from m2py_runtime import pandas_ops as po
    rng = np.random.default_rng(0)
    n = 400
    R = rng.uniform(-1, 1, n)
    Tt = (R >= 0).astype(int)
    D = (rng.random(n) < 0.5 + 0.4 * Tt).astype(float)
    df = pd.DataFrame({"y": 1 + 2.0 * D + 0.7 * R + rng.normal(0, 0.5, n), "run": R, "d": D})
    emu = _emu_rdd_estimates({"dep": "y", "runvar": "run", "exog": []},
                             {"cutoff": "0", "fuzzy": "d"}, df)
    mine = po.rdd(df, "y", "run", cutoff=0.0, fuzzy="d").set_index("method")
    for meth, (est, se) in emu.items():
        assert round(float(mine.loc[meth, "estimate"]), 2) == est


@pytest.mark.parametrize("method,fallback_runs", [(None, True)])
def test_rdd_ols_fallback_runs(method, fallback_runs):
    # the OLS fallback still produces an estimate when used directly
    from m2py_runtime import pandas_ops as po
    import m2py_runtime.pandas_ops as mod
    rng = np.random.default_rng(1)
    n = 200
    R = rng.uniform(-1, 1, n)
    df = pd.DataFrame({"y": 1 + 2.0 * (R >= 0) + 0.5 * R + rng.normal(0, 0.4, n), "run": R})
    # force the fallback by hiding rdrobust
    import builtins
    real_import = builtins.__import__

    def no_rdrobust(name, *a, **k):
        if name == "rdrobust" or name.startswith("rdrobust."):
            raise ImportError("forced")
        return real_import(name, *a, **k)
    builtins.__import__ = no_rdrobust
    try:
        out = po.rdd(df, "y", "run", cutoff=0.0)
    finally:
        builtins.__import__ = real_import
    assert "discontinuity" in out["term"].values
    assert 1.5 < float(out["estimate"].iloc[0]) < 2.5


def _emu_coef_table(cmd, df, args, opts):
    """Parse {term: coef} from a regression summary (any alphanumeric term)."""
    import re
    m2py.M2PY_DISCLOSURE_CONTROL = "0"
    out = m2py.MicroInterpreter(metadata_path=None).reg_engine.execute(cmd, df, args, opts)
    s = out[0] if isinstance(out, tuple) else str(out)
    d = {}
    for line in s.splitlines():
        mobj = re.match(r"^\s*([A-Za-z_]\w*)\s+(-?\d+\.\d+)\s+\d", line)
        if mobj and mobj.group(1) not in ("Dep", "No", "Df", "R", "Method", "Date",
                                          "Time", "Covariance", "Model"):
            d[mobj.group(1)] = float(mobj.group(2))
    return d


def _panel_df():
    rng = np.random.default_rng(0)
    rows = []
    for i in range(50):
        fe = rng.normal(0, 1)
        for t in range(5):
            x1, x2 = rng.normal(0, 1), rng.normal(0, 1)
            rows.append({"unit_id": i, "tid": t, "x1": x1, "x2": x2,
                         "y": 1 + 0.8 * x1 - 0.5 * x2 + fe + rng.normal(0, 0.5)})
    return pd.DataFrame(rows)


@pytest.mark.parametrize("effect,opts", [("fe", {}), ("re", {"re": True}),
                                         ("pooled", {"pooled": True})])
def test_regress_panel_matches_emulator(effect, opts):
    pytest.importorskip("linearmodels")
    from m2py_runtime import pandas_ops as po
    df = _panel_df()
    emu = _emu_coef_table("regress-panel", df, ["y", "x1", "x2"], opts)
    flag = {"fe": "", "re": ", re", "pooled": ", pooled"}[effect]
    mine = po.regress_panel(df, "y", ["x1", "x2"], effect=effect).set_index("term")["coef"]
    res_pl, _ = _run_analysis("regress-panel y x1 x2" + flag, df, "polars")
    assert emu
    for term, c in emu.items():
        assert np.isclose(mine[term], c, atol=1e-3), (effect, term)
    assert np.allclose(res_pl.set_index("term").loc[mine.index, "coef"], mine.values)


def test_regress_panel_diff_matches_emulator():
    pytest.importorskip("statsmodels.api")
    import re
    from m2py_runtime import pandas_ops as po
    rng = np.random.default_rng(0)
    n = 400
    g, tr = rng.integers(0, 2, n), rng.integers(0, 2, n)
    df = pd.DataFrame({"y": 1 + 0.5 * g + 0.3 * tr + 2.0 * (g * tr) + rng.normal(0, 0.5, n),
                       "g": g.astype(float), "tr": tr.astype(float),
                       "unit_id": np.arange(n) % 50, "tid": np.arange(n) % 4})
    m2py.M2PY_DISCLOSURE_CONTROL = "0"
    out = m2py.MicroInterpreter(metadata_path=None).reg_engine.execute(
        "regress-panel-diff", df, ["y", "g", "tr"], {})
    s = out[0] if isinstance(out, tuple) else str(out)
    emu_atet = float(re.search(r"g_x_tr\s+(-?\d+\.\d+)", s).group(1))
    mine = po.regress_panel_diff(df, "y", "g", "tr").set_index("term")
    res_pl, _ = _run_analysis("regress-panel-diff y g tr", df, "polars")
    assert np.isclose(mine.loc["g_x_tr", "coef"], emu_atet, atol=1e-3)
    assert np.allclose(res_pl.set_index("term")["coef"], mine["coef"])


@pytest.mark.parametrize("script,new", [
    ("regress-panel-predict y x1, predicted(yhat) residuals(res)", ["yhat", "res"]),
    ("regress-panel-predict y x1, re predicted(yhat)", ["yhat"]),
    ("regress-panel-predict y x1, pooled predicted(yhat) residuals(res)", ["yhat", "res"]),
    ("regress-panel-predict y x1, predicted(yhat) effects(eff)", ["yhat", "eff"]),
])
def test_regress_panel_predict_matches_emulator(script, new):
    pytest.importorskip("linearmodels")
    rng = np.random.default_rng(0)
    rows = []
    for i in range(50):
        fe = rng.normal(0, 1)
        for t in range(5):
            x1 = rng.normal(0, 1)
            rows.append({"unit_id": i, "tid": t, "x1": x1,
                         "y": 1 + 0.8 * x1 + fe + rng.normal(0, 0.5)})
    df = pd.DataFrame(rows)
    emu = _emu_after(script, df)
    out_pd = T.run(script, {"df": df}, "pandas")
    out_pl = T.run(script, {"df": df}, "polars").to_pandas()
    assert [c for c in out_pd.columns if c not in df.columns] == new
    for c in new:
        assert np.allclose(out_pd[c].dropna(), emu[c].dropna(), atol=1e-6), c
        assert np.allclose(out_pd[c].dropna(), out_pl[c].dropna(), atol=1e-6), c


def test_ivregress_predict_matches_emulator():
    pytest.importorskip("statsmodels.api")
    from m2py_runtime import pandas_ops as po
    rng = np.random.default_rng(0)
    n = 400
    z1, z2, u = rng.normal(0, 1, n), rng.normal(0, 1, n), rng.normal(0, 1, n)
    endo = 0.5 * z1 + 0.3 * z2 + u + rng.normal(0, 0.3, n)
    df = pd.DataFrame({"y": 1 + 1.2 * endo + 0.4 * u + rng.normal(0, 0.3, n),
                       "endo": endo, "z1": z1, "z2": z2})
    script = "ivregress-predict y (endo = z1 z2), predicted(yhat) residuals(res)"
    emu = _emu_after(script, df)
    new = [c for c in emu.columns if c not in df.columns]
    out_pd = T.run(script, {"df": df}, "pandas")
    out_pl = T.run(script, {"df": df}, "polars").to_pandas()
    assert new == ["yhat", "res"]
    for c in new:
        assert np.allclose(out_pd[c].dropna(), emu[c].dropna())
        assert np.allclose(out_pd[c].dropna(), out_pl[c].dropna())


def test_mlogit_predict_matches_emulator():
    pytest.importorskip("statsmodels.api")
    rng = np.random.default_rng(0)
    n = 400
    x1 = rng.normal(0, 1, n)
    eta = np.column_stack([np.zeros(n), 0.5 + 0.8 * x1, -0.3 + 0.5 * x1])
    probs = np.exp(eta) / np.exp(eta).sum(1, keepdims=True)
    cat = np.array([rng.choice(3, p=probs[i]) for i in range(n)])
    df = pd.DataFrame({"cat": cat, "x1": x1})
    script = "mlogit-predict cat x1, probabilities(p)"
    emu = _emu_after(script, df)
    new = [c for c in emu.columns if c not in df.columns]
    out_pd = T.run(script, {"df": df}, "pandas")
    out_pl = T.run(script, {"df": df}, "polars").to_pandas()
    assert new == ["p_0", "p_1", "p_2"]
    for c in new:
        assert np.allclose(out_pd[c].dropna(), emu[c].dropna())
        assert np.allclose(out_pd[c].dropna(), out_pl[c].dropna())


def test_ivregress_matches_emulator():
    pytest.importorskip("statsmodels.api")
    from m2py_runtime import pandas_ops as po
    rng = np.random.default_rng(0)
    n = 400
    z1, z2, u = rng.normal(0, 1, n), rng.normal(0, 1, n), rng.normal(0, 1, n)
    endo = 0.5 * z1 + 0.3 * z2 + u + rng.normal(0, 0.3, n)
    df = pd.DataFrame({"y": 1 + 1.2 * endo + 0.4 * u + rng.normal(0, 0.3, n),
                       "endo": endo, "z1": z1, "z2": z2})
    emu = _emu_coef_table("ivregress", df,
                          {"dep": "y", "exog": [], "endog": ["endo"],
                           "instruments": ["z1", "z2"], "method": "tsls"}, {})
    mine = po.ivregress(df, "y", [], ["endo"], ["z1", "z2"]).set_index("term")["coef"]
    res_pl, _ = _run_analysis("ivregress y (endo = z1 z2)", df, "polars")
    assert "endo" in emu
    for term, c in emu.items():
        assert np.isclose(mine[term], c, atol=1e-3), term
    assert np.allclose(res_pl.set_index("term").loc[mine.index, "coef"], mine.values)


def _survival_df():
    rng = np.random.default_rng(0)
    n = 300
    x1 = rng.normal(0, 1, n)
    dur = rng.exponential(np.exp(-0.5 * x1)) * 10 + 0.1
    event = (rng.random(n) < 0.7).astype(int)
    return pd.DataFrame({"event": event, "tid": dur, "x1": x1})


def test_cox_matches_emulator():
    pytest.importorskip("lifelines")
    from m2py_runtime import pandas_ops as po
    df = _survival_df()
    m2py.M2PY_DISCLOSURE_CONTROL = "0"
    emu = m2py.MicroInterpreter(metadata_path=None).survival_handler.execute(
        "cox", df, ["event", "tid", "x1"], {})
    emu_df = emu[0] if isinstance(emu, tuple) else emu          # summary.T: covars as cols
    mine = po.cox(df, "event", "tid", ["x1"]).set_index("term")
    res_pl, _ = _run_analysis("cox event tid x1", df, "polars")
    assert np.isclose(mine.loc["x1", "coef"], float(emu_df.loc["coef", "x1"]))
    assert np.isclose(res_pl.set_index("term").loc["x1", "coef"], mine.loc["x1", "coef"])


def test_kaplan_meier_matches_lifelines():
    lifelines = pytest.importorskip("lifelines")
    from m2py_runtime import pandas_ops as po
    df = _survival_df()
    kmf = lifelines.KaplanMeierFitter()
    kmf.fit(df["tid"], df["event"])
    truth = kmf.survival_function_.iloc[:, 0].to_numpy()
    mine = po.kaplan_meier(df, "event", "tid")
    res_pl, _ = _run_analysis("kaplan-meier event tid", df, "polars")
    assert np.allclose(mine["survival"].to_numpy(), truth)
    assert np.allclose(res_pl["survival"].to_numpy(), truth)


def test_weibull_matches_emulator_params():
    pytest.importorskip("lifelines")
    from m2py_runtime import pandas_ops as po
    df = _survival_df()
    m2py.M2PY_DISCLOSURE_CONTROL = "0"
    emu = m2py.MicroInterpreter(metadata_path=None).survival_handler.execute(
        "weibull", df, ["event", "tid"], {})
    emu_df = emu[0] if isinstance(emu, tuple) else emu
    # emulator returns the full Weibull summary; the coef row holds lambda_/rho_
    emu_lambda = float(emu_df.iloc[0, 0])
    emu_rho = float(emu_df.iloc[0, 1])
    mine = po.weibull(df, "event", "tid")
    assert np.isclose(mine["lambda"].iloc[0], emu_lambda, atol=1e-3)
    assert np.isclose(mine["rho"].iloc[0], emu_rho, atol=1e-3)


@pytest.mark.parametrize("reg,dep", [
    ("regress", "y"), ("logit", "binv"), ("probit", "binv"), ("poisson", "cnt"),
])
def test_coefplot_matches_emulator_fit(reg, dep):
    pytest.importorskip("statsmodels.api")
    import m2py as _m
    rng = np.random.default_rng(0)
    n = 200
    x1, x2 = rng.normal(0, 1, n), rng.normal(0, 1, n)
    df = pd.DataFrame({
        "x1": x1, "x2": x2,
        "y": 2 + 1.5 * x1 - 0.7 * x2 + rng.normal(0, 1, n),
        "binv": (0.5 * x1 + rng.normal(0, 1, n) > 0).astype(int),
        "cnt": rng.poisson(np.exp(0.3 + 0.2 * x1)),
    })
    it = _m.MicroInterpreter(metadata_path=None)
    model, _, _, _ = it.reg_engine._fit_simple(reg, df, [dep, "x1", "x2"], {})
    params = model.params.drop("const", errors="ignore")
    ci = model.conf_int().drop("const", errors="ignore")
    exp_x = params.values.tolist()
    exp_eplus = [h - c for c, h in zip(exp_x, ci.iloc[:, 1].tolist())]

    script = f"coefplot {reg} {dep} x1 x2"
    f_pd = _run_fig(script, df, "pandas")
    f_pl = _run_fig(script, df, "polars")
    t = f_pd.data[0]
    assert np.allclose(list(t.x), exp_x)
    assert list(t.y) == list(params.index)
    assert np.allclose(list(t.error_x.array), exp_eplus)
    assert np.allclose(list(t.x), list(f_pl.data[0].x))      # backend parity


def test_coefplot_requires_reg_command():
    # `coefplot y x1 x2` parses reg_cmd='y' (no reg verb) -> flagged, not emitted
    assert T.unsupported("coefplot y x1 x2") == ["coefplot y x1 x2"]
    assert "UNTRANSLATED" in T.translate("coefplot y x1 x2", backend="polars",
                                         source_path=None)


@pytest.mark.parametrize("stat", ["mean", "median", "sum", "sd", "min", "max"])
@pytest.mark.parametrize("over", [None, "kommune"])
def test_barchart_all_stats_match_emulator(stat, over):
    import m2py as _m
    _m.M2PY_DISCLOSURE_CONTROL = "0"
    df = pd.DataFrame({"inntekt": [10.0, 20, 30, 40, 50, 60],
                       "kommune": [1, 1, 2, 2, 3, 3]})
    opts = {"over": over} if over else {}
    script = f"barchart ({stat}) inntekt" + (f", over({over})" if over else "")
    emu = _m.PlotHandler().execute("barchart", df, {"stat": stat, "vars": ["inntekt"]}, opts)
    fpd = _run_fig(script, df, "pandas")
    fpl = _run_fig(script, df, "polars")
    assert _fig_equal(fpd, emu), f"{script}: differs from emulator"
    assert _fig_equal(fpd, fpl), f"{script}: pandas vs polars differ"


def test_bare_stat_flag_is_flagged_not_applied():
    # `barchart x, mean` (bare flag) -> emulator ignores it; translator flags it
    assert T.unsupported("barchart inntekt, mean") == ["barchart inntekt, mean"]
    assert T.unsupported("barchart (mean) inntekt") == []   # parenthesised works


def test_plot_is_terminal_and_writes_html_in_file_mode():
    # plots don't change the working frame; file mode emits a write_html call
    code = T.translate("histogram inntekt\nkeep if inntekt > 500",
                       backend="polars", source_path="extract")
    assert 'fig_1.write_html("plot_1.html")' in code
    assert "ops.keep(lf" in code  # pipeline continues after the plot


def test_nonstandard_bins_option_is_flagged():
    # microdata's option is bin(); 'bins(...)' is not honoured by the emulator,
    # so it must be surfaced, not silently defaulted.
    assert T.unsupported("histogram inntekt, bins(20)") == ["histogram inntekt, bins(20)"]


_FUNC_DF = pd.DataFrame({"a": [1.0, 2, 3, 4, 5], "b": [2.0, 3, 1, 5, 4],
                         "c": [10.0, 20, 30, 40, 50], "s": ["Ab", " cD ", "eF", "Gh", "iJ"],
                         "d": [18262, 18627, 18993, 19358, 19723]})


@pytest.mark.parametrize("expr", [
    # scipy distributions (handled by the pandas-eval fallback)
    "chi2tail(2, a)", "ttail(10, a)", "normal(a)", "normalden(a)",
    "binomialtail(10, 3, 0.5)", "invchi2tail(2, 0.5)",
    # row-wise (native)
    "rowmean(a,b,c)", "rowmax(a,b,c)", "rowmin(a,b,c)", "rowtotal(a,b,c)",
    "rowmissing(a,b)", "rowstd(a,b,c)", "rowmedian(a,b,c)", "rowvalid(a,b)",
    # dates (fallback)
    "year(d)", "month(d)", "quarter(d)", "week(d)", "dow(d)",
    # strings (native + fallback)
    "lower(s)", "upper(s)", "trim(s)", "length(s)", "startswith(s,'e')", "substr(s,1,1)",
    # math (native + fallback)
    "acos(a/10)", "atan(a)", "logit(a/10)", "comb(5, a)", "lnfactorial(a)",
    "inrange(a,2,4)", "inlist(a,1,3,5)", "sqrt(a)", "ln(a)",
])
def test_all_functions_match_emulator(expr):
    df = _FUNC_DF

    def emu(e):
        m2py.M2PY_DISCLOSURE_CONTROL = "0"
        it = m2py.MicroInterpreter(metadata_path=None)
        it.datasets["df"] = df.copy()
        it.active_name = "df"
        it._execute_instruction(it.parser.parse_line(f"generate r = {e}"))
        return it.datasets["df"]["r"]

    def norm(x):
        x = pd.Series(x)
        num = pd.to_numeric(x, errors="coerce")
        if num.notna().sum() >= x.notna().sum():
            return [round(float(v), 6) if pd.notna(v) else None for v in num]
        return [str(v) for v in x]

    code = T.translate(f"generate r = {expr}", backend="polars", source_path=None)
    assert "UNTRANSLATED" not in code, code
    emu_r = norm(emu(expr))
    pd_r = norm(T.run(f"generate r = {expr}", {"df": df}, "pandas")["r"])
    pl_r = norm(T.run(f"generate r = {expr}", {"df": df}, "polars").to_pandas()["r"])
    assert pd_r == emu_r, f"pandas != emulator for {expr}"
    assert pl_r == emu_r, f"polars != emulator for {expr}"


def test_multi_dataset_use_switching_matches_emulator():
    # `use` keeps existing data in the emulator, so it compares apples-to-apples.
    A = pd.DataFrame({"x": [1.0, 2, 3, 4, 5], "g": [1, 1, 2, 2, 1]})
    B = pd.DataFrame({"y": [10.0, 20, 30, 40], "g": [1, 1, 2, 2]})
    script = ("use A\ngenerate x2 = x * 2\nuse B\n"
              "collapse (mean) y -> my, by(g)\nuse A\nkeep if x > 2")

    m2py.M2PY_DISCLOSURE_CONTROL = "0"
    it = m2py.MicroInterpreter(metadata_path=None)
    it.datasets["A"], it.datasets["B"] = A.copy(), B.copy()
    it.active_name = "A"
    for ln in script.splitlines():
        it._execute_instruction(it.parser.parse_line(ln))
    emu = it.datasets["A"]                       # final active dataset

    out_pd = T.run(script, {"A": A, "B": B}, "pandas", active="A")
    out_pl = T.run(script, {"A": A, "B": B}, "polars", active="A").to_pandas()
    assert _reshape_norm(emu).equals(_reshape_norm(out_pd))   # commands hit dataset A
    assert _reshape_norm(out_pd).equals(_reshape_norm(out_pl))
    assert "x2" in out_pd.columns and (out_pd["x"] > 2).all()


def test_create_dataset_clone_and_merge_known_datasets():
    # create-dataset loads the named extract; clone copies; merge references the
    # already-created dataset variable (no parquet load).
    main = pd.DataFrame({"g": [1, 2, 3], "v": [10.0, 20, 30]})
    look = pd.DataFrame({"g": [1, 2, 3], "navn": ["a", "b", "c"]})
    script = ("create-dataset main\ncreate-dataset look\n"
              "use main\nmerge look on g\ngenerate vv = v * 2")
    code = T.translate(script, backend="pandas", source_path=None)
    assert "df_main = ops.merge(df_main, df_look" in code   # variable, not a load
    out = T.run(script, {"main": main, "look": look}, "pandas", active="main")
    assert list(out.columns) == ["g", "v", "navn", "vv"]
    assert out["vv"].tolist() == [20.0, 40.0, 60.0]


def test_for_loop_and_let_match_emulator():
    df = pd.DataFrame({"a": [1.0, 2, 3, 4], "g": [1, 1, 2, 2]})
    script = ("let k = 100\n"
              "for y in 1 2 3\n"
              "generate x$y = a + $y\n"
              "end\n"
              "generate big = a * $k\n"
              "keep if a > 1")

    m2py.M2PY_DISCLOSURE_CONTROL = "0"
    it = m2py.MicroInterpreter(metadata_path=None)
    it.datasets["df"] = df.copy()
    it.active_name = "df"
    it.run_script(script)
    emu = it.datasets["df"]

    # the loop unrolls to x1/x2/x3 and let resolves $k -> 100, before translating
    flat = T._expand_loops(script)
    assert "generate x1 = a + 1" in flat and "generate x3 = a + 3" in flat
    assert "big = a * 100" in flat and "for " not in flat and "let " not in flat

    out_pd = T.run(script, {"df": df}, "pandas")
    out_pl = T.run(script, {"df": df}, "polars").to_pandas()
    assert _reshape_norm(emu).equals(_reshape_norm(out_pd))
    assert _reshape_norm(out_pd).equals(_reshape_norm(out_pl))
    assert set(["x1", "x2", "x3", "big"]).issubset(out_pd.columns)


def test_labels_are_noop_keeping_codes_like_emulator():
    df = pd.DataFrame({"k": [1, 2, 1, 2, 1], "x": [10.0, 20, 30, 40, 50]})
    script = ('define-labels kjonn 1 "Mann" 2 "Kvinne"\n'
              "assign-labels k kjonn\ncollapse (mean) x -> mx, by(k)")
    assert T.unsupported(script) == []                  # labels translate (no flag)

    m2py.M2PY_DISCLOSURE_CONTROL = "0"
    it = m2py.MicroInterpreter(metadata_path=None)
    it.datasets["df"] = df.copy()
    it.active_name = "df"
    for ln in script.splitlines():
        it._execute_instruction(it.parser.parse_line(ln))
    emu = it.datasets["df"]                              # data keeps codes (k=1,2)

    out_pd = T.run(script, {"df": df}, "pandas")
    out_pl = T.run(script, {"df": df}, "polars").to_pandas()
    assert _reshape_norm(emu).equals(_reshape_norm(out_pd))   # collapse by code matches
    assert _reshape_norm(out_pd).equals(_reshape_norm(out_pl))
    assert set(out_pd["k"]) == {1, 2}                   # codes, not label strings


def test_clone_variables_and_units_match_emulator():
    df = pd.DataFrame({"unit_id": [1, 1, 2, 2, 3], "a": [10.0, 20, 30, 40, 50],
                       "b": [1, 2, 3, 4, 5]})

    def emu(script, ds="df"):
        m2py.M2PY_DISCLOSURE_CONTROL = "0"
        it = m2py.MicroInterpreter(metadata_path=None)
        it.datasets["df"] = df.copy()
        it.active_name = "df"
        for ln in script.splitlines():
            it._execute_instruction(it.parser.parse_line(ln))
        return it.datasets[ds]

    # clone-variables: each token -> <token>_clone
    e = emu("clone-variables a b")
    m = T.run("clone-variables a b", {"df": df}, "pandas")
    mp = T.run("clone-variables a b", {"df": df}, "polars").to_pandas()
    assert list(m.columns) == ["unit_id", "a", "b", "a_clone", "b_clone"]
    assert _reshape_norm(e).equals(_reshape_norm(m))
    assert _reshape_norm(m).equals(_reshape_norm(mp))

    # clone-variables with prefix
    e = emu("clone-variables a, prefix(ny_)")
    m = T.run("clone-variables a, prefix(ny_)", {"df": df}, "pandas")
    assert "ny_a" in m.columns and _reshape_norm(e).equals(_reshape_norm(m))

    # clone-units: new dataset = deduped entity key
    script = "use df\nclone-units df units\nuse units"
    e = emu(script, "units")
    out = T.run(script, {"df": df}, "pandas", active="df")
    assert out["unit_id"].tolist() == [1, 2, 3]
    assert _reshape_norm(e).equals(_reshape_norm(out))


def test_session_verbs_not_flagged():
    for v in ("create-dataset A", "use A", "clone-dataset A B",
              "rename-dataset A B", "delete-dataset A"):
        assert T.unsupported(v) == [], v


def test_unknown_function_is_flagged():
    # a name that is NOT a microdata function -> can't compile or fall back
    script = "generate w = totallymadeupfn(a)"
    assert "UNTRANSLATED" in T.translate(script, backend="polars", source_path=None)
    assert T.unsupported(script) == [script]


def _stats_oracle(cmd, df, args, opts):
    m2py.M2PY_DISCLOSURE_CONTROL = "0"
    return m2py.MicroInterpreter(metadata_path=None).stats_engine.execute(
        cmd, df, args, opts)


_MISS_DF = pd.DataFrame({"g": [1, 1, 2, 2, 2, 3, 3, np.nan], "h": [1, 2, 1, 2, 1, 2, 1, 1]})


@pytest.mark.parametrize("missing,keeps_nan", [
    (False, False),    # default DROPS missing (one-way, now consistent w/ two-way)
    (True, True),      # `missing` KEEPS it
])
def test_tabulate_oneway_missing_matches_emulator(missing, keeps_nan):
    opts = {"missing": True} if missing else {}
    emu = _stats_oracle("tabulate", _MISS_DF, ["g"], opts)
    emu_counts = {("NaN" if pd.isna(k) else k): int(v)
                  for k, v in emu.items() if k != "Total"}
    res, _ = _run_analysis("tabulate g" + (", missing" if missing else ""),
                           _MISS_DF, "pandas")
    mine = {("NaN" if pd.isna(r["g"]) else r["g"]): int(r["n"])
            for _, r in res.iterrows()}
    assert mine == emu_counts
    assert ("NaN" in mine) == keeps_nan


def test_tabulate_twoway_default_drops_missing_like_emulator():
    emu = _stats_oracle("tabulate", _MISS_DF, ["g", "h"], {})
    expected = {(gi, hi): int(emu.loc[gi, hi]) for gi in emu.index if gi != "Total"
                for hi in emu.columns if hi != "Total" and int(emu.loc[gi, hi]) > 0}
    res, _ = _run_analysis("tabulate g h", _MISS_DF, "pandas")
    mine = {(r["g"], r["h"]): int(r["n"]) for _, r in res.iterrows()}
    assert mine == expected                       # non-NaN cells match; NaN dropped


@pytest.mark.parametrize("opts,kw", [
    ({}, {}),
    ({"pairwise": True}, {"pairwise": True}),
    ({"covariance": True}, {"covariance": True}),
])
def test_correlate_matches_emulator(opts, kw):
    from m2py_runtime import pandas_ops as po
    df = pd.DataFrame({"a": [1.0, 2, 3, 4, 5, np.nan], "b": [2.0, 4, 5, 4, 5, 6],
                       "c": [1.0, 1, 2, np.nan, 3, 3]})
    emu = _stats_oracle("correlate", df, ["a", "b", "c"], opts)
    mine = po.correlate(df, ["a", "b", "c"], **kw).set_index("variable")
    assert np.allclose(emu.values, mine.loc[emu.index, emu.columns].values, equal_nan=True)


def test_normaltest_ci_anova_match_emulator():
    pytest.importorskip("scipy")
    from m2py_runtime import pandas_ops as po
    rng = np.random.default_rng(0)
    n = 300
    df = pd.DataFrame({"inntekt": rng.normal(5, 1, n), "formue": rng.exponential(2, n),
                       "kjonn": rng.integers(1, 3, n)})
    eng = m2py.MicroInterpreter(metadata_path=None).stats_engine
    m2py.M2PY_DISCLOSURE_CONTROL = "0"

    # normaltest
    emu = eng.execute("normaltest", df, ["inntekt", "formue"], {})
    mine, _ = _run_analysis("normaltest inntekt formue", df, "pandas")
    assert np.allclose(emu["Statistic"].astype(float).fillna(0),
                       mine["statistic"].astype(float).fillna(0), atol=1e-6)
    minep, _ = _run_analysis("normaltest inntekt formue", df, "polars")
    assert np.allclose(mine["statistic"].fillna(0), minep["statistic"].fillna(0))

    # ci (level 99)
    emu = eng.execute("ci", df, ["inntekt"], {"level": "99"})
    mine, _ = _run_analysis("ci inntekt, level(99)", df, "pandas")
    assert np.allclose([emu["Mean"].iloc[0], emu["CI_low"].iloc[0], emu["CI_high"].iloc[0]],
                       [mine["mean"].iloc[0], mine["ci_low"].iloc[0], mine["ci_high"].iloc[0]])

    # anova
    emu = eng.execute("anova", df, ["inntekt", "kjonn"], {})
    mine, _ = _run_analysis("anova inntekt kjonn", df, "pandas")
    mf = float(mine[mine["term"].str.contains("kjonn")]["F"].iloc[0])
    assert np.isclose(float(emu["F"].iloc[0]), mf, atol=1e-4)


def test_panel_tables_match_emulator():
    from m2py_runtime import pandas_ops as po
    rng = np.random.default_rng(0)
    rows = []
    for i in range(60):
        for t in (2018, 2019, 2020):
            rows.append({"unit_id": i, "tid": t, "inntekt": rng.normal(5, 1),
                         "kjonn": int(rng.integers(1, 3))})
    df = pd.DataFrame(rows)
    eng = m2py.MicroInterpreter(metadata_path=None).stats_engine
    m2py.M2PY_DISCLOSURE_CONTROL = "0"

    # summarize-panel: emulator returns multiindex (var, stat) indexed by tid
    emu = eng.execute("summarize-panel", df, ["inntekt"], {})
    mine, _ = _run_analysis("summarize-panel inntekt", df, "pandas")
    minep, _ = _run_analysis("summarize-panel inntekt", df, "polars")
    mi = mine.set_index("tid")
    for t in (2018, 2019, 2020):
        assert np.isclose(mi.loc[t, "mean"], emu.loc[t, ("inntekt", "mean")])
        assert np.isclose(mi.loc[t, "std"], emu.loc[t, ("inntekt", "std")])
    assert np.allclose(mine.sort_values("tid")["mean"], minep.sort_values("tid")["mean"])

    # tabulate-panel: counts per (kjonn, tid) == crosstab(kjonn, tid)
    emu = eng.execute("tabulate-panel", df, ["kjonn"], {})
    mine, _ = _run_analysis("tabulate-panel kjonn", df, "pandas")
    mc = {(int(r["kjonn"]), int(r["tid"])): int(r["n"]) for _, r in mine.iterrows()}
    ec = {(int(k), int(t)): int(emu.loc[k, t]) for k in emu.index for t in emu.columns}
    assert mc == ec


def test_transitions_panel_matches_emulator():
    from m2py_runtime import pandas_ops as po
    rng = np.random.default_rng(0)
    rows = []
    for i in range(80):
        s = int(rng.integers(1, 4))
        for t in (2018, 2019, 2020):
            s = int(np.clip(s + rng.integers(-1, 2), 1, 3))
            rows.append({"unit_id": i, "tid": t, "status": s})
    df = pd.DataFrame(rows)
    m2py.M2PY_DISCLOSURE_CONTROL = "0"
    emu = m2py.MicroInterpreter(metadata_path=None).stats_engine.execute(
        "transitions-panel", df, ["status"], {})           # crosstab(from, to, norm=index)
    mine = po.transitions_panel(df, ["status"])
    minep, _ = _run_analysis("transitions-panel status", df, "polars")
    for _, r in mine.iterrows():
        assert np.isclose(r["prob"], emu.loc[r["from"], r["to"]])
    assert np.allclose(mine.sort_values(["from", "to"])["prob"].to_numpy(),
                       minep.sort_values(["from", "to"])["prob"].to_numpy())


def test_hausman_matches_emulator():
    pytest.importorskip("linearmodels")
    import re
    from m2py_runtime import pandas_ops as po
    rng = np.random.default_rng(0)
    rows = []
    for i in range(50):
        fe = rng.normal(0, 1)
        for t in range(5):
            x1 = rng.normal(0, 1)
            rows.append({"unit_id": i, "tid": t, "x1": x1,
                         "y": 1 + 0.8 * x1 + fe + rng.normal(0, 0.5)})
    df = pd.DataFrame(rows)
    m2py.M2PY_DISCLOSURE_CONTROL = "0"
    out = m2py.MicroInterpreter(metadata_path=None).reg_engine.execute("hausman", df, ["y", "x1"], {})
    s = out[0] if isinstance(out, tuple) else str(out)
    emu_chi2 = float(re.search(r"chi2=(-?\d+\.\d+)", s).group(1))
    mine, _ = _run_analysis("hausman y x1", df, "pandas")
    minep, _ = _run_analysis("hausman y x1", df, "polars")
    assert np.isclose(mine["statistic"].iloc[0], emu_chi2, atol=1e-3)
    assert np.isclose(mine["statistic"].iloc[0], minep["statistic"].iloc[0])


def test_tabulate_percentages_are_correct():
    # x in {1,2}, y in {1,2}; counts (1,1)=2 (1,2)=1 (2,1)=1 (2,2)=1, total 5
    df = pd.DataFrame({"x": [1, 1, 1, 2, 2], "y": [1, 1, 2, 1, 2]})
    res, _ = _run_analysis("tabulate x y, cellpct rowpct colpct", df, "pandas")
    row = res[(res["x"] == 1) & (res["y"] == 1)].iloc[0]
    assert np.isclose(row["cellpct"], 40.0)        # 2/5
    assert np.isclose(row["rowpct"], 200 / 3)      # 2/3 of x==1
    assert np.isclose(row["colpct"], 200 / 3)      # 2/3 of y==1
    # each percentage column sums correctly
    assert np.isclose(res["cellpct"].sum(), 100.0)


def test_tabulate_chi2_matches_scipy():
    stats = pytest.importorskip("scipy.stats")
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"x": rng.integers(1, 4, 200), "y": rng.integers(1, 3, 200)})
    res, _ = _run_analysis("tabulate x y, chi2", df, "polars")
    chi2, p, dof, _ = stats.chi2_contingency(pd.crosstab(df["x"], df["y"]))
    assert np.isclose(res["chi2"].iloc[0], chi2)
    assert np.isclose(res["chi2_p"].iloc[0], p)
    assert res["chi2_dof"].iloc[0] == dof


def test_tabulate_top_bottom_positional():
    # positional = first/last n categories in value-sorted order (NOT by count).
    # k sorted ascending is 1,2,3,4 regardless of frequency.
    df = pd.DataFrame({"k": [1] * 10 + [2] * 5 + [3] * 3 + [4] * 1})
    top, _ = _run_analysis("tabulate k, top(2)", df, "pandas")
    assert top["k"].tolist() == [1, 2]              # first two values
    bot, _ = _run_analysis("tabulate k, bottom(2)", df, "pandas")
    assert bot["k"].tolist() == [3, 4]              # last two values
    bare, _ = _run_analysis("tabulate k, top", df, "pandas")  # bare -> default 10
    assert len(bare) == 4


def test_tabulate_top_two_way_keeps_first_var_categories():
    # two-way top(1): keep all rows of the first var's first category
    df = pd.DataFrame({"x": [1, 1, 2, 3], "y": [1, 2, 1, 2]})
    res, _ = _run_analysis("tabulate x y, top(1)", df, "pandas")
    assert set(res["x"]) == {1}                     # only x's first category
    assert sorted(res["y"]) == [1, 2]


def test_summarize_gini_matches_emulator_definition():
    df = pd.DataFrame({"inntekt": [10.0, 20, 30, 40, 100]})
    res, _ = _run_analysis("summarize inntekt, gini iqr", df, "pandas")
    assert np.isclose(res["gini"].iloc[0], m2py.AGG_STAT_ALIAS["gini"](df["inntekt"]))
    assert np.isclose(res["iqr"].iloc[0], m2py.AGG_STAT_ALIAS["iqr"](df["inntekt"]))


_SUM_DF = pd.DataFrame({
    "inntekt": [10.0, 20, 30, 40, 100, 5, 7, 9],
    "alder": [20.0, 30, 40, 50, 60, 25, 35, 45],
    "kjonn": [1, 1, 1, 2, 2, 2, 1, 2],
})

# emulator stat label -> my tidy column, for the two paths
_NOBY_MAP = {"mean": "Gj.snitt", "std": "Std.avvik", "count": "Antall",
             "p1": "1%", "p25": "25%", "p50": "50%", "p75": "75%", "p99": "99%"}
_BY_STATS = ["mean", "std", "min", "max", "count"]


def _summarize_oracle(df, args, opts):
    m2py.M2PY_DISCLOSURE_CONTROL = "0"
    return m2py.MicroInterpreter(metadata_path=None).stats_engine.execute(
        "summarize", df, args, opts)


def test_summarize_ungrouped_matches_emulator():
    # ungrouped path: mean/std/count + percentiles 1/25/50/75/99 (no min/max)
    emu = _summarize_oracle(_SUM_DF, ["inntekt", "alder"], {})
    for backend in ("pandas", "polars"):
        res, _ = _run_analysis("summarize inntekt alder", _SUM_DF, backend)
        res = res.set_index("variable")
        for v in ("inntekt", "alder"):
            for mine, emu_col in _NOBY_MAP.items():
                assert np.isclose(res.loc[v, mine], emu.loc[v, emu_col]), (backend, v, mine)
        assert "min" not in res.columns and "max" not in res.columns


def test_summarize_grouped_matches_emulator():
    # grouped path: mean/std/min/max/count (no percentiles)
    emu = _summarize_oracle(_SUM_DF, ["inntekt"], {"by": "kjonn"})
    for backend in ("pandas", "polars"):
        res, _ = _run_analysis("summarize inntekt, by(kjonn)", _SUM_DF, backend)
        res = res.set_index("kjonn")
        for g in (1, 2):
            for stat in _BY_STATS:
                assert np.isclose(res.loc[g, stat], emu.loc[g, ("inntekt", stat)]), (backend, g, stat)
        assert not any(c.startswith("p") and c[1:].isdigit() for c in res.columns)


def test_summarize_default_all_numeric_vars():
    # no var list -> all numeric columns (kjonn is numeric here, so included)
    res, _ = _run_analysis("summarize", _SUM_DF, "pandas")
    assert set(res["variable"]) == {"inntekt", "alder", "kjonn"}


def test_summarize_if_condition_matches_emulator():
    # `summarize x if cond` filters rows before computing — and must not change
    # the working frame.
    emu = _summarize_oracle(_SUM_DF[_SUM_DF["alder"] > 35], ["inntekt"], {})
    for backend in ("pandas", "polars"):
        res, final = _run_analysis("summarize inntekt if alder > 35", _SUM_DF, backend)
        res = res.set_index("variable")
        assert np.isclose(res.loc["inntekt", "count"], emu.loc["inntekt", "Antall"])
        assert np.isclose(res.loc["inntekt", "mean"], emu.loc["inntekt", "Gj.snitt"])
        assert len(final) == len(_SUM_DF)            # working frame unchanged


@pytest.mark.parametrize("script", [
    "tabulate g, nolabels",        # formatting option not implemented
    "tabulate g, rowsort",         # sort option not implemented
    "destring x, dpcomma",         # decimal-comma changes values
    "correlate a b, sig",          # significance text table not implemented
    "barchart x, mean",            # bare stat flag (use parenthesised (mean))
    "piechart x, percent",         # bare percent flag (use (percent))
    "scatter a b, lfit",           # regression-line overlay (scatter not mopped up)
])
def test_unhandled_options_flagged_not_silently_dropped(script):
    code = T.translate(script, backend="polars", source_path=None)
    assert "UNTRANSLATED (unhandled option" in code, code
    assert T.unsupported(script) == [script]


def test_handled_options_not_flagged():
    for script in ["summarize x, gini iqr", "tabulate x g", "merge l on k, outer_join"]:
        assert T.unsupported(script) == [], script


def test_run_helper_both_backends():
    df = pd.DataFrame({"kommune": [1, 2, 1, 2], "inntekt": [10.0, 20, 30, 40]})
    script = "collapse (mean) inntekt -> snitt, by(kommune)"
    out_pl = T.run(script, {"df": df}, backend="polars").to_pandas()
    out_pd = T.run(script, {"df": df}, backend="pandas")
    _assert_same(out_pl, out_pd, "run", script)
    assert sorted(out_pd["snitt"].tolist()) == [20.0, 30.0]
