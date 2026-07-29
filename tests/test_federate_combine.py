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
