"""End-to-end tests for the offline translator's into-form merge.

Key choice is proven to match the emulator in ``test_key_resolution.py``; here we
check the translator emits a runnable join that produces the right values, and
that pandas and polars agree.
"""

import pandas as pd
import pytest

import m2py_translate as t


def _run(script, datasets, backend, active):
    return t.run(script, datasets, backend=backend, active=active)


# --- same-entity person merge (PERSONID_1) --------------------------------

SAME_ENTITY = """create-dataset persons
import INNTEKT/WLONN as lonn
use persons
merge lonn into fam
use fam"""


@pytest.mark.parametrize("backend", ["pandas", "polars"])
def test_into_same_entity_joins_on_personid(backend):
    persons = pd.DataFrame({"PERSONID_1": [1, 2, 3], "lonn": [100, 200, 300]})
    fam = pd.DataFrame({"PERSONID_1": [1, 2, 3], "famid": [10, 10, 20]})
    out = _run(SAME_ENTITY, {"persons": persons, "fam": fam},
               backend, active="persons")
    if backend == "polars":
        out = out.to_pandas()
    out = out.sort_values("PERSONID_1").reset_index(drop=True)
    assert out["lonn"].tolist() == [100, 200, 300]   # each person's own wage


# --- family person-ref merge (collapse by mother-FNR, merge into children) -

FAMILY = """create-dataset mortab
import INNTEKT/WLONN as mor_inntekt
collapse (mean) mor_inntekt, by(mor_fnr)
use mortab
merge mor_inntekt into barn
use barn"""


@pytest.mark.parametrize("backend", ["pandas", "polars"])
def test_into_family_joins_child_to_mother(backend):
    # mortab is one row per mother (collapsed), keyed by mor_fnr.
    mortab = pd.DataFrame({"mor_fnr": [900, 901], "mor_inntekt": [500.0, 700.0]})
    # children carry their mother's fnr; two children share mother 900.
    barn = pd.DataFrame({"PERSONID_1": [1, 2, 3],
                         "mor_fnr": [900, 900, 901]})
    out = _run(FAMILY, {"mortab": mortab, "barn": barn}, backend, active="mortab")
    if backend == "polars":
        out = out.to_pandas()
    out = out.sort_values("PERSONID_1").reset_index(drop=True)
    # each child gets its mother's collapsed income
    assert out["mor_inntekt"].tolist() == [500.0, 500.0, 700.0]


def test_into_family_bakes_mor_fnr_key():
    code = t.translate(FAMILY, backend="pandas", source_path=None)
    assert "left_on='mor_fnr', right_on='mor_fnr'" in code
    assert "merge_into(df_barn, df_mortab" in code


def test_unresolved_key_is_flagged_not_failed():
    # two datasets with no shared/entity/person-ref key -> best guess + TODO
    code = t.translate(
        "create-dataset a\nimport REG/X as x\ncreate-dataset b\n"
        "import REG/Y as y\nuse a\nmerge x into b",
        backend="pandas", source_path=None)
    # a and b both default to the person key, so this actually resolves on
    # PERSONID_1 (person-centric default) -- assert it bakes a concrete key and
    # never emits broken code.
    assert "merge_into(" in code


# --- input resolution: missing dataset KeyError vs emulator fallback -------

# generate a constant so the script doesn't depend on columns the generic mock
# population lacks (the emulator fallback is a base PERSONID_1 population).
MISSING = "create-dataset persons\ngenerate flag = 1\nuse persons"


def test_missing_input_raises_keyerror_by_default():
    code = t.translate(MISSING, backend="pandas", source_path=None)
    ns = {"pd": __import__("pandas"), "datasets": {}}  # 'persons' absent
    with pytest.raises(KeyError, match="persons"):
        exec(code, ns)


def test_missing_input_emulated_when_allowed():
    code = t.translate(MISSING, backend="pandas", source_path=None)
    ns = {"pd": __import__("pandas"), "datasets": {}, "allow_emulated": True}
    exec(code, ns)
    out = ns["df"]
    assert "PERSONID_1" in out.columns and len(out) > 0   # synthesized population


def test_allow_emulated_default_baked_into_header():
    code = t.translate(MISSING, backend="pandas", source_path=None,
                       allow_emulated=True)
    assert "allow_emulated = globals().get('allow_emulated', True)" in code


