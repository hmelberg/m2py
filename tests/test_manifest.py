from m2py_runtime.manifest import Manifest

M = {
    "datasets": {
        "persons": {"source": "data/persons.parquet", "keys": ["PERSONID_1"],
                    "entity": "person", "variables": {"alder": {"dtype": "int"}}},
        "survey":  {"source": "s/survey.csv"},  # keyless, no format, no vars
    }
}


def test_names_and_has():
    m = Manifest.from_dict(M)
    assert set(m.names()) == {"persons", "survey"}
    assert m.has("persons") and not m.has("missing")


def test_location_and_inferred_format():
    m = Manifest.from_dict(M)
    assert m.location("persons") == "data/persons.parquet"
    assert m.format("persons") == "parquet"     # inferred from extension
    assert m.format("survey") == "csv"


def test_keys_default_empty_and_entity():
    m = Manifest.from_dict(M)
    assert m.keys("persons") == ["PERSONID_1"]
    assert m.keys("survey") == []               # keyless
    assert m.entity("persons") == "person"
    assert m.entity("survey") is None


def test_variables_default_empty_and_sensitive_default():
    m = Manifest.from_dict(M)
    assert m.variables("persons") == {"alder": {"dtype": "int"}}
    assert m.variables("survey") == {}
    assert m.is_sensitive("persons") is False
