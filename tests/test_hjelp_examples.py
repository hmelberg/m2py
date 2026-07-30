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


def test_harness_skriver_alle_outputfiler():
    """Kjør harnessen og se at hver EXAMPLES-id fikk sin fil."""
    subprocess.run([sys.executable, str(HARNESS)], cwd=REPO, check=True)
    sys.path.insert(0, str(HARNESS.parent))
    import run_examples

    for ex in run_examples.EXAMPLES:
        f = OUTDIR / f"{ex['id']}.txt"
        assert f.exists(), f"mangler output for {ex['id']}"
        assert f.read_text(encoding="utf-8").strip(), f"tom output for {ex['id']}"
