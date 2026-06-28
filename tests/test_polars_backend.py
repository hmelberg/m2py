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


def test_unsupported_expression_is_marked_not_silently_wrong():
    # a microdata function the polars compiler doesn't implement -> UNTRANSLATED,
    # never emitted as incorrect polars.
    script = "generate w = wordcount(a)"
    code = T.translate(script, backend="polars", source_path=None)
    assert "UNTRANSLATED" in code
    assert T.unsupported(script) == ["generate w = wordcount(a)"]


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
    "correlate a b, covariance",   # covariance variant not implemented
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
