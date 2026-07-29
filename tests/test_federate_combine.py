"""Combine-laget (fase 1): eksakt pooling + null-forgiftning."""
import numpy as np
import pandas as pd
import pytest
from m2py_runtime import federate, pandas_ops as ops


@pytest.fixture(autouse=True)
def _reset_federated():
    yield
    ops.set_federated(False)


def _nodes_tab():
    a = {"kind": "tabulate", "keys": ["grp"], "dropped": [],
         "records": [{"grp": 1, "n": 6}, {"grp": 2, "n": 3}]}
    b = {"kind": "tabulate", "keys": ["grp"], "dropped": [],
         "records": [{"grp": 1, "n": 4}, {"grp": 3, "n": 8}]}
    return [{"member": "nord", "stats": [a]}, {"member": "vest", "stats": [b]}]


def test_combine_tabulate_sums_and_treats_absent_as_zero():
    out = federate.combine_stats(_nodes_tab())
    f = out[0]["frame"].set_index("grp")["n"]
    assert f[1] == 10 and f[2] == 3 and f[3] == 8


def test_combine_tabulate_null_poisons_cell():
    nodes = _nodes_tab()
    nodes[1]["stats"][0]["records"][0]["n"] = None   # vest grp=1 suppressed
    out = federate.combine_stats(nodes)
    f = out[0]["frame"].set_index("grp")["n"]
    assert pd.isna(f[1]) and f[2] == 3


def test_combine_summarize_matches_pooled_run():
    rng = np.random.default_rng(7)
    df = pd.DataFrame({"inntekt": rng.normal(500, 50, 90),
                       "grp": rng.integers(1, 4, 90)})
    parts = [df.iloc[:30], df.iloc[30:55], df.iloc[55:]]
    per_node = []
    for i, part in enumerate(parts):
        ns = {"result_1": ops.summarize(part, vars=["inntekt"], by="grp")}
        per_node.append({"member": f"m{i}", "stats": federate.extract_stats(ns, None)})
    combined = federate.combine_stats(per_node)[0]["frame"]
    pooled = ops.summarize(df, vars=["inntekt"], by="grp")
    got = combined.sort_values("grp").reset_index(drop=True)
    want = pooled.sort_values("grp").reset_index(drop=True)
    for col in ("count", "mean", "std", "min", "max"):
        assert np.allclose(got[col].to_numpy(dtype=float),
                           want[col].to_numpy(dtype=float)), col


def test_combine_refusal_names_member():
    nodes = _nodes_tab()
    nodes[1]["stats"][0] = {"kind": "refused", "reason": "for spredt"}
    out = federate.combine_stats(nodes)
    assert out[0]["kind"] == "refused"
    assert "vest" in out[0]["reason"]


def _regress_nodes():
    rng = np.random.default_rng(3)
    x = rng.normal(size=60)
    df = pd.DataFrame({"y": 1 + 2 * x + rng.normal(scale=0.5, size=60), "x": x})
    parts = [df.iloc[:20], df.iloc[20:45], df.iloc[45:]]
    ops.set_federated(True)
    try:
        per_node = []
        for i, part in enumerate(parts):
            ns = {"result_1": ops.regress(part, "y", ["x"])}
            per_node.append({"member": f"m{i}",
                             "stats": federate.extract_stats(ns, None)})
    finally:
        ops.set_federated(False)
    return df, per_node


def test_combine_regress_matches_pooled_ols():
    df, per_node = _regress_nodes()
    combined = federate.combine_stats(per_node)[0]
    assert combined["kind"] == "regress"
    pooled = ops.regress(df, "y", ["x"])
    got = combined["frame"].set_index("term")
    want = pooled.set_index("term")
    for col in ("coef", "se", "t", "p"):
        assert np.allclose(got[col].to_numpy(dtype=float),
                           want[col].to_numpy(dtype=float), atol=1e-6), col


def test_combine_and_render_shape_and_notes():
    _, per_node = _regress_nodes()
    res = federate.combine_and_render(per_node, members=["m0", "m1", "m2"],
                                      overlap="possible")
    assert set(res) >= {"code", "out", "html", "n", "err", "figs", "results",
                        "datasetInfo"}
    assert res["err"] is None
    assert "m0" in res["results"][0] and "overlappe" in res["results"][0]
    assert "<table" in res["results"][1]


def test_combine_and_render_refusal_is_error_block():
    nodes = [{"member": "a", "stats": [{"kind": "refused", "reason": "for spredt"}]}]
    res = federate.combine_and_render(nodes)
    assert "error" in res["results"][1] and "for spredt" in res["results"][1]


def test_federated_logit_driver_matches_pooled(tmp_path):
    from m2py_remote import run_remote_from_sources
    rng = np.random.default_rng(11)
    x = rng.normal(size=120)
    p = 1 / (1 + np.exp(-(0.4 + 1.2 * x)))
    df = pd.DataFrame({"y": (rng.random(120) < p).astype(int), "x": x})
    parts = {"nord": df.iloc[:50], "vest": df.iloc[50:]}
    paths = {}
    for name, part in parts.items():
        pth = tmp_path / f"{name}.csv"
        part.to_csv(pth, index=False)
        paths[name] = str(pth)
    script = "create-dataset demo\nlogit y x"

    def fan_out(fed_round):
        out = []
        for name, pth in paths.items():
            res = run_remote_from_sources(
                script, [{"alias": "demo", "location": pth, "level": "public"}],
                federated=True, fed_round=fed_round)
            assert res["err"] is None, res["err"]
            out.append({"member": name, "stats": res["stats"]})
        return out

    drv = federate.FederatedDriver(fan_out(None))
    spec = drv.logit_spec()
    assert spec is not None and spec["terms"] == ["const", "x"]
    beta = spec["beta"]
    for _ in range(25):
        st = drv.step(fan_out({"beta": beta}))
        assert "error" not in st, st
        beta = st["beta"]
        if st["converged"]:
            break
    assert st["converged"]
    res = drv.render()
    import io
    got = pd.read_html(io.StringIO(res["results"][1 + spec["index"]]))[0]
    import statsmodels.api as sm
    X = sm.add_constant(df[["x"]])
    want = sm.Logit(df["y"], X).fit(disp=0)
    assert np.allclose(got["coef"].to_numpy(), want.params.to_numpy(), atol=1e-5)
    assert np.allclose(got["se"].to_numpy(), want.bse.to_numpy(), atol=1e-5)


def test_combine_stats_refuses_stray_logit():
    nodes = [{"member": "a", "stats": [{"kind": "logit_init", "terms": ["const"],
                                        "n": 10, "at_risk": [10]}]}]
    out = federate.combine_stats(nodes)
    assert out[0]["kind"] == "refused" and "iterative" in out[0]["reason"]
