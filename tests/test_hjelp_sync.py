"""Synk-sjekk for hjelpesidenes fellesseksjoner.

De fire repoene har hver sin hjelp.html. Fellesseksjonene skal være
byte-identiske; dagens tilstand er beviset på at de ellers driver fra
hverandre (askstat sin het «OpenStat» i to måneder)."""
import os
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "hjelp_sync_check.sh"

BLOCK_NAMES = [
    "felles-css", "felles-js",
    # Task 9:
    # "felles-editor", "felles-sidebar",
    # "felles-lagre", "felles-forklar", "felles-widgets", "felles-ai",
    # "felles-eksempler", "felles-referanse-snarveier", "felles-referanse-tab",
]


def extract_block(text: str, name: str):
    """Hent én SYNC-blokk. Godtar både /* */ og <!-- --> som markør."""
    pat = (r"(?:/\*|<!--)\s*SYNC:START\s+" + re.escape(name)
           + r"\s*(?:\*/|-->)(.*?)(?:/\*|<!--)\s*SYNC:END\s*(?:\*/|-->)")
    m = re.search(pat, text, re.DOTALL)
    return m.group(1) if m else None


def test_skriptet_finnes_og_er_kjorbart():
    assert SCRIPT.exists(), "scripts/hjelp_sync_check.sh mangler"
    assert SCRIPT.stat().st_mode & 0o111, "skriptet er ikke kjørbart"


def test_alle_blokker_finnes_i_egen_hjelp():
    """Hver navngitt blokk skal faktisk finnes i safestat sin hjelp.html."""
    text = (REPO / "hjelp.html").read_text(encoding="utf-8")
    mangler = [n for n in BLOCK_NAMES if extract_block(text, n) is None]
    assert not mangler, f"mangler SYNC-blokker: {mangler}"


def test_skriptet_gir_exit_0_naar_alt_stemmer():
    r = subprocess.run(["sh", str(SCRIPT)], cwd=REPO,
                       capture_output=True, text=True)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stdout}\n{r.stderr}"


def test_skriptet_gir_exit_1_ved_avvik(tmp_path):
    """Bygg et falskt søskenrepo med en sabotert blokk og se at skriptet
    faktisk går til exit 1. Uten denne kunne skriptet returnert 0 alltid og
    synk-disiplinen vært en illusjon."""
    text = (REPO / "hjelp.html").read_text(encoding="utf-8")
    blokk = extract_block(text, "felles-css")
    assert blokk is not None, "felles-css mangler i hjelp.html"

    falsk = tmp_path / "faksesosken"
    falsk.mkdir()
    saboterte = text.replace(blokk, blokk + "\n.sabotasje { color: red; }", 1)
    assert saboterte != text, "sabotasjen endret ingenting"
    (falsk / "hjelp.html").write_text(saboterte, encoding="utf-8")
    (falsk / "hjelp.en.html").write_text(
        (REPO / "hjelp.en.html").read_text(encoding="utf-8"), encoding="utf-8")

    r = subprocess.run(
        ["sh", str(SCRIPT)], cwd=REPO, capture_output=True, text=True,
        env={**os.environ,
             "HJELP_SYNC_ROOT": str(tmp_path),
             "HJELP_SYNC_SIBLINGS": "faksesosken"})
    assert r.returncode == 1, (
        f"skriptet godtok et avvik (exit {r.returncode})\n{r.stdout}\n{r.stderr}")
    assert "felles-css" in r.stderr, "feilmeldingen navngir ikke blokken"
