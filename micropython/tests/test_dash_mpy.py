# Enhetstester for micropython/dash.py sin _run()-kontrollflyt (CPython).
#
# `js`-modulen (jsffi) stubbes fullstendig fordi dash.py gjoer `from js import
# window` paa modul-nivaa - stubben maa derfor ligge i sys.modules['js'] FOER
# modulen lastes (samme knep som tests/test_pyodide_dash.py bruker for
# pyodide/dash.py).
#
# CPython-mangle-fella (IKKE en MicroPython-dialektfelle - MicroPython
# mangler ikke dunder-navn i klassekropper by default, saa produksjonskoden
# er upaavirket): `Dash._run()` kaller `window.__mpyCaptureStart()` og
# `window.__mpyCaptureEnd()`. Disse identifikatorene ligger tekstlig inne i
# `class Dash`, saa CPythons kompilator name-mangler dem til
# `window._Dash__mpyCaptureStart()`/`window._Dash__mpyCaptureEnd()` - IKKE de
# bokstavelige navnene. FakeWindow under eksponerer derfor metodene under de
# manglede navnene, ellers ville testene faatt AttributeError paa noe
# produksjonskoden aldri ser (MicroPython gjoer ingen slik mangling).
import importlib.util
import json
import pathlib
import sys
import types

import pytest


class FakeDashJs:
    def __init__(self):
        self.calls = {"create": [], "addCard": [], "updateCard": [], "addControls": []}

    def create(self, opts_json):
        self.calls["create"].append(json.loads(opts_json))
        return "dash%d" % len(self.calls["create"])

    def addCard(self, dash_id, opts_json, on_change, node):
        self.calls["addCard"].append(
            {"dash": dash_id, "opts": json.loads(opts_json),
             "on_change": on_change, "node": node})
        return "card%d" % len(self.calls["addCard"])

    def updateCard(self, cid, payload_json, node):
        self.calls["updateCard"].append(
            {"cid": cid, "payload": json.loads(payload_json), "node": node})

    def addControls(self, dash_id, specs_json, on_change):
        self.calls["addControls"].append(
            {"dash": dash_id, "specs": json.loads(specs_json),
             "on_change": on_change})

    def initialValues(self, id_):
        return "{}"

    def isAlive(self, id_):
        return True


class FakeWindow:
    """Emulerer js/micropython-engine.js sitt `window`: Dash-broen (uendret
    API mot pyodide/brython-sostrene) pluss capture-parets NAVNEMANGLEDE
    metoder (se filhode-kommentaren)."""

    def __init__(self, capture_text=""):
        self.Dash = FakeDashJs()
        self.capture_calls = []      # kronologisk logg: "start"/"end"
        self._capture_text = capture_text

    def _Dash__mpyCaptureStart(self):
        self.capture_calls.append("start")

    def _Dash__mpyCaptureEnd(self):
        self.capture_calls.append("end")
        text, self._capture_text = self._capture_text, ""
        return text


@pytest.fixture()
def dash(monkeypatch):
    js = types.ModuleType("js")
    js.window = FakeWindow()
    monkeypatch.setitem(sys.modules, "js", js)
    path = pathlib.Path(__file__).resolve().parents[1] / "dash.py"
    spec = importlib.util.spec_from_file_location("dash_mpy_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fake_window(dash):
    from js import window  # stubben satt i fixturen over
    return window


def last_payload(dash):
    return fake_window(dash).Dash.calls["updateCard"][-1]["payload"]


class _PendingExc(Exception):
    """Emulerer duckdb-broens replay-signal (__brython_pending__)."""
    __brython_pending__ = True


class _BadFrame:
    """Objekt med to_html() som kaster - typisk for et duckdb/pandas-resultat
    som feiler under selve renderingen (etter at callbacken har returnert)."""
    def __init__(self, exc):
        self._exc = exc

    def to_html(self):
        raise self._exc


class _OkFrame:
    """Objekt med en to_html() som virker - "table"-payload-veien."""
    columns = ["a", "b"]

    def to_html(self):
        return "<table><tr><td>a</td><td>b</td></tr></table>"


# ---- (1) unntak UNDER rendering (_payload/to_html) -> feilkort, ikke propagert ----

def test_to_html_som_kaster_gir_feilkort_ikke_propagert(dash):
    d = dash.dashboard("T")
    # callbacken selv lykkes og returnerer et objekt hvis to_html() kaster
    # foerst NAAR _payload() prosesserer resultatet.
    d.add(lambda: _BadFrame(RuntimeError("boom")))
    p = last_payload(dash)
    assert p["kind"] == "error"
    assert "RuntimeError" in p["message"] and "boom" in p["message"]


def test_pending_exception_under_to_html_gir_sql_cache_melding(dash):
    d = dash.dashboard("T")
    d.add(lambda: _BadFrame(_PendingExc("ikke i cache")))
    p = last_payload(dash)
    assert p["kind"] == "error"
    assert "SQL-sporringen er ikke i cache" in p["message"]


# ---- (2) capture start/end kalles parvis, ogsaa naar callbacken selv kaster ----

def test_capture_kalles_parvis_naar_callback_kaster(dash):
    d = dash.dashboard("T")
    d.add(lambda: 1 / 0)
    win = fake_window(dash)
    assert win.capture_calls == ["start", "end"]
    p = last_payload(dash)
    assert p["kind"] == "error" and "ZeroDivisionError" in p["message"]


def test_capture_kalles_parvis_naar_to_html_kaster(dash):
    d = dash.dashboard("T")
    d.add(lambda: _BadFrame(RuntimeError("boom")))
    win = fake_window(dash)
    # __mpyCaptureEnd() maa vaere kalt NOYAKTIG en gang (destruktiv engangslesing) -
    # skjer rett etter selve funksjonskallet, foer _payload() faar sjansen til aa kaste.
    assert win.capture_calls == ["start", "end"]


def test_capture_kalles_parvis_ved_normal_kjoering(dash):
    d = dash.dashboard("T")
    d.add(lambda: "hei")
    win = fake_window(dash)
    assert win.capture_calls == ["start", "end"]


# ---- (3) normal payload-vei gir riktig kind ----

def test_streng_gir_markdown_kind(dash):
    d = dash.dashboard("T")
    d.add(lambda: "hallo verden")
    p = last_payload(dash)
    assert p == {"kind": "markdown", "text": "hallo verden"}


def test_objekt_med_virkende_to_html_gir_table_kind(dash):
    d = dash.dashboard("T")
    d.add(lambda: _OkFrame())
    p = last_payload(dash)
    assert p["kind"] == "table"
    assert "<table" in p["html"]
    assert p["cols"] == 2


def test_print_fanges_naar_retur_er_none(dash):
    win = fake_window(dash)
    win._capture_text = "hei 3"
    d = dash.dashboard("T")
    d.add(lambda: print("hei", 3) or None)
    p = last_payload(dash)
    assert p == {"kind": "text", "text": "hei 3"}
