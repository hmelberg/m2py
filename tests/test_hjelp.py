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


def test_ingen_gammel_scrollspy():
    """Den gamle scroll-highlighteren toggler .active, som har samme styling
    som .nav-active. To scrollspyer med ulik terskel fremhever ofte to
    navlenker samtidig. Bare IntersectionObserver-varianten skal stå."""
    text = (REPO / "hjelp.html").read_text(encoding="utf-8")
    assert "function updateNav" not in text
    assert "classList.toggle('active'" not in text
    assert "initScrollspy" in text, "den nye scrollspyen mangler"


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


@pytest.mark.xfail(
    strict=True,
    reason="Tasks 5-7 legger til #tillit, #kilder, #strict-py, #strict-r",
)
def test_ingen_hengende_interne_lenker():
    """Hver href="#x" skal treffe en seksjon eller overskrift som finnes.
    Fanger at en senere task omdøper eller dropper en seksjon som lag 0
    allerede lenker til."""
    g = grab("hjelp.html")
    mal = set(g.section_ids) | g.heading_ids
    hengende = g.hrefs - mal
    assert not hengende, f"hengende interne lenker (mangler id): {sorted(hengende)}"
