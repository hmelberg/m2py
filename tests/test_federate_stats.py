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