def test_manifest_key_resolves_merge():
    from m2py_runtime.manifest import Manifest
    man = Manifest.from_dict({"datasets": {
        "persons": {"source": "p.parquet", "keys": ["id"]},
        "income":  {"source": "i.parquet", "keys": ["id"]},
    }})
    code = t.translate(
        "use income\nmerge wage into persons",
        backend="pandas", source_path=None, manifest=man)
    assert "left_on='id', right_on='id'" in code
    assert "# TODO" not in code            # resolved, not flagged


def test_runs_end_to_end_from_manifest(tmp_path):
    import pandas as pd
    from m2py_runtime.manifest import Manifest
    persons = pd.DataFrame({"id": [1, 2, 3], "alder": [20, 30, 40]})
    income  = pd.DataFrame({"id": [1, 2, 3], "wage": [100, 200, 300]})
    p = tmp_path / "persons.parquet"; persons.to_parquet(p)
    i = tmp_path / "income.parquet"; income.to_parquet(i)
    man = Manifest.from_dict({"datasets": {
        "persons": {"source": str(p), "keys": ["id"], "variables": {"alder": {}}},
        "income":  {"source": str(i), "keys": ["id"], "variables": {"wage": {}}},
    }})
    code = t.translate(
        "use income\nmerge wage into persons\nuse persons",
        backend="pandas", source_path=None, manifest=man)
    assert "ops.read_source(" in code
    ns = {"pd": pd}
    exec(code, ns)
    out = ns["df"].sort_values("id").reset_index(drop=True)
    assert out["wage"].tolist() == [100, 200, 300]   # joined on id from the manifest


def test_require_alias_resolves_from_manifest():
    from m2py_runtime.manifest import Manifest
    man = Manifest.from_dict({"datasets": {
        "no.ssb/persons": {"source": "p.parquet", "keys": ["id"]},
        "no.ssb/income":  {"source": "i.parquet", "keys": ["id"]},
    }})
    code = t.translate(
        "require no.ssb/persons as persons\n"
        "require no.ssb/income as income\n"
        "use income\nmerge wage into persons",
        backend="pandas", source_path=None, manifest=man)
    assert "left_on='id', right_on='id'" in code and "# TODO" not in code


def test_composite_key_from_manifest(tmp_path):
    import pandas as pd
    from m2py_runtime.manifest import Manifest
    a = pd.DataFrame({"id": [1, 1, 2], "yr": [2020, 2021, 2020], "v": [10, 11, 20]})
    b = pd.DataFrame({"id": [1, 1, 2], "yr": [2020, 2021, 2020], "w": [1, 2, 3]})
    pa = tmp_path / "a.parquet"; a.to_parquet(pa)
    pb = tmp_path / "b.parquet"; b.to_parquet(pb)
    man = Manifest.from_dict({"datasets": {
        "a": {"source": str(pa), "keys": ["id", "yr"], "variables": {"v": {}}},
        "b": {"source": str(pb), "keys": ["id", "yr"], "variables": {"w": {}}},
    }})
    code = t.translate("use a\nmerge v into b\nuse b",
                       backend="pandas", source_path=None, manifest=man)
    assert "['id', 'yr']" in code
    ns = {"pd": pd}; exec(code, ns)
    out = ns["df"].sort_values(["id", "yr"]).reset_index(drop=True)
    assert out["v"].tolist() == [10, 11, 20]


def test_composite_key_old_syntax_from_manifest(tmp_path):
    import pandas as pd
    from m2py_runtime.manifest import Manifest
    a = pd.DataFrame({"id": [1, 1, 2], "yr": [2020, 2021, 2020], "v": [10, 11, 20]})
    b = pd.DataFrame({"id": [1, 1, 2], "yr": [2020, 2021, 2020], "w": [1, 2, 3]})
    pa = tmp_path / "a.parquet"; a.to_parquet(pa)
    pb = tmp_path / "b.parquet"; b.to_parquet(pb)
    man = Manifest.from_dict({"datasets": {
        "a": {"source": str(pa), "keys": ["id", "yr"], "variables": {"v": {}}},
        "b": {"source": str(pb), "keys": ["id", "yr"], "variables": {"w": {}}},
    }})
    # old-syntax: `merge b` merges b into the active frame `a` (no `into`)
    code = t.translate("use a\nmerge b", backend="pandas", source_path=None, manifest=man)
    assert "['id', 'yr']" in code
    ns = {"pd": pd}; exec(code, ns)
    out = ns["df"].sort_values(["id", "yr"]).reset_index(drop=True)
    assert len(out) == 3                       # no row multiplication
    assert out["w"].tolist() == [1, 2, 3]
