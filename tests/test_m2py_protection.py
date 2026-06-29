from m2py_protection import resolve_policy, PUBLIC, PROTECTED, SENSITIVE


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
