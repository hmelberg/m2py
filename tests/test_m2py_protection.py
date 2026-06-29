import pandas as pd
from m2py_protection import resolve_policy, PUBLIC, PROTECTED, SENSITIVE, PandasProtect


def test_resolve_policy_public_is_all_pass():
    pol = resolve_policy([PUBLIC])
    assert pol["level"] == PUBLIC
    assert pol["auth_required"] is False
    assert pol["log"] is False
    assert pol["pre_recipe"] is None
    assert pol["post_suppress"] is None


def test_resolve_policy_protected_suppresses_and_logs():
    pol = resolve_policy([PROTECTED])
    assert pol["auth_required"] is True
    assert pol["log"] is True
    assert pol["post_suppress"] == {"min_n": 5}


def test_resolve_policy_most_restrictive_wins():
    pol = resolve_policy([PUBLIC, PROTECTED, PUBLIC])
    assert pol["level"] == PROTECTED


def test_resolve_policy_empty_defaults_public():
    assert resolve_policy([])["level"] == PUBLIC


def test_suppress_nans_small_counts_in_freq_table():
    table = pd.DataFrame({"x": [1, 2, 3], "n": [12, 3, 7]})
    out = PandasProtect().suppress(table, {"min_n": 5})
    # row with n=3 is below threshold -> NaN; others intact
    assert pd.isna(out.loc[1, "n"])
    assert out.loc[0, "n"] == 12
    assert out.loc[2, "n"] == 7
    # category keys are never touched
    assert list(out["x"]) == [1, 2, 3]


def test_suppress_none_spec_passes_through():
    table = pd.DataFrame({"x": [1], "n": [2]})
    out = PandasProtect().suppress(table, None)
    assert out.loc[0, "n"] == 2


def test_suppress_non_table_passes_through():
    obj = {"not": "a table"}
    assert PandasProtect().suppress(obj, {"min_n": 5}) is obj
