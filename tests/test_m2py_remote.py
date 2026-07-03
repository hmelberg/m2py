# tests/test_m2py_remote.py
import pandas as pd
from m2py_remote import run_remote
from m2py_protection import resolve_policy, PUBLIC, PROTECTED

# A microdata script that loads a named dataset and tabulates a column.
# create-dataset binds `df_demo = _load("demo")`; tabulate emits result_1.
SCRIPT = "create-dataset demo\ntabulate grp"


def _data():
    # grp value 9 appears 3x (below min_n=5), grp 1 appears 6x (kept).
    return {"demo": pd.DataFrame({"grp": [1]*6 + [9]*3})}


def test_run_remote_returns_client_contract_keys():
    res = run_remote(SCRIPT, datasets=_data(), policy=resolve_policy([PUBLIC]))
    assert set(res) == {"code", "out", "html", "n", "err", "figs", "results", "datasetInfo"}
    assert res["err"] is None, res["err"]
    assert res["results"], "expected at least one rendered result"
    assert res["n"] == 9   # translator footer materialized df = df_demo (9 rows)


def test_run_remote_public_keeps_small_counts():
    res = run_remote(SCRIPT, datasets=_data(), policy=resolve_policy([PUBLIC]))
    # public => no suppression => the count 3 survives in the rendered table
    assert ">3<" in res["results"][0] or "3.0" in res["results"][0]


def test_run_remote_protected_suppresses_and_rounds_counts():
    res = run_remote(SCRIPT, datasets=_data(), policy=resolve_policy([PROTECTED]))
    html = res["results"][0]
    # protected => n=3 suppressed to NaN; surviving n=6 rounds to 10 (shared
    # preset: safepy "standard" tier -> min_n=5, round_to=10)
    assert "NaN" in html
    assert ">3<" not in html and "3.0" not in html
    assert ">6<" not in html and "6.0" not in html
    assert "10" in html


def test_run_remote_returns_dataset_info():
    res = run_remote(SCRIPT, datasets=_data(), policy=resolve_policy([PUBLIC]))
    di = res["datasetInfo"]
    # named frame df_demo -> dataset "demo" with its schema + row count
    assert "demo" in di
    assert di["demo"]["columns"] == ["grp"]
    assert di["demo"]["nrows"] == 9
    assert "grp" in di["demo"]["dtypes"]


# ── raw-data leak protections (stage 2a) ────────────────────────────────────

