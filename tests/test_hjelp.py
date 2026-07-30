"""Strukturtester for hjelp.html som gjelder på tvers av de fire repoene.
Task 4 og senere tasks utvider denne fila.

Identitet, påkrevde seksjoner og forbudte strenger. Testen finnes fordi
askstat sin hjelpeside het «OpenStat» i to måneder uten at noe fanget det."""
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

IDENTITY = {
    "safestat": {
        "title_no": "SafeStat – Dokumentasjon",
        "title_en": "SafeStat – Documentation",
        "h1": "SafeStat",
        "nav_logo": "SafeStat",
        "lead_no": "Analyser beskyttede data uten at dataene forlater det trygge.",
    },
}

FORBUDT_OVERALT = ["Microdata Script Runner"]


def read(fil: str) -> str:
    return (REPO / fil).read_text(encoding="utf-8")


class _Grab(HTMLParser):
    """Plukker ut title, første h1, nav-logo, lead, alle section-id-er,
    overskrift-id-er og interne href="#..."-mål.
    Bruker stdlib — bs4 er ikke installert og skal ikke installeres."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = None
        self.h1 = None
        self.nav_logo = None
        self.lead = None
        self.section_ids = []
        self.heading_ids = set()
        self.hrefs = set()
        self._want = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._want = "title"
        elif tag == "h1" and self.h1 is None:
            self._want = "h1"
        elif tag == "div" and a.get("class") == "nav-logo":
            self._want = "nav_logo"
        elif tag == "p" and a.get("class") == "lead":
            self._want = "lead"
        elif tag == "section" and a.get("id"):
            self.section_ids.append(a["id"])
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6") and a.get("id"):
            self.heading_ids.add(a["id"])
        href = a.get("href")
        if href and href.startswith("#") and len(href) > 1:
            self.hrefs.add(href[1:])

    def handle_data(self, data):
        if self._want and data.strip():
            setattr(self, self._want, data.strip())
            self._want = None

    def handle_endtag(self, tag):
        self._want = None


def grab(fil: str) -> _Grab:
    p = _Grab()
    p.feed(read(fil))
    return p


@pytest.mark.parametrize("fil", ["hjelp.html", "hjelp.en.html"])
def test_ingen_gammel_scrollspy(fil):
    """Den gamle scroll-highlighteren toggler .active, som har samme styling
    som .nav-active. To scrollspyer med ulik terskel fremhever ofte to
    navlenker samtidig. Bare IntersectionObserver-varianten skal stå."""
    text = read(fil)
    assert "function updateNav" not in text
    assert "classList.toggle('active'" not in text
    assert "initScrollspy" in text, f"den nye scrollspyen mangler i {fil}"


@pytest.mark.parametrize("fil", ["hjelp.html", "hjelp.en.html"])
def test_ingen_forbudte_strenger(fil):
    text = read(fil)
    for s in FORBUDT_OVERALT:
        assert s not in text, f"{fil} inneholder fortsatt «{s}»"


def test_identitet_norsk():
    ident = IDENTITY["safestat"]
    g = grab("hjelp.html")
    assert g.title == ident["title_no"]
    assert g.h1 == ident["h1"]
    assert g.nav_logo == ident["nav_logo"]
    assert g.lead == ident["lead_no"]


def test_identitet_engelsk():
    ident = IDENTITY["safestat"]
    g = grab("hjelp.en.html")
    assert g.title == ident["title_en"]
    assert g.h1 == ident["h1"]
    assert g.nav_logo == ident["nav_logo"]


def test_lag0_seksjoner_finnes():
    ids = grab("hjelp.html").section_ids
    for s in ("intro", "hurtigstart"):
        assert s in ids, f"mangler seksjon #{s}"


def test_navfilter_finnes():
    assert 'class="nav-filter"' in read("hjelp.html")


def test_denne_siden_dekker_tabell():
    """Lag 0 skal ha en oversiktstabell, ikke bare prosa."""
    text = read("hjelp.html")
    m = re.search(r'<section id="intro".*?</section>', text, re.DOTALL)
    assert m, "fant ikke intro-seksjonen"
    assert 'class="overview"' in m.group(0), "intro mangler oversiktstabell"


def test_tillit_og_kilder_finnes():
    ids = grab("hjelp.html").section_ids
    for s in ("tillit", "kilder"):
        assert s in ids, f"mangler seksjon #{s}"


def test_tillit_har_oversiktstabell():
    text = read("hjelp.html")
    m = re.search(r'<section id="tillit".*?</section>', text, re.DOTALL)
    assert m, "fant ikke tillit-seksjonen"
    blokk = m.group(0)
    assert 'class="doc-table"' in blokk, "tillit mangler tabell"
    # De tre nivåene skal navngis eksplisitt.
    for niva in ("public", "protected", "sensitive"):
        assert niva in blokk, f"tillit nevner ikke nivået «{niva}»"


def test_strict_py_har_avvist_eksempel_med_ekte_feilmelding():
    """Seksjonen skal vise et eksempel som blir avvist, med safepy sin
    faktiske feilmelding — ikke en omskrevet variant."""
    text = read("hjelp.html")
    m = re.search(r'<section id="strict-py".*?</section>', text, re.DOTALL)
    assert m, "fant ikke strict-py-seksjonen"
    blokk = m.group(0)
    assert "'head' is not allowed" in blokk
    assert "reveal individual rows" in blokk


def test_strict_py_resultatblokker_stemmer_med_harness():
    """Hver <pre class="result"> i strict-py skal finnes ordrett i en
    outputfil fra harnessen. Fanger resultater som er redigert for hånd."""
    outdir = REPO / "docs" / "hjelp_examples" / "output"
    kjort = [f.read_text(encoding="utf-8").strip() for f in outdir.glob("*.txt")]
    text = read("hjelp.html")
    m = re.search(r'<section id="strict-py".*?</section>', text, re.DOTALL)
    assert m
    blokker = re.findall(r'<pre class="result">(.*?)</pre>', m.group(0), re.DOTALL)
    assert blokker, "strict-py har ingen resultatblokker"
    import html as _html
    for b in blokker:
        ren = _html.unescape(b).strip()
        assert any(ren == k for k in kjort), (
            f"resultatblokk finnes ikke i harness-output:\n{ren[:200]}")


def test_ingen_hengende_interne_lenker():
    """Hver href="#x" skal treffe en seksjon eller overskrift som finnes.
    Fanger at en senere task omdøper eller dropper en seksjon som lag 0
    allerede lenker til."""
    g = grab("hjelp.html")
    mal = set(g.section_ids) | g.heading_ids
    hengende = g.hrefs - mal
    assert not hengende, f"hengende interne lenker (mangler id): {sorted(hengende)}"


def test_strict_r_har_avvist_eksempel():
    text = read("hjelp.html")
    m = re.search(r'<section id="strict-r".*?</section>', text, re.DOTALL)
    assert m, "fant ikke strict-r-seksjonen"
    assert "base-R function 'head' is not supported" in m.group(0)


def test_strict_r_og_sql_finnes():
    ids = grab("hjelp.html").section_ids
    for s in ("strict-r", "strict-sql"):
        assert s in ids, f"mangler seksjon #{s}"


def test_r_dialekten_er_beskrevet_som_oversatt():
    """R-koden oversettes, den kjøres aldri direkte. Leseren må få vite det,
    ellers forventer de at hele R er tilgjengelig."""
    text = read("hjelp.html")
    m = re.search(r'<section id="strict-r".*?</section>', text, re.DOTALL)
    assert m
    blokk = m.group(0).lower()
    assert "oversett" in blokk, "strict-r sier ikke at koden oversettes"


def test_strict_r_og_sql_resultatblokker_stemmer_med_harness():
    """Hver <pre class="result"> i strict-r/strict-sql skal finnes ordrett i
    en outputfil fra harnessen. Fanger resultater som er redigert for hånd."""
    outdir = REPO / "docs" / "hjelp_examples" / "output"
    kjort = [f.read_text(encoding="utf-8").strip() for f in outdir.glob("*.txt")]
    text = read("hjelp.html")
    import html as _html
    for sid in ("strict-r", "strict-sql"):
        m = re.search(rf'<section id="{sid}".*?</section>', text, re.DOTALL)
        assert m, f"fant ikke {sid}-seksjonen"
        blokker = re.findall(r'<pre class="result">(.*?)</pre>', m.group(0), re.DOTALL)
        assert blokker, f"{sid} har ingen resultatblokker"
        for b in blokker:
            ren = _html.unescape(b).strip()
            assert any(ren == k for k in kjort), (
                f"{sid}: resultatblokk finnes ikke i harness-output:\n{ren[:200]}")


def test_gammel_strict_seksjon_er_borte():
    """Den gamle #strict dekket alle tre dialektene på femten linjer og er
    erstattet av #strict-py/#strict-r/#strict-sql. To sett regler for det
    samme er verre enn ingen."""
    ids = grab("hjelp.html").section_ids
    assert "strict" not in ids, "den gamle #strict-seksjonen står fortsatt"
    for ny in ("strict-py", "strict-r", "strict-sql"):
        assert ny in ids, f"mangler #{ny}"


def test_ikke_kjorte_resultater_er_merket():
    """Et resultat som ikke kommer fra harnessen skal bære klassen
    'illustration' OG ordet «illustrasjon» synlig for leseren. Ellers ser
    oppdiktede tall ut som kjørt output."""
    text = read("hjelp.html")
    for m in re.finditer(r'<section id="(federert|nokler)".*?</section>',
                         text, re.DOTALL):
        seksjon = m.group(0)
        for res in re.findall(r'<pre class="result([^"]*)">', seksjon):
            assert "illustration" in res, (
                f"resultatblokk i #{m.group(1)} er ikke merket som illustrasjon")
        if 'class="result illustration"' in seksjon:
            assert "illustrasjon" in seksjon.lower(), (
                f"#{m.group(1)} mangler synlig «illustrasjon»-merking")


def test_federert_og_nokler_finnes():
    ids = grab("hjelp.html").section_ids
    for s in ("federert", "nokler"):
        assert s in ids, f"mangler seksjon #{s}"


# ── Task 9: lag 2 og lag 3 i SYNC-blokker ──────────────────────────────────

SYNC_BLOKKER = [
    "felles-css", "felles-js", "felles-running", "felles-editor",
    "felles-sidebar", "felles-lagre", "felles-forklar", "felles-widgets",
    "felles-ai", "felles-eksempler", "felles-referanse-snarveier",
    "felles-referanse-tab",
]

APPNAVN = ["SafeStat", "OpenStat", "AskStat", "Microdata"]


def _block(text, name):
    pat = (r"(?:/\*|<!--)\s*SYNC:START\s+" + re.escape(name)
           + r"\s*(?:\*/|-->)(.*?)(?:/\*|<!--)\s*SYNC:END\s*(?:\*/|-->)")
    m = re.search(pat, text, re.DOTALL)
    return m.group(1) if m else None


@pytest.mark.parametrize("navn", SYNC_BLOKKER)
def test_sync_blokk_finnes(navn):
    assert _block(read("hjelp.html"), navn) is not None, f"mangler {navn}"


@pytest.mark.parametrize("navn", SYNC_BLOKKER)
def test_sync_blokk_er_repo_noytral(navn):
    """En fellesblokk skal ikke nevne et appnavn — da kan den ikke deles."""
    blokk = _block(read("hjelp.html"), navn)
    assert blokk is not None
    for navn_app in APPNAVN:
        assert navn_app not in blokk, (
            f"{navn} nevner «{navn_app}»; flytt det til lag 0 eller lag 1")


def test_modustabell_finnes_og_er_utenfor_sync():
    """Modustabellen er repo-spesifikk og skal IKKE ligge i en SYNC-blokk."""
    text = read("hjelp.html")
    m = re.search(r'<section id="modes".*?</section>', text, re.DOTALL)
    assert m, "fant ikke modes-seksjonen"
    blokk = m.group(0)
    assert 'class="doc-table"' in blokk, "modes mangler tabell"
    assert "SYNC:START" not in blokk, "modustabellen skal ikke være i en SYNC-blokk"
    # safestat har microdata og safestat (remote) i tillegg til de sju vanlige.
    for modus in ("microdata", "Python", "R", "DuckDB", "Brython",
                  "MicroPython", "SafeStat"):
        assert modus in blokk, f"modustabellen mangler «{modus}»"


# ── Task 9b: den engelske sida tar igjen resten ────────────────────────────

EN_SEKSJONER = [
    "intro", "hurtigstart", "tillit", "kilder", "strict-py", "strict-r",
    "strict-sql", "federert", "nokler", "modes", "editor", "sidebar",
    "lagre-dele", "forklar", "widgets", "ai", "eksempler", "tab-full",
]


@pytest.mark.parametrize("seksjon", EN_SEKSJONER)
def test_engelsk_har_samme_seksjoner(seksjon):
    # Samme seksjons-id-er som den norske — ellers peker delte nav-lenker
    # i tomme luften.
    assert seksjon in grab("hjelp.en.html").section_ids


def test_engelsk_har_sync_blokkene():
    # Uten felles-css og felles-js har den engelske sida verken scrollspy,
    # navfilter eller styling — og synk-sjekken feller den i streng modus.
    text = read("hjelp.en.html")
    for navn in SYNC_BLOKKER:
        assert _block(text, navn) is not None, f"mangler {navn} i hjelp.en.html"


def test_engelsk_har_ingen_norsk_rest():
    # Gamle norsk-avledede avsnitt som beskriver appen som en
    # microdata.no-kjører skal være borte.
    text = read("hjelp.en.html")
    for rest in ("Script Runner", "Microdata Script Runner"):
        assert rest not in text, f"«{rest}» står igjen i hjelp.en.html"


def test_engelsk_resultatblokker_er_identiske_med_norske():
    # Tall er tall. En resultatblokk som avviker mellom språkene betyr at
    # noen har redigert output for hånd.
    import html as _html
    no = re.findall(r'<pre class="result">(.*?)</pre>', read("hjelp.html"), re.DOTALL)
    en = re.findall(r'<pre class="result">(.*?)</pre>', read("hjelp.en.html"), re.DOTALL)
    assert no, "fant ingen resultatblokker i hjelp.html"
    norm = lambda xs: sorted(_html.unescape(x).strip() for x in xs)
    assert norm(no) == norm(en), "resultatblokkene skiller seg mellom språkene"
