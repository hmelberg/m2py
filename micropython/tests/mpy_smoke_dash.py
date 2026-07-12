# Kjøres under unix-micropython: micropython micropython/tests/mpy_smoke_dash.py
#
# Ende-til-ende-røyk for dash.py sin _func_params()-fallback (se filhode-
# kommentaren punkt 3 i dash.py, og js/micropython-engine.js sin
# __scriptLog/__mpySource()): MicroPython-funksjoner mangler __code__, så
# dash.add(<funksjon>) må hente parameternavnene ved å tekst-parse en
# kildelogg i stedet. Stubber `js`-modulen (window.Dash-broen +
# capture-hooks + __mpySource()) med samme knep som task-6-rapportens
# lastesjekk ("MPY-DASH-LASTING OK"), definerer én funksjon BÅDE som ekte
# MicroPython-funksjon OG som kildetekst i __mpySource()-stubben (samme
# navn/signatur - simulerer at motoren logget scriptet funksjonen ble
# definert i), og verifiserer at dash.Dash(...).add(f) henter riktige
# parameternavn og bygger et fungerende kort uten å krasje.
import sys
sys.path.insert(0, 'micropython')
import json

# Kildeteksten __mpySource() ville returnert dersom dette var scriptet
# motoren nettopp kjørte (js/micropython-engine.js logger scriptet FØR
# _execute_code, se run()). Signaturen matcher meinfunk under nøyaktig.
TEST_SOURCE = (
    "def meinfunk(a=2, b=5):\n"
    "    return a + b\n"
)


class FakeDashJs:
    """Minimal stub av window.Dash (js/dash.js) - fanger opp addCard/
    updateCard slik at vi kan inspisere kortet _run() bygde."""
    def __init__(self):
        self.cards = {}
        self._n = 0

    def create(self, opts_json):
        return "dash1"

    def addCard(self, dash_id, opts_json, on_change, node):
        self._n += 1
        cid = "card%d" % self._n
        self.cards[cid] = {"opts": json.loads(opts_json)}
        return cid

    def updateCard(self, cid, payload_json, node):
        self.cards[cid]["last_payload"] = json.loads(payload_json)

    def addControls(self, dash_id, specs_json, on_change):
        pass

    def initialValues(self, id_):
        return "{}"

    def isAlive(self, id_):
        return True


class FakeWindow:
    """Emulerer window slik js/micropython-engine.js eksponerer den:
    Dash-broen, capture-hookene (__mpyCaptureStart/End) og kildelogg-
    getteren (__mpySource) - se dash.py sin _func_params()-fallback.
    MicroPython mangler IKKE dunder-navn i klassekropper (bekreftet i
    test_dash_mpy.py sin filhode-kommentar), så disse kan hete akkurat det
    produksjonskoden kaller - ingen navnemanglings-omvei nødvendig her,
    i motsetning til CPython/pytest-versjonen av denne stubben."""
    def __init__(self):
        self.Dash = FakeDashJs()
        self.capture_calls = []

    def __mpyCaptureStart(self):
        self.capture_calls.append("start")

    def __mpyCaptureEnd(self):
        self.capture_calls.append("end")
        return ""

    def __mpySource(self):
        return TEST_SOURCE


class _JsModuleStub:
    pass


sys.modules['js'] = _JsModuleStub()
sys.modules['js'].window = FakeWindow()

import dash


# Den "ekte" funksjonen - definert på toppnivå akkurat som en runner-script
# ville gjort det. Under MicroPython har DENNE ingen __code__, så
# dash.add() må gå fallback-veien og tekst-parse TEST_SOURCE over for å
# finne parameternavnene 'a' og 'b'.
def meinfunk(a=2, b=5):
    return a + b


d = dash.Dash("smoke")
d.add(meinfunk)

cids = list(d._cards.keys())
assert len(cids) == 1, "forventet noyaktig ett kort, fikk %d" % len(cids)
cid = cids[0]
card = d._cards[cid]
assert card["params"] == ["a", "b"], "feil parametre fra fallback-parseren: %r" % (card["params"],)

win = sys.modules['js'].window
payload = win.Dash.cards[cid]["last_payload"]
assert payload["kind"] == "number", "forventet number-kort (ingen krasj), fikk %r" % (payload,)
assert payload["value"] == 7, "forventet verdi 7 (2+5 fra defaults), fikk %r" % (payload,)
assert win.capture_calls == ["start", "end"], "capture ikke kalt parvis: %r" % (win.capture_calls,)

print("MPY-DASH-RØYK OK")
