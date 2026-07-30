"""Eksempel-harness for hjelpesidene: resultatblokkene skal være genererte,
ikke skrevet for hånd. Testen låser at harnessen er deterministisk — samme
kode inn gir samme tekst ut, hver gang."""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HARNESS = REPO / "docs" / "hjelp_examples" / "run_examples.py"
OUTDIR = REPO / "docs" / "hjelp_examples" / "output"


def test_harness_er_deterministisk():
    """To kjøringer på rad gir identisk output for hvert eksempel."""
    sys.path.insert(0, str(HARNESS.parent))
    import run_examples

    df1 = run_examples.build_frame()
    df2 = run_examples.build_frame()
    for ex in run_examples.EXAMPLES:
        a = run_examples.run_one(ex, df1)
        b = run_examples.run_one(ex, df2)
        assert a == b, f"{ex['id']} er ikke deterministisk"


def test_avvist_eksempel_gir_ekte_feilmelding():
    """Et eksempel merket expect_ok=False skal produsere safepy sin faktiske
    feilmelding — ikke en tom blokk og ikke en oppdiktet tekst."""
    sys.path.insert(0, str(HARNESS.parent))
    import run_examples

    df = run_examples.build_frame()
    ex = next(e for e in run_examples.EXAMPLES if e["id"] == "strict-py-avvist-head")
    out = run_examples.run_one(ex, df)
    assert "'head' is not allowed" in out
    assert "reveal individual rows" in out


EXPECTED_TEXT = {
    "strict-py-gruppegjennomsnitt": (
        "kjonn  mean(lonn)\n"
        "1  520 790\n"
        "2  518 450"
    ),
    "strict-r-summarise": (
        "  m  n\n"
        "1  520 790  2 530\n"
        "2  518 450  2 470"
    ),
    # DuckDB's GROUP BY has no guaranteed row order on its own — measured
    # ~35/65 split over 20 calls on 2026-07-30, within the same process, not
    # just across engine versions. run_examples.py's strict-sql-gruppe entry
    # now has an explicit ORDER BY kjonn, which was verified to make this
    # fully deterministic (12 consecutive runs, one row order). So this is
    # compared with plain exact equality below, same as the other two — no
    # order-insensitive special case. If this ever starts failing, the first
    # suspect is someone having dropped ORDER BY from that example's code.
    "strict-sql-gruppe": (
        "  m  n\n"
        "1  520 790  2 530\n"
        "2  518 450  2 470"
    ),
}


def test_godkjente_eksempler_gir_forventet_tekst():
    """Determinisme og ikke-tomhet er ikke nok: uten dette låser ingenting
    det faktiske INNHOLDET til de tre expect_ok=True-eksemplene. En feil i
    _format_payload som gir konsistent men FEIL tekst ville passert de andre
    testene stille — og feil tall ville havnet i hjelpesidene."""
    sys.path.insert(0, str(HARNESS.parent))
    import run_examples

    df = run_examples.build_frame()
    for ex_id, expected in EXPECTED_TEXT.items():
        ex = next(e for e in run_examples.EXAMPLES if e["id"] == ex_id)
        actual = run_examples.run_one(ex, df)
        assert actual == expected, (
            f"{ex_id}: uventet tekst.\n"
            f"--- forventet ---\n{expected}\n"
            f"--- fikk ---\n{actual}"
        )


def test_harness_skriver_alle_outputfiler():
    """Kjør harnessen og se at hver EXAMPLES-id fikk sin fil."""
    subprocess.run([sys.executable, str(HARNESS)], cwd=REPO, check=True)
    sys.path.insert(0, str(HARNESS.parent))
    import run_examples

    for ex in run_examples.EXAMPLES:
        f = OUTDIR / f"{ex['id']}.txt"
        assert f.exists(), f"mangler output for {ex['id']}"
        assert f.read_text(encoding="utf-8").strip(), f"tom output for {ex['id']}"


# ── Task 12b: #microdata kjørt headless via MicroInterpreter ───────────────

def test_microdata_harness_er_deterministisk():
    """Samme mønster som test_harness_er_deterministisk, for microdata-
    eksemplene: to kjøringer på et ferskt datasett gir identisk tekst."""
    sys.path.insert(0, str(HARNESS.parent))
    import run_examples

    df1 = run_examples.build_frame()
    df2 = run_examples.build_frame()
    for ex in run_examples.MICRODATA_EXAMPLES:
        a = run_examples.run_microdata_example(ex, df1)
        b = run_examples.run_microdata_example(ex, df2)
        assert a == b, f"{ex['id']} er ikke deterministisk"


