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


# ---- (4) _func_params: __code__-fallback for MicroPython (c_no_dunder_code) ----
#
# MicroPython-funksjoner mangler __code__ - se filhode-kommentaren i dash.py
# punkt 3. Under CPython/pytest TAR alle ekte def-funksjoner (og lambdaer)
# alltid __code__-veien (den er alltid til stede), saa fallback-parseren
# testes her paa to måter: (a) DIREKTE mot _parse_params_from_source med
# haandskrevne kildestrenger (dekker parse-logikken uavhengig av om noe
# objekt faktisk mangler __code__), og (b) via _func_params selv med et
# konstruert "MicroPython-lignende" objekt (callable, har __name__, har
# INGEN __code__-attributt) for aa oeve selve AttributeError-fallback-grenen
# og window.__mpySource()-oppslaget ende-til-ende.
#
# `win.__mpySource = ...` under settes UTENFOR enhver klassekropp (i en
# vanlig testfunksjon) - se `_Dash__mpyCaptureStart/End`-kommentaren i
# filhodet for hvorfor navnemangling er relevant her: dash.py sitt
# `window.__mpySource()`-kall skjer i `_func_params`, en MODULFUNKSJON
# (utenfor "class Dash"), saa CPython mangler IKKE selve kallet - stubben
# maa derfor eksponere det BOKSTAVELIGE navnet `__mpySource`. Ville vi satt
# det via en `def __mpySource(self):` INNI FakeWindow-klassekroppen, hadde
# CPythons kompilator manglet SELVE DEFINISJONEN til `_FakeWindow__mpySource`
# (mangling gjelder ethvert `__navn`-forekomst tekstlig inne i en
# klassedefinisjon, ogsaa def-statements) - da ville `window.__mpySource()`
# fra dash.py feilet med AttributeError. Attributt-tilordning i en vanlig
# funksjon (ikke i en klassekropp) mangler IKKE, saa `win.__mpySource = fn`
# her gir et oppslaabart, bokstavelig `__mpySource`-attributt.

class _NoCodeFunc:
    """Emulerer en MicroPython-funksjon: callable, har __name__, har IKKE
    __code__ (getattr(f, '__code__', MISSING) gir AttributeError, akkurat
    som en ekte MicroPython-funksjon gjor - fase 0-funn)."""
    def __init__(self, name):
        self.__name__ = name

    def __call__(self, **kwargs):
        return None


class _NoCodeLambda(_NoCodeFunc):
    def __init__(self):
        super().__init__("<lambda>")


def test_parse_params_enkel_def(dash):
    src = "def f(a, b):\n    pass\n"
    assert dash._parse_params_from_source(src, "f") == ["a", "b"]


def test_parse_params_defaults_med_parenteser_og_komma_i_streng(dash):
    src = 'def f(a, b=(1,2), c="x,y"):\n    pass\n'
    assert dash._parse_params_from_source(src, "f") == ["a", "b", "c"]


def test_parse_params_annotasjoner(dash):
    src = 'def f(a: int, b: str = "z") -> None:\n    pass\n'
    assert dash._parse_params_from_source(src, "f") == ["a", "b"]


def test_parse_params_args_kwargs_droppes(dash):
    src = "def f(a, *args, **kwargs):\n    pass\n"
    assert dash._parse_params_from_source(src, "f") == ["a"]


def test_parse_params_kwonly_etter_stjerne_tas_med(dash):
    # NB: co_varnames-veien (CPython/__code__) tar med kwonly-parametre -
    # fallback-parseren maa matche det, ikke bare droppe alt etter '*'.
    src = "def f(a, *, b):\n    pass\n"
    assert dash._parse_params_from_source(src, "f") == ["a", "b"]


def test_parse_params_siste_definisjon_vinner_samme_script(dash):
    src = "def f(a):\n    pass\ndef f(a, b):\n    pass\n"
    assert dash._parse_params_from_source(src, "f") == ["a", "b"]


def test_parse_params_siste_definisjon_vinner_paa_tvers_av_scriptlogg(dash):
    # __mpySource() slaar sammen flere run()-kall (se js/micropython-
    # engine.js) - nyeste script staar sist. Samme fasit: bakerste treff
    # vinner uavhengig av script-grenser.
    eldre = "def f(a, b):\n    pass\n"
    nyere = "def f(x):\n    pass\n"
    src = eldre + "\n\x00SCRIPT\x00\n" + nyere
    assert dash._parse_params_from_source(src, "f") == ["x"]


def test_parse_params_funksjon_ikke_funnet_gir_norsk_value_error(dash):
    with pytest.raises(ValueError, match="fant ikke parametrene"):
        dash._parse_params_from_source("def g(x):\n pass\n", "f")


def test_func_params_bruker_code_naar_tilgjengelig(dash):
    def f(a, b):
        pass
    assert dash._func_params(f) == ["a", "b"]


def test_func_params_faller_tilbake_til_kildeparsing_uten_code(dash):
    win = fake_window(dash)
    win.__mpySource = lambda: "def minfunk(a, b=2):\n    pass\n"
    assert dash._func_params(_NoCodeFunc("minfunk")) == ["a", "b"]


def test_func_params_lambda_uten_code_gir_norsk_feil(dash):
    with pytest.raises(ValueError, match="lambda"):
        dash._func_params(_NoCodeLambda())


def test_func_params_uten_code_og_uten_mpysource_gir_norsk_feil(dash):
    # FakeWindow har ingen __mpySource by default -> window.__mpySource()
    # kaster AttributeError, fanges av _func_params, gir tydelig norsk feil
    # (IKKE en stille tom liste).
    with pytest.raises(ValueError, match="fant ikke parametrene"):
        dash._func_params(_NoCodeFunc("ukjent"))


def test_func_params_funksjon_ikke_i_loggen_gir_norsk_feil(dash):
    win = fake_window(dash)
    win.__mpySource = lambda: "def annenfunk(z):\n    pass\n"
    with pytest.raises(ValueError, match="fant ikke parametrene"):
        dash._func_params(_NoCodeFunc("minfunk"))
