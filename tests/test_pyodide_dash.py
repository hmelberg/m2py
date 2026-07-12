"""pyodide/dash.py sin rene logikk testet i CPython: `js` og `pyodide.ffi`
stubbes, saa _infer/_payload/dashboard-flyten kan kjoeres uten browser."""
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


@pytest.fixture()
def dash(monkeypatch):
    js = types.ModuleType("js")
    js.window = types.SimpleNamespace(Dash=FakeDashJs())
    monkeypatch.setitem(sys.modules, "js", js)
    path = pathlib.Path(__file__).resolve().parents[1] / "pyodide" / "dash.py"
    spec = importlib.util.spec_from_file_location("dash_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fake(dash):
    from js import window  # stubben over
    return window.Dash


def test_number_payload_er_raa_v3(dash):
    p = dash._payload(42.5, unit="kr", fmt=",.1f", ref=40, bra="opp")
    assert p == {"kind": "number", "value": 42.5, "unit": "kr",
                 "fmt": ",.1f", "ref": 40, "bra": "opp"}


def test_number_payload_nan_ref_saniteres(dash):
    p = dash._payload(1.0, ref=float("nan"))
    assert p["ref"] is None


def test_nan_verdi_blir_tekst(dash):
    assert dash._payload(float("nan"))["kind"] == "text"


def test_infer_tuple_liste_bool(dash):
    assert dash._infer("bins", (5, 50)).kind == "slider"
    assert dash._infer("art", ["a", "b"]).kind == "dropdown"
    assert dash._infer("vis", True).kind == "checkbox"
    assert dash._infer("navn", "x").kind == "textfield"
    assert dash._infer("n", 7).kind == "numberfield"


def test_funksjonskort_foerste_render(dash):
    d = dash.dashboard("T")
    d.add(lambda bins: bins * 2, bins=(5, 50))
    calls = fake(dash).calls
    assert len(calls["addCard"]) == 1
    specs = calls["addCard"][0]["opts"]["controls"]
    assert specs[0]["type"] == "slider" and specs[0]["name"] == "bins"
    # foerste kjoering med default (min=5) -> updateCard med number 10
    up = calls["updateCard"][-1]["payload"]
    assert up["kind"] == "number" and up["value"] == 10


def test_print_fanges_naar_retur_er_none(dash):
    d = dash.dashboard("T")
    d.add(lambda n: print("hei", n), n=3)
    up = fake(dash).calls["updateCard"][-1]["payload"]
    assert up == {"kind": "text", "text": "hei 3"}


def test_exception_gir_feilkort(dash):
    d = dash.dashboard("T")
    d.add(lambda n: 1 / 0, n=3)
    up = fake(dash).calls["updateCard"][-1]["payload"]
    assert up["kind"] == "error" and "ZeroDivisionError" in up["message"]


def test_controls_rekjoerer_kort_med_navneoverlapp(dash):
    d = dash.dashboard("T")
    d.add(lambda aar: aar * 1)
    before = len(fake(dash).calls["updateCard"])
    d.controls(aar=(2020, 2026))
    calls = fake(dash).calls
    assert len(calls["addControls"]) == 1
    assert len(calls["updateCard"]) == before + 1  # kortet rekjoert med delt default
    assert calls["updateCard"][-1]["payload"]["value"] == 2020
