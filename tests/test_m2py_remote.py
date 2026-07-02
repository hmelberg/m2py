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


def test_protected_refuses_histogram_but_public_allows_it():
    script = "create-dataset demo\nhistogram x"
    prot = run_remote(script, datasets=_xy_data(), policy=resolve_policy([PROTECTED]))
    assert prot["err"] and "histogram" in prot["err"]
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
