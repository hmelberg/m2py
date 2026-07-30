"""Strukturtester for hjelp.html som gjelder på tvers av de fire repoene.
Task 4 og senere tasks utvider denne fila."""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_ingen_gammel_scrollspy():
    """Den gamle scroll-highlighteren toggler .active, som har samme styling
    som .nav-active. To scrollspyer med ulik terskel fremhever ofte to
    navlenker samtidig. Bare IntersectionObserver-varianten skal stå."""
    text = (REPO / "hjelp.html").read_text(encoding="utf-8")
    assert "function updateNav" not in text
    assert "classList.toggle('active'" not in text
    assert "initScrollspy" in text, "den nye scrollspyen mangler"
