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
    assert set(res) == {"code", "out", "html", "n", "err", "figs", "results"}
    assert res["err"] is None, res["err"]
    assert res["results"], "expected at least one rendered result"
    assert res["n"] == 9   # translator footer materialized df = df_demo (9 rows)


def test_run_remote_public_keeps_small_counts():
    res = run_remote(SCRIPT, datasets=_data(), policy=resolve_policy([PUBLIC]))
    # public => no suppression => the count 3 survives in the rendered table
    assert ">3<" in res["results"][0] or "3.0" in res["results"][0]


def test_run_remote_protected_suppresses_small_counts():
    res = run_remote(SCRIPT, datasets=_data(), policy=resolve_policy([PROTECTED]))
    html = res["results"][0]
    # protected => n=3 row suppressed to NaN; the surviving count 6 still shows
    assert ">6<" in html or "6.0" in html
    assert "NaN" in html  # suppressed cell renders as NaN
    # the suppressed count must be GONE, not merely NaN-tokened elsewhere
    assert ">3<" not in html and "3.0" not in html
