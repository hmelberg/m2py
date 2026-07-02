import pandas as pd
from m2py_remote import run_remote_from_sources

SCRIPT = "create-dataset demo\ntabulate grp"


def _csv(tmp_path):
    p = tmp_path / "demo.csv"
    pd.DataFrame({"grp": [1] * 6 + [9] * 3}).to_csv(p, index=False)
    return str(p)


def test_from_sources_public_runs_and_keeps_small_counts(tmp_path):
    sources = [{"alias": "demo", "location": _csv(tmp_path), "level": "public"}]
    res = run_remote_from_sources(SCRIPT, sources)
    assert res["err"] is None, res["err"]
    assert res["results"]
    # public => count 3 survives
    assert ">3<" in res["results"][0] or "3.0" in res["results"][0]


def test_from_sources_protected_suppresses_small_counts(tmp_path):
    sources = [{"alias": "demo", "location": _csv(tmp_path), "level": "protected"}]
    res = run_remote_from_sources(SCRIPT, sources)
    html = res["results"][0]
    assert "NaN" in html
    assert ">3<" not in html and "3.0" not in html
    # surviving count 6 rounds to 10 (shared preset: min_n=5, round_to=10)
    assert ">6<" not in html and "6.0" not in html
    assert "10" in html
