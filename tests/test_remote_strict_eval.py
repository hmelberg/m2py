# tests/test_remote_strict_eval.py
# AST-hvitelistet uttrykks-eval i fjernkjøring (m2py_remote):
# beskyttede kilder (level != "public") får kun microdata-uttrykksspråket i
# generate/replace/keep-uttrykk; public (store, åpne data) beholder fri eval.
import pandas as pd

import m2py
from m2py_remote import run_remote
from m2py_protection import resolve_policy, PUBLIC, PROTECTED


def _data(n=40):
    return {"demo": pd.DataFrame({
        "inntekt": [100.0 + i for i in range(n)],
        "alder": [20 + (i % 50) for i in range(n)],
        "grp": [1, 2] * (n // 2)})}


def _run(script, level):
    return run_remote(script, datasets=_data(), policy=resolve_policy([level]))


# ── beskyttet: fluktforsøk avvises høylytt ──────────────────────────────────

def test_protected_refuses_dunder_import():
    res = _run("create-dataset demo\ngenerate x = __import__('os').getpid()",
               PROTECTED)
    assert res["err"] and "Personvern" in res["err"], res["err"]


def test_protected_refuses_dunder_attribute_walk():
    res = _run("create-dataset demo\ngenerate x = (1).__class__.__mro__",
               PROTECTED)
    assert res["err"] and "Personvern" in res["err"], res["err"]


def test_protected_refuses_unknown_function():
    res = _run("create-dataset demo\ngenerate x = open('/etc/passwd')",
               PROTECTED)
    assert res["err"] and "Personvern" in res["err"], res["err"]


def test_protected_refuses_attribute_on_column():
    # metodekall på Series (f.eks. .to_csv) er utenfor uttrykksspråket
    res = _run("create-dataset demo\ngenerate x = inntekt.to_csv()",
               PROTECTED)
    assert res["err"] and "Personvern" in res["err"], res["err"]


def test_protected_refuses_escape_in_condition():
    res = _run("create-dataset demo\nkeep if len(__import__('os').getcwd()) > 0",
               PROTECTED)
    assert res["err"] and "Personvern" in res["err"], res["err"]


# ── beskyttet: legitime uttrykk går fortsatt gjennom ────────────────────────

def test_protected_allows_arithmetic_and_known_functions():
    res = _run("create-dataset demo\n"
               "generate y = inntekt * 2 + abs(alder - 40)\n"
               "keep if alder > 30 & grp == 1\n"
               "summarize y", PROTECTED)
    assert res["err"] is None, res["err"]
    assert res["results"]


def test_protected_allows_np_functions():
    res = _run("create-dataset demo\ngenerate z = np.log(inntekt)\nsummarize z",
               PROTECTED)
    assert res["err"] is None, res["err"]


# ── public (stordata-tilfellet): fri eval beholdes ──────────────────────────

def test_public_keeps_free_eval():
    res = _run("create-dataset demo\ngenerate x = __import__('math').pi",
               PUBLIC)
    assert res["err"] is None, res["err"]


# ── hygiene: modusen er alltid av etter kjøring ─────────────────────────────

def test_strict_mode_reset_after_run():
    _run("create-dataset demo\ngenerate x = inntekt * 2", PROTECTED)
    assert m2py.M2PY_STRICT_EVAL is False


def test_strict_mode_reset_after_refusal():
    _run("create-dataset demo\ngenerate x = open('f')", PROTECTED)
    assert m2py.M2PY_STRICT_EVAL is False
