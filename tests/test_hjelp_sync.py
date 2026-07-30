"""Synk-sjekk for hjelpesidenes fellesseksjoner.

De fire repoene har hver sin hjelp.html. Fellesseksjonene skal være
byte-identiske; dagens tilstand er beviset på at de ellers driver fra
hverandre (askstat sin het «OpenStat» i to måneder)."""
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "hjelp_sync_check.sh"

BLOCK_NAMES = [
    "felles-css", "felles-js",
    # Task 9:
    # "felles-editor", "felles-sidebar",
    # "felles-lagre", "felles-forklar", "felles-widgets", "felles-ai",
    # "felles-eksempler", "felles-referanse-snarveier", "felles-referanse-tab",
]

# hjelp.en.html har ingen SYNC-blokker ennå (Task 2 rørte kun hjelp.html;
# Task 9 legger dem inn i den engelske sida). Eksplisitt utsatt, ikke bare
# fraværende — se marks= under.
HJELP_FILER = [
    "hjelp.html",
    pytest.param(
        "hjelp.en.html",
        marks=pytest.mark.skip(
            reason="Task 9: hjelp.en.html har ingen SYNC-blokker ennå"),
    ),
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


@pytest.mark.parametrize("filnavn", HJELP_FILER)
def test_alle_blokker_finnes_i_egen_hjelp(filnavn):
    """Hver navngitt blokk skal faktisk finnes i safestat sin hjelp-fil.

    Dekker både hjelp.html og hjelp.en.html — en blokk som mangler i BEGGE
    filer på begge sider av en sammenligning hopper synk-skriptet stille
    over (se hjelp_sync_check.sh), så uten denne parametriseringen ville et
    slettet block-navn i den engelske sida vært et permanent blindsone."""
    text = (REPO / filnavn).read_text(encoding="utf-8")
    mangler = [n for n in BLOCK_NAMES if extract_block(text, n) is None]
    assert not mangler, f"{filnavn} mangler SYNC-blokker: {mangler}"


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


def test_streng_modus_avviser_manglende_blokker(tmp_path):
    """HJELP_SYNC_STRICT=1 skal ikke godta at en fil hopper stille over fordi
    den ikke har noen SYNC-blokker. Uten dette kunne en kopi som stille
    bommer på én fil (f.eks. hjelp.en.html i et søsken) likevel gi exit 0 på
    Task 17 sin sluttport — nøyaktig hullet strengmodus finnes for å tette."""
    falsk = tmp_path / "faksesosken2"
    falsk.mkdir()
    # hjelp.html mistet SYNC-blokkene sine i kopieringen: null blokker, som
    # om et søsken sin kopi stille bommet på denne fila.
    (falsk / "hjelp.html").write_text(
        "<html><body>ingen sync-blokker her</body></html>", encoding="utf-8")
    (falsk / "hjelp.en.html").write_text(
        (REPO / "hjelp.en.html").read_text(encoding="utf-8"), encoding="utf-8")

    env_base = {**os.environ,
                "HJELP_SYNC_ROOT": str(tmp_path),
                "HJELP_SYNC_SIBLINGS": "faksesosken2"}

    r_lenient = subprocess.run(["sh", str(SCRIPT)], cwd=REPO,
                                capture_output=True, text=True, env=env_base)
    assert r_lenient.returncode == 0, (
        "ulåst (standard) modus skal fortsatt godta en fil uten "
        f"SYNC-blokker under utrulling\n{r_lenient.stdout}\n{r_lenient.stderr}")

    r_strict = subprocess.run(
        ["sh", str(SCRIPT)], cwd=REPO, capture_output=True, text=True,
        env={**env_base, "HJELP_SYNC_STRICT": "1"})
    assert r_strict.returncode == 1, (
        "streng modus godtok en fil uten SYNC-blokker "
        f"(exit {r_strict.returncode})\n{r_strict.stdout}\n{r_strict.stderr}")
    assert "hjelp.html" in r_strict.stderr, (
        "feilmeldingen i streng modus navngir ikke fila som mangler blokker")
