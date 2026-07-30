"""Synk-sjekk for hjelpesidenes fellesseksjoner.

De fire repoene har hver sin hjelp.html. Fellesseksjonene skal være
byte-identiske; dagens tilstand er beviset på at de ellers driver fra
hverandre (askstat sin het «OpenStat» i to måneder)."""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "hjelp_sync_check.sh"

BLOCK_NAMES = [
    "felles-css", "felles-js", "felles-editor", "felles-sidebar",
    "felles-lagre", "felles-forklar", "felles-widgets", "felles-ai",
    "felles-eksempler", "felles-referanse-snarveier", "felles-referanse-tab",
]

HJELP_FILER = ["hjelp.html", "hjelp.en.html"]


def extract_block(text: str, name: str):
    """Hent én SYNC-blokk. Godtar både /* */ og <!-- --> som markør."""
    pat = (r"(?:/\*|<!--)\s*SYNC:START\s+" + re.escape(name)
           + r"\s*(?:\*/|-->)(.*?)(?:/\*|<!--)\s*SYNC:END\s*(?:\*/|-->)")
    m = re.search(pat, text, re.DOTALL)
    return m.group(1) if m else None


def strip_block(text: str, name: str) -> str:
    """Fjern en hel SYNC-blokk — markørene OG innholdet — fra teksten.

    Brukes til å konstruere «blokk mangler hos begge sider»-scenarioet på
    forespørsel, i stedet for å lete etter et blokknavn som allerede er
    fraværende (se test_streng_modus_avviser_manglende_enkeltblokk)."""
    pat = (r"(?:/\*|<!--)\s*SYNC:START\s+" + re.escape(name)
           + r"\s*(?:\*/|-->).*?(?:/\*|<!--)\s*SYNC:END\s*(?:\*/|-->)\n?")
    ny, n = re.subn(pat, "", text, count=1, flags=re.DOTALL)
    assert n == 1, f"fant ikke akkurat én blokk '{name}' å fjerne"
    return ny


def test_skriptet_finnes_og_er_kjorbart():
    assert SCRIPT.exists(), "scripts/hjelp_sync_check.sh mangler"
    assert SCRIPT.stat().st_mode & 0o111, "skriptet er ikke kjørbart"


@pytest.mark.parametrize("filnavn", HJELP_FILER)
def test_alle_blokker_finnes_i_egen_hjelp(filnavn):
    """Hver navngitt blokk skal faktisk finnes i safestat sin hjelp-fil.

    Dekker både hjelp.html og hjelp.en.html — en blokk som mangler i BEGGE
    filer på begge sider av en sammenligning hopper synk-skriptet stille
    over (se hjelp_sync_check.sh), så uten denne parametriseringen ville et
    slettet block-navn i den engelske sida vært et permanent blindsone.

    hjelp.en.html har ingen SYNC-blokker ennå (Task 9 legger dem inn) — den
    hopper selv-aktiverende over basert på fila sitt FAKTISKE innhold, ikke
    et statisk merke noen må huske å fjerne. Så snart Task 9 legger inn
    markørene, begynner denne testen å kjøre den ekte sjekken av seg selv."""
    text = (REPO / filnavn).read_text(encoding="utf-8")
    if "SYNC:START" not in text:
        pytest.skip(f"{filnavn} har ingen SYNC-blokker ennå")
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


def test_streng_modus_avviser_manglende_enkeltblokk(tmp_path):
    """Skiller seg fra test_streng_modus_avviser_manglende_blokker over: der
    hadde fila NULL SYNC-blokker (filnivå-hoppet). Her HAR fila blokker —
    filnivå-sjekken slipper den gjennom — men én bestemt blokk mangler hos
    BEGGE sider. Det er nøyaktig scenarioet fra koordinator-reviewen: en
    blokk (f.eks. felles-referanse-tab) glemt i alle repoer under Task
    9/11/13/15. Før 'continue'-linjen for dette tilfellet i
    hjelp_sync_check.sh ble rutet gjennom skip(), fanget ikke
    HJELP_SYNC_STRICT=1 dette i det hele tatt — strengmodus-påstanden var
    uverifisert nettopp her.

    Nå som safestat har alle elleve blokkene, finnes det ikke lenger et
    blokknavn som mangler av seg selv — så scenarioet bygges direkte: en
    blokk fjernes (markører og innhold) fra en KOPI av hjelp.html, og den
    samme fjernes fra det falske søskenet. Kopien kjøres fra sitt eget
    'hovedrepo' (med en kopi av selve skriptet), slik at skriptets $HERE
    peker dit i stedet for det virkelige safestat-repoet — ellers ville
    skriptet lest den ekte, uendrede hjelp.html og aldri sett hullet."""
    blokknavn = "felles-referanse-tab"  # vilkårlig valg blant BLOCK_NAMES

    no_tekst = (REPO / "hjelp.html").read_text(encoding="utf-8")
    en_tekst = (REPO / "hjelp.en.html").read_text(encoding="utf-8")
    assert extract_block(no_tekst, blokknavn) is not None, (
        f"'{blokknavn}' finnes ikke i hjelp.html — testen kan ikke fjerne den")

    fjernet = strip_block(no_tekst, blokknavn)
    assert extract_block(fjernet, blokknavn) is None
    assert "SYNC:START" in fjernet, (
        "fjerningen tok med seg alle blokkene — filnivå-hoppet ville da "
        "dekket scenarioet i stedet for blokknivå-hoppet vi vil teste")

    # 'hovedrepo': en kopi av det virkelige repoet, men med blokken fjernet
    # fra hjelp.html — dette er $HERE sett fra skriptets eget ståsted.
    hoved = tmp_path / "hovedrepo"
    (hoved / "scripts").mkdir(parents=True)
    hoved_script = hoved / "scripts" / "hjelp_sync_check.sh"
    shutil.copy(SCRIPT, hoved_script)
    hoved_script.chmod(0o755)
    (hoved / "hjelp.html").write_text(fjernet, encoding="utf-8")
    (hoved / "hjelp.en.html").write_text(en_tekst, encoding="utf-8")

    # Falskt søsken: samme blokk fjernet — «mangler hos begge sider».
    falsk = tmp_path / "faksesosken3"
    falsk.mkdir()
    (falsk / "hjelp.html").write_text(fjernet, encoding="utf-8")
    (falsk / "hjelp.en.html").write_text(en_tekst, encoding="utf-8")

    env_base = {**os.environ,
                "HJELP_SYNC_ROOT": str(tmp_path),
                "HJELP_SYNC_SIBLINGS": "faksesosken3"}

    r_lenient = subprocess.run(["sh", str(hoved_script)], cwd=hoved,
                                capture_output=True, text=True, env=env_base)
    assert r_lenient.returncode == 0, (
        "ulåst (standard) modus skal godta en blokk som mangler hos begge "
        f"sider\n{r_lenient.stdout}\n{r_lenient.stderr}")

    r_strict = subprocess.run(
        ["sh", str(hoved_script)], cwd=hoved, capture_output=True, text=True,
        env={**env_base, "HJELP_SYNC_STRICT": "1"})
    assert r_strict.returncode == 1, (
        "streng modus godtok en blokk som mangler hos begge sider "
        f"(exit {r_strict.returncode})\n{r_strict.stdout}\n{r_strict.stderr}")
    assert blokknavn in r_strict.stderr, (
        f"feilmeldingen i streng modus navngir ikke den manglende blokken "
        f"'{blokknavn}'\n{r_strict.stderr}")