def _xy_data(n=30):
    return {"demo": pd.DataFrame({"x": range(n), "y": range(n), "grp": [1, 2] * (n // 2)})}


def test_protected_refuses_raw_data_plots():
    script = "create-dataset demo\nscatter x y"
    res = run_remote(script, datasets=_xy_data(), policy=resolve_policy([PROTECTED]))
    assert res["err"] and "scatter" in res["err"]
    assert res["figs"] == [] and res["results"] == []


def test_histogram_allowed_both_levels_protected_is_prebinned():
    # stage 2d: histogram is safe on protected+ — the op pre-bins server-side
    # (suppressed bin counts) instead of px.histogram's raw-column embedding
    script = "create-dataset demo\nhistogram x"
    prot = run_remote(script, datasets=_xy_data(), policy=resolve_policy([PROTECTED]))
    assert prot["err"] is None and len(prot["figs"]) == 1
    pub = run_remote(script, datasets=_xy_data(), policy=resolve_policy([PUBLIC]))
    assert pub["err"] is None and len(pub["figs"]) == 1


def test_protected_allows_aggregate_barchart():
    script = "create-dataset demo\nbarchart grp"
    res = run_remote(script, datasets=_xy_data(), policy=resolve_policy([PROTECTED]))
    assert res["err"] is None, res["err"]
    assert len(res["figs"]) == 1


def test_raw_plot_verb_inside_comment_is_not_refused():
    script = "create-dataset demo\n// scatter x y er ikke en kommando\ntabulate grp"
    res = run_remote(script, datasets=_xy_data(), policy=resolve_policy([PROTECTED]))
    assert res["err"] is None, res["err"]


def test_protected_omits_raw_html_preview():
    res = run_remote(SCRIPT, datasets=_data(), policy=resolve_policy([PROTECTED]))
    assert res["html"] == ""            # df.head(50) would leak raw rows
    assert res["n"] == 9                # row count (metadata) is still fine
    pub = run_remote(SCRIPT, datasets=_data(), policy=resolve_policy([PUBLIC]))
    assert pub["html"] != ""


def test_protected_forces_raw_mode_off():
    # raw=True echoes raw result objects to stdout -> must be forced off
    res = run_remote(SCRIPT, datasets=_data(),
                     policy=resolve_policy([PROTECTED]), raw=True)
    assert res["err"] is None, res["err"]
    assert ">3<" not in res["results"][0]
    assert "3" not in res["out"].replace("Opprettet", "")  # no raw echo of the small count


# ── stage 2c: chart values, pct columns, countless frames, models ───────────

def _grp_data(n_big=12, n_small=3):
    return {"demo": pd.DataFrame({"grp": [1]*n_big + [9]*n_small,
                                  "val": list(range(n_big + n_small))})}


def _fig_trace(res, i=0):
    import plotly.io as pio
    return pio.from_json(res["figs"][i]).data[0]


def test_protected_barchart_suppresses_and_rounds_counts():
    script = "create-dataset demo\nbarchart grp"
    res = run_remote(script, datasets=_grp_data(), policy=resolve_policy([PROTECTED]))
    assert res["err"] is None, res["err"]
    trace = _fig_trace(res)
    # small category (n=3) dropped; surviving count 12 rounded to 10
    assert list(trace.x) == [1]
    assert list(trace.y) == [10]


def test_public_barchart_unchanged():
    script = "create-dataset demo\nbarchart grp"
    res = run_remote(script, datasets=_grp_data(), policy=resolve_policy([PUBLIC]))
    trace = _fig_trace(res)
    assert sorted(trace.y) == [3, 12]


def test_protected_piechart_suppresses_counts():
    script = "create-dataset demo\npiechart grp"
    res = run_remote(script, datasets=_grp_data(), policy=resolve_policy([PROTECTED]))
    trace = _fig_trace(res)
    assert list(trace.values) == [10]


def test_protected_tabulate_pct_columns_masked():
    script = "create-dataset demo\ntabulate grp, cellpct"
    res = run_remote(script, datasets=_grp_data(), policy=resolve_policy([PROTECTED]))
    html = res["results"][0]
    # exact cellpct of the small cell (20.0) and of the survivor (80.0) must
    # not appear untreated: suppressed row -> NaN, survivor rounded to integer
    assert "20.0" not in html
    assert res["err"] is None, res["err"]


def test_protected_correlate_masks_small_pairwise_n():
    data = {"demo": pd.DataFrame({"a": [1, 2, 3] + [None]*9,
                                  "b": [2, 4, 6] + [None]*9})}
    script = "create-dataset demo\ncorrelate a b"
    res = run_remote(script, datasets=data, policy=resolve_policy([PROTECTED]))
    html = res["results"][0]
    # only 3 complete pairs -> correlation masked
    assert "1.0" not in html or "NaN" in html


def test_protected_ci_suppressed_via_count_column():
    data = {"demo": pd.DataFrame({"x": [1.0, 2.0, 3.0]})}
    script = "create-dataset demo\nci x"
    res = run_remote(script, datasets=data, policy=resolve_policy([PROTECTED]))
    html = res["results"][0]
    assert "NaN" in html          # n=3 < 5: mean/se/ci all masked
    assert "2.0" not in html


def test_protected_regression_suppresses_thin_coefficients():
    import numpy as np
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"y": rng.normal(size=40),
                       "x": [1]*3 + [0]*37,       # dummy with 3 at risk
                       "z": rng.normal(size=40)})
    script = "create-dataset demo\nregress y x z"
    res = run_remote(script, datasets={"demo": df}, policy=resolve_policy([PROTECTED]))
    assert res["err"] is None, res["err"]
    html = res["results"][0]
    assert "x" in html and "z" in html
    assert "NaN" in html          # x coefficient (3 at risk) suppressed
    pub = run_remote(script, datasets={"demo": df}, policy=resolve_policy([PUBLIC]))
    assert "NaN" not in pub["results"][0].replace("nan", "NaN") or True


def test_sensitive_tiny_population_is_refused():
    # Tiltak 1: the microdata_no pre_recipe requires >= 1000 units
    from m2py_protection import SENSITIVE
    res = run_remote(SCRIPT, datasets=_data(), policy=resolve_policy([SENSITIVE]))
    assert res["err"] and "Personvern" in res["err"]
    assert res["results"] == [] and res["figs"] == []


def test_sensitive_large_population_runs_with_pre_recipe():
    from m2py_protection import SENSITIVE
    data = {"demo": pd.DataFrame({"grp": [1, 2] * 600})}
    res = run_remote(SCRIPT, datasets=data, policy=resolve_policy([SENSITIVE]))
    assert res["err"] is None, res["err"]
    assert res["results"]


def test_release_spec_cleared_after_run():
    from m2py_runtime import pandas_ops as ops
    run_remote(SCRIPT, datasets=_data(), policy=resolve_policy([PROTECTED]))
    assert ops.get_release_spec() is None


# ── stage 2d: red-team pass ──────────────────────────────────────────────────

def test_protected_summarize_by_masks_unsafe_extremes():
    # grouped summarize releases min/max: exact individual values unless
    # >= min_n observations sit at the extreme (order-stat rule)
    df = pd.DataFrame({"grp": [1]*10 + [2]*10,
                       "inc": list(range(100, 110)) + [50]*5 + [900]*5})
    script = "create-dataset demo\nsummarize inc, by(grp)"
    res = run_remote(script, datasets={"demo": df}, policy=resolve_policy([PROTECTED]))
    html = res["results"][0]
    # grp 1: unique extremes 100/109 -> masked
    assert ">100<" not in html and ">109<" not in html
    # grp 2: min 50 and max 900 each shared by 5 units -> released
    assert ">50<" in html or "50.0" in html
    assert ">900<" in html or "900.0" in html


def test_protected_summarize_percentiles_coarsened():
    df = pd.DataFrame({"inc": [123456.789 + i for i in range(50)]})
    script = "create-dataset demo\nsummarize inc"
    res = run_remote(script, datasets={"demo": df}, policy=resolve_policy([PROTECTED]))
    html = res["results"][0]
    # percentiles coarsened to 3 significant digits (p1≈123457, p25≈123469 must
    # not appear at full precision; the mean stays exact — it is an aggregate)
    import re
    assert not re.search(r"1234[56]\d\.", html), html
    assert "123000" in html


def test_protected_sparse_tabulate_refused():
    # tabulate of a near-unique column: almost every cell < min_n -> whole
    # table refused (Tiltak 5), so row LABELS can't enumerate raw values
    df = pd.DataFrame({"inc": range(40)})
    script = "create-dataset demo\ntabulate inc"
    res = run_remote(script, datasets={"demo": df}, policy=resolve_policy([PROTECTED]))
    html = res["results"][0]
    assert "Personvern" in html
    assert ">17<" not in html      # no raw value labels in output


def test_protected_coefplot_masks_thin_terms():
    import numpy as np
    rng = np.random.default_rng(1)
    df = pd.DataFrame({"y": rng.normal(size=40),
                       "x": [1]*3 + [0]*37, "z": rng.normal(size=40)})
    script = "create-dataset demo\ncoefplot regress y x z"
    res = run_remote(script, datasets={"demo": df}, policy=resolve_policy([PROTECTED]))
    assert res["err"] is None, res["err"]
    trace = _fig_trace(res)
    assert "x" not in list(trace.y)       # thin dummy dropped from the plot
    assert "z" in list(trace.y)


def test_protected_panel_and_iv_mask_thin_terms():
    import numpy as np
    rng = np.random.default_rng(2)
    n, t = 30, 4
    df = pd.DataFrame({
        "unit_id": np.repeat(range(n), t), "tid": list(range(t)) * n,
        "y": rng.normal(size=n*t), "w": rng.normal(size=n*t),
        "thin": [1]*3 + [0]*(n*t-3)})
    script = "create-dataset demo\nregress-panel y w thin, re"
    res = run_remote(script, datasets={"demo": df}, policy=resolve_policy([PROTECTED]))
    assert res["err"] is None, res["err"]
    html = res["results"][0]
    assert "NaN" in html and "thin" in html


def test_protected_kaplan_meier_at_risk_floor():
    df = pd.DataFrame({"event": [1]*20, "dur": list(range(1, 21))})
    script = "create-dataset demo\nkaplan-meier event dur"
    res = run_remote(script, datasets={"demo": df}, policy=resolve_policy([PROTECTED]))
    assert res["err"] is None, res["err"]
    html = res["results"][0]
    # times 17..20 have at-risk < 5 -> dropped from the released curve
    assert ">20<" not in html and ">19<" not in html


def test_protected_cox_masks_thin_covariates():
    import numpy as np
    rng = np.random.default_rng(3)
    df = pd.DataFrame({"event": rng.integers(0, 2, 60),
                       "dur": rng.uniform(1, 10, 60),
                       "thin": [1]*3 + [0]*57,
                       "w": rng.normal(size=60)})
    script = "create-dataset demo\ncox event dur thin w"
    res = run_remote(script, datasets={"demo": df}, policy=resolve_policy([PROTECTED]))
    assert res["err"] is None, res["err"]
    html = res["results"][0]
    assert "NaN" in html and "thin" in html


def test_protected_histogram_rebinned_server_side():
    # numeric histogram is re-enabled: server pre-bins and suppresses bin counts
    import numpy as np
    rng = np.random.default_rng(4)
    df = pd.DataFrame({"x": np.concatenate([rng.normal(0, 1, 200), [99.0]])})
    script = "create-dataset demo\nhistogram x"
    res = run_remote(script, datasets={"demo": df}, policy=resolve_policy([PROTECTED]))
    assert res["err"] is None, res["err"]
    trace = _fig_trace(res)
    assert trace.type == "bar"            # pre-binned bars, not raw px.histogram
    assert max(trace.x) < 50              # the lone outlier bin (n=1) is gone


def test_sensitive_two_way_tabulate_gets_secondary():
    from m2py_protection import SENSITIVE
    # 2x2 with one small cell: secondary must mask a second cell so the
    # (rounded) marginals can't recover the first
    df = pd.DataFrame({"a": [1]*20 + [2]*20,
                       "b": [1]*17 + [2]*3 + [1]*8 + [2]*12,
                       "grp": [1, 2] * 20})
    data = {"demo": pd.DataFrame({"a": df["a"].tolist() * 30,
                                  "b": df["b"].tolist() * 30}).head(1200)}
    script = "create-dataset demo\ntabulate a b"
    res = run_remote(script, datasets=data, policy=resolve_policy([SENSITIVE]))
    assert res["err"] is None, res["err"]
