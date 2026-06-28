"""Tests for variable-metadata inference (m2py_runtime/profile.py)."""

import pandas as pd
from m2py_runtime.profile import infer_schema


def test_infers_dtype_level_cardinality():
    df = pd.DataFrame({
        "age": [20, 31, 44, 55, 66, 70, 81, 90, 25, 39],   # numeric, high-card -> continuous
        "sex": [1, 2, 1, 2, 1, 2, 1, 2, 1, 2],             # numeric, low-card  -> nominal
        "name": list("abcdefghij"),                         # string -> nominal
    })
    s = infer_schema(df)
    assert s["age"] == {"dtype": "int", "level": "continuous", "cardinality": 10}
    assert s["sex"]["level"] == "nominal" and s["sex"]["cardinality"] == 2
    assert s["name"]["dtype"] == "string" and s["name"]["level"] == "nominal"


def test_bool_is_nominal():
    df = pd.DataFrame({"flag": [True, False, True]})
    assert infer_schema(df)["flag"]["level"] == "nominal"
