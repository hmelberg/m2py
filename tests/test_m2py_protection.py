import pandas as pd
from m2py_protection import resolve_policy, PUBLIC, PROTECTED, SENSITIVE, PandasProtect


def test_resolve_policy_public_is_all_pass():
    pol = resolve_policy([PUBLIC])
    assert pol["level"] == PUBLIC
    assert pol["auth_required"] is False
    assert pol["log"] is False
    assert pol["pre_recipe"] is None
    assert pol["post_suppress"] is None


def test_resolve_policy_protected_uses_shared_preset():
    # Values mirror safepy's "standard" tier (protected level): min_n=5, round to 10.
    pol = resolve_policy([PROTECTED])
    assert pol["auth_required"] is True
    assert pol["log"] is True
    assert pol["post_suppress"]["min_n"] == 5
    assert pol["post_suppress"]["round"] == 10
    assert pol["post_suppress"]["secondary"] is False


def test_resolve_policy_sensitive_adds_pre_recipe_and_secondary():
    pol = resolve_policy([SENSITIVE])
    assert pol["pre_recipe"] == {"profile": "microdata_no"}
    assert pol["post_suppress"]["min_n"] == 5
    assert pol["post_suppress"]["secondary"] is True


def test_resolve_policy_most_restrictive_wins():
    pol = resolve_policy([PUBLIC, PROTECTED, PUBLIC])
    assert pol["level"] == PROTECTED


def test_resolve_policy_empty_defaults_public():
    assert resolve_policy([])["level"] == PUBLIC


def test_suppress_nans_small_counts_in_freq_table():
    table = pd.DataFrame({"x": [1, 2, 3], "n": [12, 3, 7]})
    out = PandasProtect().suppress(table, {"min_n": 5})
    # row with n=3 is below threshold -> NaN; others intact (no round in spec)
    assert pd.isna(out.loc[1, "n"])
    assert out.loc[0, "n"] == 12
    assert out.loc[2, "n"] == 7
    # category keys are never touched
    assert list(out["x"]) == [1, 2, 3]


def test_suppress_rounds_counts_when_spec_says_so():
    table = pd.DataFrame({"x": [1, 2], "n": [12, 6]})
    out = PandasProtect().suppress(table, {"min_n": 5, "round": 10})
    assert out.loc[0, "n"] == 10
    assert out.loc[1, "n"] == 10


def test_suppress_pairs_summarize_stats_with_count_column():
    # summarize-style frame: count column drives suppression of the stat columns
    table = pd.DataFrame(
        {"count": [12, 3], "mean": [100.0, 42.0], "std": [5.0, 1.0]},
        index=["inntekt", "rare_var"],
    )
    out = PandasProtect().suppress(table, {"min_n": 5})
    assert out.loc["inntekt", "mean"] == 100.0
    assert pd.isna(out.loc["rare_var", "mean"])       # count 3 < 5 -> stats gone
    assert pd.isna(out.loc["rare_var", "std"])
    assert pd.isna(out.loc["rare_var", "count"])      # the small count itself too


def test_suppress_none_spec_passes_through():
    table = pd.DataFrame({"x": [1], "n": [2]})
    out = PandasProtect().suppress(table, None)
    assert out.loc[0, "n"] == 2


def test_suppress_non_table_passes_through():
    obj = {"not": "a table"}
    assert PandasProtect().suppress(obj, {"min_n": 5}) is obj


def test_suppress_countless_frame_passes_through():
    # aggregate tables without a count column are a documented later slice
    table = pd.DataFrame({"a": [1.0, 2.0]})
    out = PandasProtect().suppress(table, {"min_n": 5})
    assert list(out["a"]) == [1.0, 2.0]
