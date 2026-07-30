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
