"""Protection policy + the pandas ProtectionAdapter for SafeStat remote compute.

resolve_policy turns one-or-more source protection levels into a single policy
(most-restrictive-source-wins). PandasProtect is the v1 reference adapter; it
wraps the `protect` package for result-side disclosure control. No emulator or
translator code is touched here — this is purely additive.
"""
from __future__ import annotations

PUBLIC = "public"
PROTECTED = "protected"
SENSITIVE = "sensitive"

_ORDER = {PUBLIC: 0, PROTECTED: 1, SENSITIVE: 2}


def resolve_policy(levels):
    """Most-restrictive-source-wins. Returns a ProtectionPolicy dict."""
    level = max(levels, key=lambda lv: _ORDER[lv]) if levels else PUBLIC
    if level == PUBLIC:
        return {"level": PUBLIC, "auth_required": False, "log": False,
                "pre_recipe": None, "post_suppress": None}
    if level == PROTECTED:
        return {"level": PROTECTED, "auth_required": True, "log": True,
                "pre_recipe": None, "post_suppress": {"min_n": 5}}
    return {"level": SENSITIVE, "auth_required": True, "log": True,
            "pre_recipe": {"profile": "microdata_no"},
            "post_suppress": {"min_n": 5, "secondary": True}}