def test_microdata_avvisning_gir_ekte_feilmelding():
    """Et avvist microdata-eksempel skal bære m2py sin faktiske FEIL-tekst,
    ikke en omskrevet eller oppdiktet variant."""
    sys.path.insert(0, str(HARNESS.parent))
    import run_examples

    df = run_examples.build_frame()
    ex = next(e for e in run_examples.MICRODATA_EXAMPLES
              if e["id"] == "microdata-avvist-populasjon")
    out = run_examples.run_microdata_example(ex, df)
    assert "FEIL" in out
    assert "krever minst 1000 enheter per populasjon" in out


def test_microdata_disclosure_control_gjenopprettes():
    """run_microdata_example skal ikke la M2PY_DISCLOSURE_CONTROL lekke ut i
    modulen etter kjøring — ellers ville rekkefølgen andre tester kjører i
    påvirke resultatet deres (delt modul-global)."""
    sys.path.insert(0, str(HARNESS.parent))
    import run_examples
    import m2py

    had_attr_before = hasattr(m2py, "M2PY_DISCLOSURE_CONTROL")
    value_before = getattr(m2py, "M2PY_DISCLOSURE_CONTROL", None)

    df = run_examples.build_frame()
    run_examples.run_microdata_example(run_examples.MICRODATA_EXAMPLES[0], df)

    assert hasattr(m2py, "M2PY_DISCLOSURE_CONTROL") == had_attr_before
    assert getattr(m2py, "M2PY_DISCLOSURE_CONTROL", None) == value_before


def test_harness_skriver_microdata_outputfiler():
    subprocess.run([sys.executable, str(HARNESS)], cwd=REPO, check=True)
    sys.path.insert(0, str(HARNESS.parent))
    import run_examples

    for ex in run_examples.MICRODATA_EXAMPLES:
        f = OUTDIR / f"{ex['id']}.txt"
        assert f.exists(), f"mangler output for {ex['id']}"
        assert f.read_text(encoding="utf-8").strip(), f"tom output for {ex['id']}"


# ── Task 12b: felles-lagre/felles-forklar/felles-widgets kjørt via Node ────

NODE_HARNESS = REPO / "docs" / "hjelp_examples" / "run_examples_js.mjs"
NODE_IDS = [
    "felles-widgets-title",
    "felles-widgets-question",
    "felles-forklar-blokker",
    "felles-lagre-delelenke",
]


def _node_available() -> bool:
    import shutil as _shutil
    return _shutil.which("node") is not None


def test_node_harness_finnes_og_er_selvstendig_kjorbar():
    import shutil as _shutil
    assert NODE_HARNESS.exists(), "docs/hjelp_examples/run_examples_js.mjs mangler"
    node = _shutil.which("node")
    if node is None:
        import pytest as _pytest
        _pytest.skip("node ikke i PATH i dette miljøet")
    r = subprocess.run([node, str(NODE_HARNESS)], cwd=REPO,
                       capture_output=True, text=True)
    assert r.returncode == 0, f"node-harnessen feilet:\n{r.stdout}\n{r.stderr}"
    for id_ in NODE_IDS:
        f = OUTDIR / f"{id_}.txt"
        assert f.exists(), f"mangler output for {id_}"
        assert f.read_text(encoding="utf-8").strip(), f"tom output for {id_}"


def test_node_harness_er_deterministisk_pa_tvers_av_prosesser():
    """Kjør node-harnessen to ganger som separate prosesser og se at hver
    outputfil er byte-identisk begge ganger — spesielt viktig for
    delelenka, siden gzip generelt kan bære tidsstempler (CompressionStream
    gjør det ikke, men det er nettopp det denne testen skal fange hvis det
    endrer seg)."""
    import shutil as _shutil
    node = _shutil.which("node")
    if node is None:
        import pytest as _pytest
        _pytest.skip("node ikke i PATH i dette miljøet")

    r1 = subprocess.run([node, str(NODE_HARNESS)], cwd=REPO, check=True)
    snap1 = {id_: (OUTDIR / f"{id_}.txt").read_text(encoding="utf-8") for id_ in NODE_IDS}
    r2 = subprocess.run([node, str(NODE_HARNESS)], cwd=REPO, check=True)
    snap2 = {id_: (OUTDIR / f"{id_}.txt").read_text(encoding="utf-8") for id_ in NODE_IDS}
    assert snap1 == snap2, "node-harnessen er ikke deterministisk på tvers av prosesser"
