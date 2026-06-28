# tests/test_manifest_integration.py
import pandas as pd
import m2py_translate as t
from m2py_runtime.manifest import Manifest


def test_keyed_merge_plus_keyless_csv(tmp_path):
    persons = pd.DataFrame({"PERSONID_1": [1, 2, 3], "kommnr": [1, 1, 2]})
    income = pd.DataFrame({"PERSONID_1": [1, 2, 3], "wage": [100, 200, 300]})
    survey = pd.DataFrame({"resp": [5, 6, 7]})            # keyless
    pp = tmp_path / "p.parquet"; persons.to_parquet(pp)
    pi = tmp_path / "i.parquet"; income.to_parquet(pi)
    sc = tmp_path / "s.csv"; survey.to_csv(sc, index=False)
    man = Manifest.from_dict({"datasets": {
        "persons": {"source": str(pp), "keys": ["PERSONID_1"],
                    "variables": {"kommnr": {}}},
        "income":  {"source": str(pi), "keys": ["PERSONID_1"],
                    "variables": {"wage": {}}},
        "survey":  {"source": str(sc)},                   # keyless, csv
    }})
    code = t.translate(
        "use income\nmerge wage into persons\n"
        "use persons\ncollapse (mean) wage, by(kommnr)",
        backend="pandas", source_path=None, manifest=man)
    ns = {"pd": pd}; exec(code, ns)
    out = ns["df"].sort_values("kommnr").reset_index(drop=True)
    assert out["wage"].tolist() == [150.0, 300.0]   # (100+200)/2, 300


def test_keyless_single_table_needs_no_key(tmp_path):
    survey = pd.DataFrame({"resp": [5, 6, 7, 8]})
    sc = tmp_path / "s.csv"; survey.to_csv(sc, index=False)
    man = Manifest.from_dict({"datasets": {"survey": {"source": str(sc)}}})
    code = t.translate("use survey\ngenerate big = 1 if resp > 6",
                       backend="pandas", source_path=None, manifest=man)
    ns = {"pd": pd}; exec(code, ns)
    assert ns["df"]["big"].fillna(0).tolist() == [0, 0, 1, 1]
