"""Node-side federated statistics (fase 1, spec 2026-07-29 §5)."""
import numpy as np
import pandas as pd
import pytest
from m2py_runtime import pandas_ops as ops


@pytest.fixture(autouse=True)
def _reset_federated():
    yield
    ops.set_federated(False)


def _df(n=20, seed=1):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    return pd.DataFrame({"y": 2 + 3 * x + rng.normal(scale=0.1, size=n), "x": x})


from m2py_runtime import federate

SPEC = {"min_n": 5, "round": 10, "percentile_sig_figs": 3,
        "max_low_cell_share": 0.5}


def _tab_ns():
    df = pd.DataFrame({"grp": [1] * 6 + [2] * 3})
    return {"result_1": ops.tabulate(df, ["grp"])}


def test_extract_tabulate_public_keeps_exact_counts():
    stats = federate.extract_stats(_tab_ns(), None)
    assert stats[0]["kind"] == "tabulate"
    assert stats[0]["keys"] == ["grp"]
    assert {r["grp"]: r["n"] for r in stats[0]["records"]} == {1: 6, 2: 3}


def test_extract_tabulate_protected_masks_and_rounds():
    stats = federate.extract_stats(_tab_ns(), SPEC)
    by = {r["grp"]: r["n"] for r in stats[0]["records"]}
    assert by[2] is None          # 3 < min_n -> suppressed
    assert by[1] == 10            # 6 rounds to 10


def test_extract_summarize_drops_percentiles():
    df = pd.DataFrame({"inntekt": [10.0, 20, 30, 40, 50, 60],
                       "grp": [1, 1, 1, 2, 2, 2]})
    ns = {"result_1": ops.summarize(df, vars=["inntekt"], by="grp")}
    stats = federate.extract_stats(ns, None)
    s = stats[0]
    assert s["kind"] == "summarize"
    assert set(s["keys"]) == {"grp", "variable"}
    r1 = next(r for r in s["records"] if r["grp"] == 1)
    assert r1["count"] == 3 and r1["mean"] == 20.0
    assert not any(c.startswith("p") and c[1:].isdigit() for r in s["records"] for c in r)


def test_extract_regress_public_emits_fedstats():
    ops.set_federated(True)
    ns = {"result_1": ops.regress(_df(), "y", ["x"])}
    stats = federate.extract_stats(ns, None)
    assert stats[0]["kind"] == "regress"
    assert stats[0]["terms"] == ["const", "x"]


def test_extract_regress_below_threshold_refused():
    ops.set_federated(True)
    ns = {"result_1": ops.regress(_df(n=4), "y", ["x"])}
    stats = federate.extract_stats(ns, SPEC)
    assert stats[0]["kind"] == "refused"
    assert "for få" in stats[0]["reason"]


def test_extract_logit_init_and_round_kinds():
    ops.set_federated(True)
    ns = {"result_1": ops.logit(_logit_df(), "y", ["x"])}
    assert federate.extract_stats(ns, None)[0]["kind"] == "logit_init"
    ops.set_fed_round([0.0, 0.0])
    try:
        ns = {"result_1": ops.logit(_logit_df(), "y", ["x"])}
    finally:
        ops.set_fed_round(None)
    s = federate.extract_stats(ns, None)[0]
    assert s["kind"] == "logit_round" and "hess" in s


def test_extract_logit_below_threshold_refused():
    ops.set_federated(True)
    ns = {"result_1": ops.logit(_logit_df(n=4), "y", ["x"])}
    assert federate.extract_stats(ns, SPEC)[0]["kind"] == "refused"


def test_extract_unknown_and_figures_unsupported():
    ns = {"result_1": "just a string", "fig_1": object()}
    stats = federate.extract_stats(ns, None)
    assert stats[0]["kind"] == "unsupported"


def _logit_df(n=40, seed=5):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    p = 1 / (1 + np.exp(-(0.5 + 1.5 * x)))
    return pd.DataFrame({"y": (rng.random(n) < p).astype(float), "x": x})


def test_logit_federated_init_emits_terms_no_fit():
    ops.set_federated(True)
    out = ops.logit(_logit_df(), "y", ["x"])
    fs = out.attrs["fedstats"]
    assert fs["model"] == "logit" and fs["terms"] == ["const", "x"]
    assert fs["n"] == 40 and "grad" not in fs


def test_logit_federated_round_computes_grad_hess_at_beta():
    df = _logit_df()
    ops.set_federated(True)
    ops.set_fed_round([0.0, 0.0])
    try:
        fs = ops.logit(df, "y", ["x"]).attrs["fedstats"]
    finally:
        ops.set_fed_round(None)
    assert fs["model"] == "logit_round"
    X = np.column_stack([np.ones(40), df["x"].to_numpy()])
    y = df["y"].to_numpy()
    p = np.full(40, 0.5)                      # sigmoid(0)
    assert np.allclose(fs["grad"], X.T @ (y - p))
    assert np.allclose(fs["hess"], (X * (p * (1 - p))[:, None]).T @ X)


def test_regress_attaches_fedstats_only_when_federated():
    df = _df()
    plain = ops.regress(df, "y", ["x"])
    assert "fedstats" not in plain.attrs
    ops.set_federated(True)
    fed = ops.regress(df, "y", ["x"])
    fs = fed.attrs["fedstats"]
    assert fs["terms"] == ["const", "x"]
    assert fs["n"] == 20
    X = np.column_stack([np.ones(20), df["x"].to_numpy()])
    assert np.allclose(fs["xtx"], X.T @ X)
    assert np.allclose(fs["xty"], X.T @ df["y"].to_numpy())
    assert fs["yty"] == pytest.approx(float(df["y"] @ df["y"]))
    assert fs["at_risk"][0] == 20
