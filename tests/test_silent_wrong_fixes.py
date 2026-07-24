# tests/test_silent_wrong_fixes.py
# Regresjonstester for stille-feil-tall-funnene fra Fable-reviewen 2026-07-24:
# (1) ikke-deterministisk merge-nøkkel, (2) pandas_ops.keep/drop kolonne-før-
# betingelse, (3) énveis tabulate row/colpct = konstant 100 i pandas_ops,
# (4) quote-ublind ' if '-splitt i parseren.
import pandas as pd
import pytest

from m2py_runtime.keys import resolve_merge_key
from m2py_runtime import pandas_ops as ops
import m2py


# ── (1) merge-nøkkel: deterministisk ved flere felleskolonner ───────────────

def test_common_key_deterministic_sorted():
    # common-grenen nås når verken src_key (første kildekolonne) eller tgt_key
    # deles: to felleskolonner midt i listene skal velges stabilt (alfabetisk
    # førstemann), ikke etter hash-rekkefølge.
    r = resolve_merge_key(["s1", "zeta", "alpha"], ["alpha", "zeta", "t1"])
    assert r.status == "ok"
    assert r.left_on == "alpha" and r.right_on == "alpha"


def test_common_key_stable_across_orderings():
    a = resolve_merge_key(["s1", "b_kol", "a_kol"], ["a_kol", "b_kol", "t1"])
    b = resolve_merge_key(["s1", "a_kol", "b_kol"], ["b_kol", "a_kol", "t1"])
    assert a.left_on == b.left_on == "a_kol"


# ── (2) keep/drop: betingelsen evalueres FØR kolonnefilteret ────────────────

def _df():
    return pd.DataFrame({"x": [1, 2, 3, 4], "y": [1, 1, 0, 0], "z": [9, 8, 7, 6]})


def test_keep_condition_may_reference_dropped_column():
    # `keep x if y == 1`: y er ikke blant beholdte kolonner — betingelsen skal
    # likevel virke (emulator-rekkefølgen), ikke gi NameError.
    out = ops.keep(_df(), vars=["x"], cond="y == 1")
    assert list(out.columns) == ["x"]
    assert list(out["x"]) == [1, 2]


def test_drop_condition_may_reference_dropped_column():
    out = ops.drop(_df(), vars=["y"], cond="y == 1")
    assert "y" not in out.columns
    assert list(out["x"]) == [3, 4]


# ── (3) énveis tabulate: row/colpct = andel av totalen, ikke konstant 100 ───

def test_oneway_tabulate_pct_not_constant_100():
    df = pd.DataFrame({"grp": [1] * 6 + [2] * 3 + [3] * 1})
    out = ops.tabulate(df, ["grp"], rowpct=True, colpct=True, cellpct=True)
    for col in ("rowpct", "colpct", "cellpct"):
        vals = sorted(out[col].round(1))
        assert vals == [10.0, 30.0, 60.0], (col, vals)


def test_twoway_tabulate_pct_unchanged():
    df = pd.DataFrame({"x": [1, 1, 1, 2, 2], "y": [1, 1, 0, 1, 0]})
    out = ops.tabulate(df, ["x", "y"], rowpct=True)
    row = out[(out["x"] == 1) & (out["y"] == 1)].iloc[0]
    assert round(float(row["rowpct"]), 4) == round(200 / 3, 4)


# ── (4) ' if '-splitt: quote-bevisst ────────────────────────────────────────

def test_if_inside_string_literal_not_split():
    e = m2py.MicroInterpreter(catalog=None)
    e.datasets["d"] = pd.DataFrame({"grp": [1, 2, 1]})
    e.active_name = "d"
    # 'what if scenario' inneholder ' if ' — skal IKKE tolkes som betingelse.
    e.run_script("define-labels glab 1 'what if scenario' 2 'other'\nassign-labels grp glab")
    lbls = e.label_manager.codelists.get("glab") or {}
    assert "what if scenario" in [str(v) for v in lbls.values()], lbls


def test_real_if_condition_still_works():
    e = m2py.MicroInterpreter(catalog=None)
    e.datasets["d"] = pd.DataFrame({"x": [1, 2, 3, 4]})
    e.active_name = "d"
    e.run_script("keep if x > 2")
    assert list(e.datasets["d"]["x"]) == [3, 4]
