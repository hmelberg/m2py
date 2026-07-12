# Dash v2 fase 2 — pyodide- og webR-runtime: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dashboardet (dash v2) skal virke likt i brython-, pyodide- og R-modus: samme API-overflate, samme utseende, samme URL-state.

**Architecture:** `js/dash.js` (motoren) overtar norsk tallformat + delta og får strukturert tabell-payload og busy-API. Ny `pyodide/dash.py` (egen kopi, PyProxy-callbacks, hovedtråd). Ny `webr/dash.R` (deklarasjons-register) + `js/dash-webr.js` (bygger dashboardet etter kjøring, re-kjører kort async via evalR/captureR med siste-vinner-kø). Spec: `docs/superpowers/specs/2026-07-12-dash-v2-runtimes-design.md`.

**Tech Stack:** Vanilla JS (node:test for ren halvdel), Brython, Pyodide (hovedtråd), webR (async, Shelter/captureR), jsonlite, pytest (med js-stub) for pyodide-adapterens rene logikk.

## Global Constraints

- **Ingen bakoverkompat:** number-payload-kontrakten ERSTATTES (v3). Motor + brython-adapter oppdateres i samme branch; mellom Task 1 og Task 3 er brython-dashboards midlertidig ufullstendig formatert — det er OK på feature-branchen.
- **Adaptere bygger ALDRI kort/layout-DOM** — alt går via `window.Dash.*`. All data krysser grensen som JSON-strenger; kun callbacks og DOM-noder er rå.
- **Tusenskille er U+202F** (smalt hardt mellomrom), desimalskille `,`, minus U+2212 — én implementasjon, i JS.
- **Branch:** `dash-v2-runtimes` fra master. safestat leder; openstat synkes i siste task.
- **Cache-feller:** `pyodide/dash.py` og `webr/dash.R` hentes med `?v=M2PY_VERSION` — bump `window.M2PY_VERSION` (index.html:842) i Task 9. Service workeren cacher same-origin — avregistrer SW / hard reload ved iterering i browser.
- **LIB_REGISTRY-fella:** `dash`-oppføringen i `js/brython-engine.js:68` har vaktkommentar og js-deps som `{url, global}`-OBJEKTER. Ikke rør den — den er fortsatt korrekt (js-deps hoppes over når `window.Dash` finnes).
- **Testkommandoer:** `node --test tests/js/` og `python3 -m pytest tests/test_pyodide_dash.py -q`.
- Kjør `git checkout -b dash-v2-runtimes` før Task 1.

---

### Task 1: Motor — number-payload v3 (formatNumber + computeDelta i ren halvdel)

**Files:**
- Modify: `js/dash.js` (ren halvdel: nye funksjoner etter `D.autoOrder` ~linje 65; DOM-halvdel: `fmtNumber` ~linje 129, number-gren i `D.renderPayload` ~linje 206)
- Test: `tests/js/dash.test.js` (append)

**Interfaces:**
- Produces: `D.formatNumber(value, fmt) -> string` (norsk formatering; `fmt` er python-format-spec-delmengde `[,][.N][f|%]` eller null → default: rund til 2 desimaler, strip etternuller, grupper). `D.computeDelta(value, ref, fmt, bra) -> {text, dir, good} | null`. Number-payload-kontrakt v3: `{kind:"number", value, unit, fmt, ref, bra}` (adaptere sender rå verdier — Task 3/4/6 avhenger av denne).

- [ ] **Step 1: Skriv failende tester**

Append i `tests/js/dash.test.js`:

```js
test('formatNumber: default — heltall grupperes med U+202F', () => {
  assert.strictEqual(D.formatNumber(1234567), '1\u202f234\u202f567');
});

test('formatNumber: default — 2 desimaler uten etternuller, komma', () => {
  assert.strictEqual(D.formatNumber(3.14159), '3,14');
  assert.strictEqual(D.formatNumber(2.5), '2,5');
  assert.strictEqual(D.formatNumber(2.0), '2');
});

test('formatNumber: negativ bruker ekte minustegn', () => {
  assert.strictEqual(D.formatNumber(-1234.5), '\u22121\u202f234,5');
});

test('formatNumber: fmt ",.1f" — gruppert, 1 desimal', () => {
  assert.strictEqual(D.formatNumber(12345.678, ',.1f'), '12\u202f345,7');
});

test('formatNumber: fmt ".0f" — ingen gruppering', () => {
  assert.strictEqual(D.formatNumber(12345.678, '.0f'), '12346');
});

test('formatNumber: fmt ".1%" — prosent', () => {
  assert.strictEqual(D.formatNumber(0.1234, '.1%'), '12,3%');
});

test('formatNumber: ukjent fmt faller tilbake til default (kaster aldri)', () => {
  assert.strictEqual(D.formatNumber(1234.5, 'kroner'), '1\u202f234,5');
});

test('formatNumber: ikke-tall passeres som streng', () => {
  assert.strictEqual(D.formatNumber(NaN), 'NaN');
  assert.strictEqual(D.formatNumber(Infinity), 'Infinity');
});

test('computeDelta: retning, fortegn og god/dårlig', () => {
  const d = D.computeDelta(120, 100, null, 'opp');
  assert.deepStrictEqual(d, { text: '+20', dir: 'opp', good: true });
  const n = D.computeDelta(80, 100, null, 'opp');
  assert.deepStrictEqual(n, { text: '\u221220', dir: 'ned', good: false });
  const f = D.computeDelta(100, 100, null, 'ned');
  assert.deepStrictEqual(f, { text: '+0', dir: 'flat', good: true });
});

test('computeDelta: null/ikke-endelig ref gir null', () => {
  assert.strictEqual(D.computeDelta(5, null, null, 'opp'), null);
  assert.strictEqual(D.computeDelta(5, undefined, null, 'opp'), null);
  assert.strictEqual(D.computeDelta(5, Infinity, null, 'opp'), null);
});

test('computeDelta: bruker fmt på differansen', () => {
  const d = D.computeDelta(0.35, 0.30, '.1%', 'opp');
  assert.strictEqual(d.text, '+5,0%');
});
```

- [ ] **Step 2: Kjør — verifiser at de feiler**

Run: `node --test tests/js/dash.test.js`
Expected: FAIL — `D.formatNumber is not a function`

- [ ] **Step 3: Implementer i `js/dash.js`**

Rett etter `D.autoOrder` (i ren halvdel, før K2-blokken):

```js
  // Number-payload v3 (spec 2026-07-12 §3.1): adapterne sender rå
  // {value, unit, fmt, ref, bra}; motoren formaterer. Én implementasjon
  // av norsk tallformat — U+202F tusenskille, komma-desimal, U+2212-minus.
  var NNBSP = '\u202f';
  var MINUS = '\u2212';

  function groupInt(intStr) {
    return intStr.replace(/\B(?=(\d{3})+(?!\d))/g, NNBSP);
  }

  // fmt: python-format-spec-delmengden [,][.N][f|%]. Ukjent spec → default
  // (rund til 2 desimaler, strip etternuller, grupper). Kaster aldri.
  D.formatNumber = function (value, fmt) {
    if (typeof value !== 'number' || !isFinite(value)) return String(value);
    var m = (typeof fmt === 'string' && fmt) ? fmt.match(/^(,)?(?:\.(\d+))?(f|%)?$/) : null;
    var known = !!(m && (m[1] || m[2] != null || m[3]));
    var group = known ? !!m[1] : true;
    var pct = known && m[3] === '%';
    var v = pct ? value * 100 : value;
    var abs = Math.abs(v);
    var s;
    if (known) {
      var decimals = (m[2] != null) ? +m[2] : (m[3] ? 6 : null); // som pythons format()
      s = (decimals != null) ? abs.toFixed(decimals) : String(abs);
    } else {
      s = String(Math.abs(+v.toFixed(2)));
    }
    var parts = s.split('.');
    if (group) parts[0] = groupInt(parts[0]);
    s = parts[0] + (parts[1] ? ',' + parts[1] : '');
    return (v < 0 ? MINUS : '') + s + (pct ? '%' : '');
  };

  D.computeDelta = function (value, ref, fmt, bra) {
    if (typeof value !== 'number' || !isFinite(value)) return null;
    if (typeof ref !== 'number' || !isFinite(ref)) return null;
    var diff = value - ref;
    var dir = diff > 0 ? 'opp' : (diff < 0 ? 'ned' : 'flat');
    var good = dir === 'flat' || dir === (bra || 'opp');
    return { text: (diff >= 0 ? '+' : MINUS) + D.formatNumber(Math.abs(diff), fmt),
             dir: dir, good: good };
  };
```

Erstatt hele `fmtNumber` (DOM-halvdelen, ~linje 129) — widget-verdivisning skal bruke samme format (fjerner U+00A0-inkonsistensen fra `toLocaleString('nb-NO')`):

```js
  function fmtNumber(v) {
    return D.formatNumber(v);
  }
```

Erstatt number-grenen i `D.renderPayload` (fjern all `p.text`/`p.delta`-lesing — v2-felter finnes ikke lenger):

```js
    if (kind === 'number') {
      var k = el('div', 'dash-kpi');
      k.appendChild(el('span', 'dash-kpi-value', D.formatNumber(p.value, p.fmt)));
      if (p.unit) k.appendChild(el('span', 'dash-kpi-unit', p.unit));
      var delta = D.computeDelta(p.value, p.ref, p.fmt, p.bra);
      if (delta) {
        var arrow = delta.dir === 'opp' ? '▲' : (delta.dir === 'ned' ? '▼' : '–');
        var dcls = 'dash-kpi-delta ' + (delta.good ? 'dash-kpi-delta--good' : 'dash-kpi-delta--bad');
        k.appendChild(el('span', dcls, arrow + ' ' + delta.text));
      }
      return k;
    }
```


- [ ] **Step 4: Kjør testene**

Run: `node --test tests/js/dash.test.js`
Expected: PASS (alle, inkl. de 98 eksisterende — sjekk spesielt at ingen gamle number-tester refererer `p.text`/`p.delta`; hvis noen gjør det, oppdater dem til v3-kontrakten i samme commit)

- [ ] **Step 5: Commit**

```bash
git add js/dash.js tests/js/dash.test.js
git commit -m "feat(dash): number-payload v3 — norsk tallformat + delta i motoren"
```

---

### Task 2: Motor — strukturert tabell, payloadCols, setBusy, isAlive

**Files:**
- Modify: `js/dash.js` (ren halvdel: `D.payloadCols`; DOM-halvdel: table-gren i `renderPayload`, `D.addCard`/`D.updateCard` cols-avledning, nye `D.setBusy`/`D.isAlive`)
- Test: `tests/js/dash.test.js` (append)

**Interfaces:**
- Consumes: —
- Produces: tabell-payload kan nå også være `{kind:"table", columns:[str], rows:[[celle,...],...]}` (html-varianten består). `D.payloadCols(p) -> number`. `D.setBusy(cardId)` (slår på shimmer til neste updateCard). `D.isAlive(dashId) -> boolean` (DOM-roten er fortsatt tilkoblet — brukes av pyodide-adapterens proxy-rydding i Task 4).

- [ ] **Step 1: Skriv failende tester**

```js
test('payloadCols: html-tabell bruker cols, strukturert bruker columns.length', () => {
  assert.strictEqual(D.payloadCols({ kind: 'table', html: '<table/>', cols: 9 }), 9);
  assert.strictEqual(D.payloadCols({ kind: 'table', columns: ['a', 'b'], rows: [] }), 2);
  assert.strictEqual(D.payloadCols({ kind: 'number', value: 1 }), 0);
});
```

- [ ] **Step 2: Kjør — verifiser FAIL**

Run: `node --test tests/js/dash.test.js`
Expected: FAIL — `D.payloadCols is not a function`

- [ ] **Step 3: Implementer**

Ren halvdel (etter `D.computeDelta`):

```js
  D.payloadCols = function (p) {
    if (!p) return 0;
    if (typeof p.cols === 'number') return p.cols;
    if (p.columns && p.columns.length) return p.columns.length;
    return 0;
  };
```

Table-grenen i `renderPayload` erstattes med:

```js
    if (kind === 'table') {
      var w = el('div', 'dash-table-wrap');
      if (p.html != null) {
        w.innerHTML = p.html;
        return w;
      }
      // strukturert variant (spec 2026-07-12 §3.2) — bygget med textContent,
      // aldri innerHTML: celleinnhold kan ikke smugle markup.
      var tbl = el('table');
      var trh = el('tr');
      (p.columns || []).forEach(function (c) { trh.appendChild(el('th', null, String(c))); });
      var thead = el('thead');
      thead.appendChild(trh);
      tbl.appendChild(thead);
      var tbody = el('tbody');
      (p.rows || []).forEach(function (row) {
        var tr = el('tr');
        (row || []).forEach(function (cell) {
          tr.appendChild(el('td', null, cell == null ? '' : String(cell)));
        });
        tbody.appendChild(tr);
      });
      tbl.appendChild(tbody);
      w.appendChild(tbl);
      return w;
    }
```

(CSS trengs ikke: `css/dash.css:79-85` styler `.dash-table-wrap table/th/td` generisk.)

I `D.addCard` og `D.updateCard`: erstatt begge `p.cols || 0`-forekomstene (linjene med `placeCard(...)` og span-oppdateringen) med `D.payloadCols(p)`.

Nye API-er nederst i DOM-halvdelen (før `module.exports`):

```js
  // Async-runtimes (dash-webr): slå på loading-shimmer til neste updateCard.
  D.setBusy = function (cardId) {
    var rec = _cards[cardId];
    if (rec) rec.node.classList.add('dash-card--loading');
  };

  // Lever dashboardet fortsatt i DOM? (pyodide-adapteren rydder proxies
  // for døde dashboards ved neste dashboard()-kall.)
  D.isAlive = function (id) {
    var d = _dashes[id];
    return !!(d && d.root && d.root.isConnected);
  };
```

- [ ] **Step 4: Kjør testene**

Run: `node --test tests/js/dash.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add js/dash.js tests/js/dash.test.js
git commit -m "feat(dash): strukturert tabell-payload + setBusy/isAlive"
```

---

### Task 3: brython/dash.py — rå number-payload (slanking)

**Files:**
- Modify: `brython/dash.py` (slett `_NNBSP`, `_MINUS`, `_fmt_norsk`, `_fmt_default_norsk`, `_delta`; erstatt `_number_payload`)

**Interfaces:**
- Consumes: number-payload v3 fra Task 1.
- Produces: `_number_payload(value, unit, fmt, ref, bra) -> {"kind","value","unit","fmt","ref","bra"}` — samme form som pyodide- (Task 4) og R-adapteren (Task 6) skal sende.

- [ ] **Step 1: Erstatt formatering med rå payload**

Slett linjene med `_NNBSP = ...`, `_MINUS = ...` og hele funksjonene `_fmt_norsk`, `_fmt_default_norsk`, `_delta` (brython/dash.py:151-188). Erstatt `_number_payload` (linje 191-198) med:

```python
def _number_payload(value, unit, fmt, ref, bra):
    """Number-payload v3: raa verdier — js/dash.js formaterer (norsk
    gruppering, delta). ref saniteres her: json.dumps av nan/inf gir
    literal NaN/Infinity som knekker JSON.parse i JS."""
    if ref is not None and (ref != ref or abs(ref) == float("inf")):
        ref = None
    return {"kind": "number", "value": value, "unit": unit or "",
            "fmt": fmt, "ref": ref, "bra": bra}
```

(Kallstedene i `add()`/`_run()` er uendret — signaturen består. Merk: brython-Series har fått `to_html` i dash v2-forbedringer S1, så Series treffer allerede tabell-grenen — ingen Series-endring her; spec §7 sitt Series-punkt er alt dekket. Noter avviket i ledgeren.)

- [ ] **Step 2: Syntaks-sjekk**

Run: `python3 -c "import ast; ast.parse(open('brython/dash.py').read())" && echo OK`
Expected: `OK`

- [ ] **Step 3: Kjør node-testene (regresjon)**

Run: `node --test tests/js/`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add brython/dash.py
git commit -m "refactor(dash): brython-adapter sender rå number-payload (v3)"
```

---

### Task 4: pyodide/dash.py — pyodide-adapteret

**Files:**
- Create: `pyodide/dash.py`
- Test: `tests/test_pyodide_dash.py`

**Interfaces:**
- Consumes: `window.Dash.create/addCard/updateCard/addControls/initialValues/isAlive` (Task 1-2), number-payload v3.
- Produces: modulen `dash` i pyodide (registreres av Task 5): `dashboard(title, layout)`, `Dash.add(x, title=, at=, unit=, fmt=, ref=, bra=, **kwargs)`, `Dash.controls(**kwargs)`, widget-fabrikkene `slider/dropdown/checkbox/textfield/numberfield/play` (samme signaturer som brython/dash.py:46-79).

- [ ] **Step 1: Skriv failende tester**

Create `tests/test_pyodide_dash.py`:

```python
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
```

- [ ] **Step 2: Kjør — verifiser FAIL**

Run: `python3 -m pytest tests/test_pyodide_dash.py -q`
Expected: FAIL/ERROR — `pyodide/dash.py` finnes ikke

- [ ] **Step 3: Skriv `pyodide/dash.py`**

Fila er en tilpasset kopi av `brython/dash.py` (bevisst duplikat — spec §2 pkt 1). Fullstendig innhold:

```python
"""dash v2 - pyodide-adapter (spec 2026-07-12-dash-v2-runtimes-design.md §4).
Egen kopi av brython/dash.py-moensteret - IKKE delt fil (besluttet i brainstorm).
Bygger ALDRI kort/layout-DOM selv; alt gaar via window.Dash (js/dash.js).
Data krysser grensen som JSON-strenger; callbacks krysser som PyProxy
(pyodide kjoerer paa hovedtraaden - direkte kall, ingen koe)."""
import io
import json
import sys

from js import window

try:
    from pyodide.ffi import create_proxy
except ImportError:          # CPython (pytest med js-stub): ingen proxy noedvendig
    def create_proxy(f):
        return f


# ---- proxy-livssyklus: destruer callbacks for dashboards hvis DOM er borte ----

_live = []   # [(dash_id, [proxies])]


def _reap():
    keep = []
    for dash_id, proxies in _live:
        alive = False
        try:
            alive = bool(window.Dash.isAlive(dash_id))
        except Exception:
            pass
        if alive:
            keep.append((dash_id, proxies))
        else:
            for p in proxies:
                try:
                    p.destroy()
                except Exception:
                    pass
    _live[:] = keep


def dashboard(title="", layout=None):
    return Dash(title, layout)


class Widget:
    def __init__(self, kind, values=None, **spec):
        self.kind = kind
        self.spec = {k: v for k, v in spec.items() if v is not None}
        self.values = values  # dropdown: original-objektene (indeks -> verdi)

    def to_spec(self, name):
        d = dict(self.spec)
        d["type"] = self.kind
        d["name"] = name
        return d

    def default(self):
        if self.kind == "dropdown":
            return self.values[self.spec.get("index", 0)]
        if self.kind in ("slider", "play"):
            return self.spec.get("default", self.spec["min"])
        return self.spec.get("default")

    def from_raw(self, raw):
        """JS-raaverdi -> Python-verdi."""
        if self.kind == "dropdown":
            return self.values[int(raw)]
        if self.kind in ("slider", "numberfield", "play"):
            v = float(raw)
            bounds = [self.spec.get(k) for k in ("min", "max", "step", "default")]
            ints = all(isinstance(b, int) for b in bounds if b is not None)
            return int(v) if ints and v == int(v) else v
        if self.kind == "checkbox":
            return bool(raw)
        return raw


def slider(min, max, step=None, default=None, label=None):
    return Widget("slider", min=min, max=max, step=step,
                  default=default if default is not None else min, label=label)


def play(min, max, step=None, default=None, interval=600, loop=False, label=None):
    return Widget("play", min=min, max=max, step=step,
                  default=default if default is not None else min,
                  interval=interval, loop=loop, label=label)


def dropdown(*options, default=None, label=None):
    if len(options) == 1 and isinstance(options[0], (list, tuple)):
        opts = list(options[0])
    else:
        opts = list(options)
    idx = opts.index(default) if default in opts else 0
    return Widget("dropdown", values=opts,
                  options=[str(o) for o in opts], index=idx, label=label)


def checkbox(default=False, label=None):
    return Widget("checkbox", default=bool(default), label=label)


def textfield(default="", label=None):
    return Widget("textfield", default=str(default), label=label)


def numberfield(default=0, min=None, max=None, step=None, label=None):
    return Widget("numberfield", default=default, min=min, max=max,
                  step=step, label=label)


def _scalar(value):
    """numpy-skalar -> python int/float/bool (json.dumps taaler ikke numpy)."""
    if type(value).__module__ == "numpy" and hasattr(value, "item") \
            and not hasattr(value, "__len__"):
        try:
            return value.item()
        except Exception:
            return value
    return value


def _infer(name, value):
    """Implisitt kwarg->widget-mapping (spec v1 4.2). Rekkefolgen betyr noe:
    bool foer int (bool er subklasse av int)."""
    value = _scalar(value)
    if isinstance(value, Widget):
        return value
    if isinstance(value, bool):
        return checkbox(default=value)
    if isinstance(value, tuple) and len(value) in (2, 3) \
            and all(isinstance(v, (int, float)) for v in value):
        return slider(*value)
    if isinstance(value, (list, set)) or hasattr(value, "tolist"):
        seq = value.tolist() if hasattr(value, "tolist") else list(value)
        return dropdown(*seq)
    if isinstance(value, str):
        return textfield(default=value)
    if isinstance(value, (int, float)):
        return numberfield(default=value)
    if isinstance(value, tuple):
        raise ValueError(
            "dash: %s=%r er en tuppel, men ikke (min,max[,steg]) med tall. "
            "Bruk list(...) rundt verdien for aa lage en nedtrekksmeny." % (name, value))
    if isinstance(value, dict):
        raise ValueError(
            "dash: %s=%r er en dict - ikke stottet direkte som kontroll. "
            "Bruk list(...) rundt noklene eller verdiene for aa lage en nedtrekksmeny."
            % (name, value))
    raise ValueError(
        "dash: kan ikke lage kontroll av %s=%r (type %s). "
        "Bruk list(...) rundt verdien for en nedtrekksmeny, eller oppgi en "
        "widget eksplisitt (dash.slider/dropdown/checkbox/textfield/"
        "numberfield/play)." % (name, value, type(value).__name__))


def _figure_spec(x):
    """Ekte plotly: Figure har to_json() (NaN-trygg JSON-streng).
    data+layout-guarden hindrer at pandas-objekter (som ogsaa har to_json,
    men ikke .layout) treffer grenen."""
    if hasattr(x, "to_json") and hasattr(x, "data") and hasattr(x, "layout"):
        try:
            d = json.loads(x.to_json())
            if isinstance(d, dict) and "data" in d:
                return d
        except Exception:
            pass
    if isinstance(x, dict) and "data" in x and "layout" in x:
        return x
    return None


def _mpl_image(x):
    """Ekte matplotlib Figure/Axes (inkl. df.plot()-retur) -> PNG data-URI.
    Forsokes kun naar scriptet alt har importert matplotlib."""
    if "matplotlib" not in sys.modules:
        return None
    fig = x if hasattr(x, "savefig") else getattr(x, "figure", None)
    if fig is None or not hasattr(fig, "savefig"):
        return None
    import base64
    import matplotlib.pyplot as plt
    fig.set_size_inches(7.2, 4.4)   # fyller innholdsflaten uten letterboxing (v1 §7)
    fig.set_dpi(100)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


_IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")


def _number_payload(value, unit, fmt, ref, bra):
    """Number-payload v3: raa verdier - js/dash.js formaterer. ref saniteres:
    json.dumps av nan/inf gir literal NaN/Infinity som knekker JSON.parse."""
    ref = _scalar(ref)
    if ref is not None and (ref != ref or abs(ref) == float("inf")):
        ref = None
    return {"kind": "number", "value": value, "unit": unit or "",
            "fmt": fmt, "ref": ref, "bra": bra}


def _payload(x, unit=None, fmt=None, ref=None, bra="opp"):
    """add(x)-dispatch (spec v1 §5). Rekkefolgen er prioritetsrekkefolgen."""
    x = _scalar(x)
    if x is None:
        return {"kind": "text", "text": ""}
    if isinstance(x, bool):
        return {"kind": "text", "text": str(x)}
    if isinstance(x, (int, float)):
        if x != x or abs(x) == float("inf"):
            return {"kind": "text", "text": str(x)}
        return _number_payload(x, unit, fmt, ref, bra)
    if isinstance(x, str):
        s = x.strip()
        if s.startswith("data:image") or (
                s.split("?")[0].lower().endswith(_IMG_EXT)
                and (s.startswith("http") or "/" in s) and "\n" not in s):
            return {"kind": "image", "src": s}
        return {"kind": "markdown", "text": x}
    fig = _figure_spec(x)
    if fig is not None:
        return {"kind": "figure", "spec": fig}
    src = _mpl_image(x)
    if src:
        return {"kind": "image", "src": src}
    if hasattr(x, "to_html"):
        try:
            ncols = len(list(getattr(x, "columns", []) or []))
        except Exception:
            ncols = 0
        return {"kind": "table", "html": x.to_html(), "cols": ncols}
    if hasattr(x, "to_frame"):      # pandas Series (har ikke egen to_html)
        try:
            return {"kind": "table", "html": x.to_frame().to_html(), "cols": 1}
        except Exception:
            pass
    if hasattr(x, "nodeType"):      # DOM-element via JsProxy (escape-luke)
        return {"kind": "node"}
    return {"kind": "text", "text": repr(x)}


def _dom_node(x):
    return x


def _func_params(f):
    code = f.__code__
    return list(code.co_varnames[:code.co_argcount + code.co_kwonlyargcount])


def _initial_raw(id_):
    """Lagrede raa-startverdier (K2/URL-state) via window.Dash.initialValues."""
    try:
        raw_json = window.Dash.initialValues(id_)
    except Exception:
        return {}
    if not raw_json:
        return {}
    try:
        raw = json.loads(raw_json)
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _map_raw(raw, widgets):
    out = {}
    for n, r in raw.items():
        if n in widgets:
            try:
                out[n] = widgets[n].from_raw(r)
            except Exception:
                pass
    return out


class Dash:
    def __init__(self, title="", layout=None):
        self._cards = {}       # card_id -> dict(func, widgets, unit, ...)
        self._shared = {}      # navn -> Widget
        self._shared_vals = {} # navn -> Python-verdi
        self._proxies = []
        self.id = window.Dash.create(json.dumps({"title": title, "layout": layout}))
        _reap()
        _live.append((self.id, self._proxies))

    def _proxy(self, f):
        p = create_proxy(f)
        self._proxies.append(p)
        return p

    # ---- offentlig API ----

    def add(self, x, title=None, at=None, unit=None, fmt=None, ref=None,
            bra="opp", **kwargs):
        if callable(x) and not isinstance(x, Widget):
            self._add_func(x, title, at, unit, kwargs, fmt=fmt, ref=ref, bra=bra)
            return
        p = _payload(x, unit=unit, fmt=fmt, ref=ref, bra=bra)
        opts = {"title": title, "area": at, "content": p}
        node = _dom_node(x) if p["kind"] == "node" else None
        window.Dash.addCard(self.id, json.dumps(opts), None, node)

    def controls(self, **kwargs):
        # re-registrerer HELE settet hver gang; addControls erstatter
        # toppstripa i JS, saa gamle closures fyres aldri igjen.
        for name, value in kwargs.items():
            w = _infer(name, value)
            self._shared[name] = w
            self._shared_vals[name] = w.default()
        specs = [w.to_spec(n) for n, w in self._shared.items()]

        def on_change(values_json):
            raw = json.loads(values_json)
            for n, r in raw.items():
                if n in self._shared:
                    self._shared_vals[n] = self._shared[n].from_raw(r)
            for cid, card in self._cards.items():
                if set(card["params"]) & set(self._shared):
                    self._run(cid)

        window.Dash.addControls(self.id, json.dumps(specs), self._proxy(on_change))
        self._shared_vals.update(_map_raw(_initial_raw(self.id), self._shared))
        for cid, card in self._cards.items():
            if set(card["params"]) & set(self._shared):
                self._run(cid)

    # ---- internt ----

    def _add_func(self, func, title, at, unit, kwargs, fmt=None, ref=None, bra="opp"):
        widgets = {n: _infer(n, v) for n, v in kwargs.items()}
        specs = [w.to_spec(n) for n, w in widgets.items()]
        card = {
            "func": func,
            "widgets": widgets,
            "unit": unit,
            "fmt": fmt,
            "ref": ref,
            "bra": bra,
            "params": _func_params(func),
            "vals": {n: w.default() for n, w in widgets.items()},
        }
        holder = {}

        def on_change(values_json):
            raw = json.loads(values_json)
            for n, r in raw.items():
                if n in widgets:
                    card["vals"][n] = widgets[n].from_raw(r)
            self._run(holder["cid"])

        opts = {"title": title, "area": at, "controls": specs, "content": None}
        cid = window.Dash.addCard(self.id, json.dumps(opts),
                                  self._proxy(on_change) if specs else None, None)
        holder["cid"] = cid
        self._cards[cid] = card
        if specs:
            card["vals"].update(_map_raw(_initial_raw(cid), widgets))
        self._run(cid)
        return cid

    def _run(self, cid):
        card = self._cards[cid]
        vals = dict(card["vals"])
        for n in card["params"]:
            if n not in vals and n in self._shared_vals:
                vals[n] = self._shared_vals[n]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        node = None
        try:
            res = card["func"](**vals)
            if res is None and buf.getvalue().strip():
                p = {"kind": "text", "text": buf.getvalue().rstrip()}
            else:
                p = _payload(res, unit=card["unit"], fmt=card.get("fmt"),
                             ref=card.get("ref"), bra=card.get("bra", "opp"))
                if p["kind"] == "node":
                    node = _dom_node(res)
        except Exception as e:
            p = {"kind": "error", "message": "%s: %s" % (type(e).__name__, e)}
        finally:
            sys.stdout = old
        window.Dash.updateCard(cid, json.dumps(p), node)
```

- [ ] **Step 4: Kjør testene**

Run: `python3 -m pytest tests/test_pyodide_dash.py -q`
Expected: PASS (8 tester)

- [ ] **Step 5: Commit**

```bash
git add pyodide/dash.py tests/test_pyodide_dash.py
git commit -m "feat(dash): pyodide-adapter — PyProxy-callbacks, ekte plotly/matplotlib/pandas"
```

---

### Task 5: index.html — python-modus-integrasjon

**Files:**
- Modify: `index.html` (script-tag ~linje 805; stale kommentar ~linje 821-823; python-modusens `preRun` linje 3649; ny `__ensurePyDash` ved `__ensureDuckBridge` ~linje 8709)

**Interfaces:**
- Consumes: `pyodide/dash.py` (Task 4).
- Produces: `import dash` virker i python-modus; `window.Dash` finnes alltid (eager script).

- [ ] **Step 1: Last js/dash.js eagert**

Etter `<script src="js/brython-engine.js"></script>` (linje 805):

```html
  <script src="js/dash.js"></script>
```

Oppdater den stale kommentaren i ds-strippe-blokken (linje 821-823): erstatt «dash.js (lastes lazy via LIB_REGISTRY først når et dashboard-script faktisk kjører) leser…» med «dash.js (lastes eagert siden fase 2 — pyodide/R trenger den utenom LIB_REGISTRY) leser…». IKKE rør `dash`-oppføringen i `js/brython-engine.js` — den er nå en no-op (window.Dash finnes) men er riktig og vaktet.

- [ ] **Step 2: Legg til `__ensurePyDash`**

Rett over `async function runStatxScript` (etter `__ensureDuckBridge`-blokken, ~linje 8728):

```js
    // ── python-modus: registrer pyodide/dash.py som modulen `dash` (lazy) ──
    // Samme mønster som __ensureDuckBridge. MÅ kjøres FØR micropip-løkka i
    // python-modusens preRun — ellers feiler find_spec('dash') og micropip
    // installerer PyPI-pakken `dash` (plotly sin — feil og diger).
    var __pyDashP = null;
    function __ensurePyDash(py) {
      if (__pyDashP) return __pyDashP;
      var base = window.location.href.replace(/[^/]+$/, '');
      __pyDashP = fetch(base + 'pyodide/dash.py?v=' + (window.M2PY_VERSION || '1'))
        .then(function (r) { if (!r.ok) throw new Error('pyodide/dash.py: ' + r.status); return r.text(); })
        .then(function (code) {
          return py.runPythonAsync(
            'import sys, importlib.util\n' +
            'def _reg_dash(src):\n' +
            '    spec = importlib.util.spec_from_loader("dash", loader=None)\n' +
            '    mod = importlib.util.module_from_spec(spec)\n' +
            '    sys.modules["dash"] = mod\n' +
            '    exec(compile(src, "dash.py", "exec"), mod.__dict__)\n' +
            '_reg_dash(' + JSON.stringify(code) + ')');
        })
        .catch(function (e) { __pyDashP = null; throw e; });
      return __pyDashP;
    }
```

- [ ] **Step 3: Hook i python-modusens preRun**

Øverst i `python.preRun` (linje 3649, FØR `loadPackagesFromImports`-blokken):

```js
        preRun: async function (script, ctx) {
          // dash-import registreres FØR pakke-sjekkene under — se __ensurePyDash.
          if (/^\s*(?:import|from)\s+dash\b/m.test(script)) {
            try { await __ensurePyDash(ctx.py); }
            catch (e) { console.warn('pyodide/dash.py:', e); }
          }
          try {
```

(Resten av preRun uendret. DOM-livssyklusen trenger INGEN endring: python-kjøringen tømmer `#outputArea` FØR segmentløkka (linje 10311-10312) og bruker `appendOutput` etterpå — dashboard-DOM bygget under segmentene overlever. Feilstien er vaktet av `incrementalStarted`.)

- [ ] **Step 4: Sanity-sjekk**

Run: `node --check js/dash.js && node --test tests/js/ && python3 -m pytest tests/test_pyodide_dash.py -q`
Expected: PASS. (index.html-endringene browser-verifiseres samlet i Task 9.)

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat(dash): python-modus — eager js/dash.js + lazy import dash via pyodide-FS-registrering"
```

---

### Task 6: webr/dash.R — R-adapteret

**Files:**
- Create: `webr/dash.R`

**Interfaces:**
- Consumes: number-payload v3 (Task 1), strukturert tabell (Task 2).
- Produces (kalles av Task 7 via evalR): `dashboard(title, layout)` (returnerer miljø med `$add`, `$controls`), widget-hjelperne, `.dash_reset()`, `.dash_registry_json() -> chr` (JSON: `{dashes:[{title, layout, cards:[{title, at, func?, params?, controls?, payload?}], shared:[spec]}]}`), `.dash_run(di, ci, values_json) -> chr` (payload-JSON; tegner evt. plott som captureR fanger).

- [ ] **Step 1: Skriv `webr/dash.R`**

```r
# dash v2 - webR-adapter (spec 2026-07-12-dash-v2-runtimes-design.md §5).
# Bygger ALDRI DOM: dashboard()/add()/controls() samler deklarasjoner i
# .dash-miljoet. js/dash-webr.js henter .dash_registry_json() etter
# kjoringen, bygger kort via window.Dash, og re-kjorer funksjonskort med
# .dash_run() (async, captureR). All data krysser grensen som JSON.

.dash <- new.env(parent = emptyenv())

.dash_reset <- function() {
  .dash$dashes <- list()
  invisible(NULL)
}
.dash_reset()

# ---- widgets (samme spec-vokabular som python-adapterne) ----

.dash_widget <- function(kind, spec, values = NULL) {
  spec <- spec[!vapply(spec, is.null, logical(1))]
  list(kind = kind, spec = spec, values = values)
}

slider <- function(min, max, step = NULL, default = NULL, label = NULL) {
  .dash_widget("slider", list(min = min, max = max, step = step,
                              default = if (is.null(default)) min else default,
                              label = label))
}

play <- function(min, max, step = NULL, default = NULL, interval = 600,
                 loop = FALSE, label = NULL) {
  .dash_widget("play", list(min = min, max = max, step = step,
                            default = if (is.null(default)) min else default,
                            interval = interval, loop = isTRUE(loop),
                            label = label))
}

dropdown <- function(..., default = NULL, label = NULL) {
  opts <- c(...)
  idx <- if (!is.null(default) && default %in% opts) which(opts == default)[1] - 1 else 0
  # I() paa options: jsonlite auto_unbox maa ikke kollapse en
  # en-elements meny til skalar - JS-siden venter alltid array.
  .dash_widget("dropdown",
               list(options = I(as.character(opts)), index = idx, label = label),
               values = opts)
}

checkbox <- function(default = FALSE, label = NULL) {
  .dash_widget("checkbox", list(default = isTRUE(default), label = label))
}

textfield <- function(default = "", label = NULL) {
  .dash_widget("textfield", list(default = as.character(default), label = label))
}

numberfield <- function(default = 0, min = NULL, max = NULL, step = NULL,
                        label = NULL) {
  .dash_widget("numberfield", list(default = default, min = min, max = max,
                                   step = step, label = label))
}

.dash_is_widget <- function(v) {
  is.list(v) && !is.null(v$kind) && !is.null(v$spec)
}

# Implisitt kwarg->widget, typebasert (spec §5.2):
#   numerisk lengde 2-3 -> slider | character/factor >1 -> dropdown |
#   numerisk >3 -> dropdown | logical(1) -> checkbox |
#   tall(1) -> numberfield | streng(1) -> textfield
# Kant (dokumentert): numerisk meny med 2-3 valg krever eksplisitt dropdown().
.dash_infer <- function(name, value) {
  if (.dash_is_widget(value)) return(value)
  if (is.logical(value) && length(value) == 1) return(checkbox(default = value))
  if (is.numeric(value) && length(value) %in% c(2, 3))
    return(do.call(slider, unname(as.list(value))))
  if ((is.character(value) || is.factor(value)) && length(value) > 1)
    return(dropdown(as.character(value)))
  if (is.numeric(value) && length(value) > 3) return(dropdown(value))
  if (is.numeric(value) && length(value) == 1) return(numberfield(default = value))
  if (is.character(value) && length(value) == 1) return(textfield(default = value))
  stop(sprintf(paste0(
    "dash: kan ikke lage kontroll av %s (type %s, lengde %d). Bruk ",
    "slider()/dropdown()/checkbox()/textfield()/numberfield()/play()."),
    name, class(value)[1], length(value)))
}

.dash_default <- function(w) {
  if (w$kind == "dropdown") return(w$values[[w$spec$index + 1]])
  w$spec$default
}

.dash_from_raw <- function(w, raw) {
  if (w$kind == "dropdown") return(w$values[[as.integer(raw) + 1]])
  if (w$kind %in% c("slider", "numberfield", "play")) return(as.numeric(raw))
  if (w$kind == "checkbox") return(isTRUE(raw))
  as.character(raw)
}

.dash_widget_spec <- function(name, w) {
  c(w$spec, list(type = w$kind, name = name))
}

# ---- payload (spec v1 §5 - rekkefolgen er prioritetsrekkefolgen) ----

.dash_payload <- function(x, unit = NULL, fmt = NULL, ref = NULL, bra = "opp") {
  if (is.null(x)) return(list(kind = "text", text = ""))
  if (inherits(x, "data.frame")) {
    # rows som data.frame: toJSON(dataframe="values") gir array-av-arrays
    return(list(kind = "table", columns = I(as.character(names(x))), rows = x))
  }
  if (is.numeric(x) && length(x) == 1) {
    if (!is.finite(x)) return(list(kind = "text", text = format(x)))
    if (!is.null(ref) && (!is.numeric(ref) || !is.finite(ref))) ref <- NULL
    return(list(kind = "number", value = x,
                unit = if (is.null(unit)) "" else unit,
                fmt = fmt, ref = ref, bra = bra))
  }
  if (is.logical(x) && length(x) == 1) return(list(kind = "text", text = format(x)))
  if (is.character(x) && length(x) == 1) {
    s <- trimws(x)
    if (startsWith(s, "data:image") ||
        grepl("\\.(png|jpe?g|gif|svg|webp)(\\?.*)?$", tolower(s)))
      return(list(kind = "image", src = s))
    return(list(kind = "markdown", text = x))
  }
  list(kind = "text", text = paste(capture.output(print(x)), collapse = "\n"))
}

.dash_payload_json <- function(p) {
  as.character(jsonlite::toJSON(p, dataframe = "values", auto_unbox = TRUE,
                                na = "null", null = "null", digits = NA))
}

# ---- offentlig API ----

dashboard <- function(title = "", layout = NULL) {
  di <- length(.dash$dashes) + 1
  d <- new.env(parent = emptyenv())
  d$title <- title
  d$layout <- layout
  d$cards <- list()
  d$shared <- list()
  .dash$dashes[[di]] <- d

  d$add <- function(x, title = NULL, at = NULL, unit = NULL, fmt = NULL,
                    ref = NULL, bra = "opp", ...) {
    kw <- list(...)
    ci <- length(d$cards) + 1
    if (is.function(x)) {
      widgets <- list()
      for (n in names(kw)) widgets[[n]] <- .dash_infer(n, kw[[n]])
      d$cards[[ci]] <- list(func = x, widgets = widgets,
                            params = names(formals(x)),
                            title = title, at = at, unit = unit, fmt = fmt,
                            ref = ref, bra = bra)
    } else if (inherits(x, "ggplot")) {
      # statiske plott realiseres via samme captureR-sti som funksjonskort
      d$cards[[ci]] <- list(func = local({ .x <- x; function() .x }),
                            widgets = list(), params = character(0),
                            title = title, at = at, unit = NULL, fmt = NULL,
                            ref = NULL, bra = "opp")
    } else {
      d$cards[[ci]] <- list(payload = .dash_payload(x, unit = unit, fmt = fmt,
                                                    ref = ref, bra = bra),
                            title = title, at = at)
    }
    invisible(NULL)
  }

  d$controls <- function(...) {
    kw <- list(...)
    for (n in names(kw)) d$shared[[n]] <- .dash_infer(n, kw[[n]])
    invisible(NULL)
  }

  d
}

# ---- grensesnittet js/dash-webr.js bruker ----

.dash_registry_json <- function() {
  dashes <- lapply(.dash$dashes, function(d) {
    cards <- lapply(d$cards, function(card) {
      out <- list(title = card$title, at = card$at)
      if (!is.null(card$func)) {
        out$func <- TRUE
        out$params <- I(as.character(card$params))
        specs <- list()
        for (n in names(card$widgets))
          specs[[length(specs) + 1]] <- .dash_widget_spec(n, card$widgets[[n]])
        out$controls <- specs
      } else {
        out$payload <- card$payload
      }
      out
    })
    shared <- list()
    for (n in names(d$shared))
      shared[[length(shared) + 1]] <- .dash_widget_spec(n, d$shared[[n]])
    list(title = d$title, layout = d$layout, cards = cards, shared = shared)
  })
  as.character(jsonlite::toJSON(list(dashes = dashes), dataframe = "values",
                                auto_unbox = TRUE, na = "null", null = "null",
                                digits = NA))
}

.dash_run <- function(di, ci, values_json) {
  d <- .dash$dashes[[di]]
  card <- d$cards[[ci]]
  raw <- jsonlite::fromJSON(values_json, simplifyVector = FALSE)
  vals <- list()
  for (n in card$params) {
    w <- card$widgets[[n]]
    if (is.null(w)) w <- d$shared[[n]]
    if (is.null(w)) next
    vals[[n]] <- if (!is.null(raw[[n]])) .dash_from_raw(w, raw[[n]])
                 else .dash_default(w)
  }
  res <- tryCatch(do.call(card$func, vals), error = function(e) e)
  if (inherits(res, "error"))
    return(.dash_payload_json(list(kind = "error",
                                   message = conditionMessage(res))))
  if (inherits(res, "ggplot")) {
    print(res)   # tegner -> JS-gluen bruker captureR-bildet
    return(.dash_payload_json(list(kind = "text", text = "")))
  }
  .dash_payload_json(.dash_payload(res, unit = card$unit, fmt = card$fmt,
                                   ref = card$ref, bra = card$bra))
}
```

- [ ] **Step 2: Parse-sjekk (hvis Rscript finnes lokalt)**

Run: `command -v Rscript >/dev/null && Rscript -e 'invisible(parse("webr/dash.R")); cat("OK\n")' || echo "Rscript mangler — parses i browser-røyk (Task 9)"`
Expected: `OK` (eller fallback-meldingen)

- [ ] **Step 3: Commit**

```bash
git add webr/dash.R
git commit -m "feat(dash): webR-adapter — deklarasjons-register + dash_run"
```

---

### Task 7: js/dash-webr.js — JS-glue + runHybridR-hooks

**Files:**
- Create: `js/dash-webr.js`
- Modify: `index.html` (script-tag etter js/dash.js; to hooks i `runHybridR` — før Phase 2-løkka ~linje 8637 og etter `renderROutputParts` ~linje 8699)
- Test: `tests/js/dash-webr.test.js`

**Interfaces:**
- Consumes: `window.Dash.*` (inkl. `setBusy`, `payloadCols` via updateCard), `window.M2PY.getWebR/loadWebR`, `webr/dash.R`-grensesnittet (Task 6), `window.M2PY_VERSION`.
- Produces: `window.DashWebR = { makeQueue, ensureDefs(), reset(), mount() }`. `makeQueue()` er ren (node-testet): `{schedule(key, args, run), idle()}` — sekvensiell kjede med per-nøkkel siste-vinner-koalescing.

- [ ] **Step 1: Skriv failende test for køen**

Create `tests/js/dash-webr.test.js`:

```js
const test = require('node:test');
const assert = require('node:assert');
const G = require('../../js/dash-webr.js');

test('makeQueue: sekvensiell, per-nøkkel siste-vinner-koalescing', async () => {
  const q = G.makeQueue();
  const ran = [];
  const run = (tag) => (args) => new Promise((res) =>
    setTimeout(() => { ran.push([tag, args]); res(); }, 5));
  q.schedule('a', 1, run('a'));
  q.schedule('a', 2, run('a'));   // koalesceres: kun nyeste args kjøres
  q.schedule('b', 9, run('b'));
  await q.idle();
  assert.deepStrictEqual(ran, [['a', 2], ['b', 9]]);
});

test('makeQueue: feil i én jobb stopper ikke kjeden', async () => {
  const q = G.makeQueue();
  const ran = [];
  q.schedule('x', 1, () => Promise.reject(new Error('boom')));
  q.schedule('y', 2, (args) => { ran.push(args); return Promise.resolve(); });
  await q.idle();
  assert.deepStrictEqual(ran, [2]);
});

test('makeQueue: ny endring under kjøring gir ny kjøring etterpå', async () => {
  const q = G.makeQueue();
  const ran = [];
  let firstStarted;
  const gate = new Promise((r) => { firstStarted = r; });
  q.schedule('a', 1, async (args) => { firstStarted(); ran.push(args); });
  await gate;
  q.schedule('a', 2, async (args) => { ran.push(args); });
  await q.idle();
  assert.deepStrictEqual(ran, [1, 2]);
});
```

- [ ] **Step 2: Kjør — verifiser FAIL**

Run: `node --test tests/js/dash-webr.test.js`
Expected: FAIL — cannot find module js/dash-webr.js

- [ ] **Step 3: Skriv `js/dash-webr.js`**

```js
/* dash-webr.js — JS-glue for dash v2 i R-modus (spec 2026-07-12 §5.3).
   webr/dash.R samler deklarasjoner under script-kjøringen; denne fila henter
   registeret etterpå (mount), bygger dashboardet via window.Dash (js/dash.js)
   og re-kjører funksjonskort async via evalR + captureR i en EGEN Shelter
   (aldri app-shelteret — purge her skal ikke kunne rive andres objekter).
   Ren halvdel: makeQueue — node-testet, ingen DOM/webR. */
(function (global) {
  'use strict';
  var G = {};

  // Sekvensiell kjede med per-nøkkel siste-vinner-koalescing: maks én
  // dash_run om gangen (webR-kanalen serialiserer uansett), og raske
  // widget-endringer på samme kort kollapser til nyeste verdier.
  G.makeQueue = function () {
    var chain = Promise.resolve();
    var pending = {};
    return {
      schedule: function (key, args, run) {
        var had = Object.prototype.hasOwnProperty.call(pending, key);
        pending[key] = args;
        if (had) return;
        chain = chain.then(function () {
          var a = pending[key];
          delete pending[key];
          return run(a);
        }).catch(function () {});
      },
      idle: function () { return chain; }
    };
  };

  // ---- browser-halvdel ----
  var _defsP = null;     // memoisert: jsonlite + webr/dash.R evaluert
  var _shelter = null;   // dash-webr sin egen Shelter

  G.ensureDefs = function () {
    if (_defsP) return _defsP;
    _defsP = (async function () {
      var M = global.M2PY;
      await M.loadWebR();
      var webR = M.getWebR();
      try { await webR.installPackages(['jsonlite'], { quiet: true }); } catch (e) {}
      var r = await fetch('webr/dash.R?v=' + (global.M2PY_VERSION || '1'));
      if (!r.ok) throw new Error('webr/dash.R: ' + r.status);
      await webR.evalRVoid(await r.text());
    })().catch(function (e) { _defsP = null; throw e; });
    return _defsP;
  };

  G.reset = async function () {
    if (!_defsP) return;
    await _defsP;
    await global.M2PY.getWebR().evalRVoid('.dash_reset()');
  };

  async function dashShelter() {
    if (_shelter) return _shelter;
    var webR = global.M2PY.getWebR();
    _shelter = await new webR.Shelter();
    return _shelter;
  }

  async function evalRString(code) {
    var webR = global.M2PY.getWebR();
    var obj = await webR.evalR(code);
    try {
      var js = await obj.toJs();
      return (js && js.values && js.values[0] != null) ? String(js.values[0]) : '';
    } finally {
      try { await webR.destroy(obj); } catch (e) {}
    }
  }

  function bitmapToDataUri(bmp) {
    var c = document.createElement('canvas');
    c.width = bmp.width;
    c.height = bmp.height;
    c.getContext('2d').drawImage(bmp, 0, 0);
    return c.toDataURL('image/png');
  }

  // Kjør ett funksjonskort R-side; returnér endelig payload.
  // Regler (spec §5.3): payload-JSON fra .dash_run er sannheten, MEN
  //  - fanget plott vinner over tom tekst (ggplot/base-plot-kort)
  //  - stdout vinner over tom tekst (print-paritet med python-adapterne)
  async function runCard(di, ci, rawValues) {
    var shelter = await dashShelter();
    var code = '.dash_run(' + di + ', ' + ci + ', ' +
               JSON.stringify(JSON.stringify(rawValues)) + ')';
    var cap = await shelter.captureR(code, {
      withAutoprint: false,
      captureGraphics: { width: 720, height: 480 }
    });
    try {
      var js = await cap.result.toJs();
      var payload = JSON.parse((js && js.values && js.values[0]) ||
        '{"kind":"error","message":"tomt svar fra .dash_run"}');
      if (payload.kind === 'text' && !payload.text) {
        if (cap.images && cap.images.length) {
          payload = { kind: 'image',
                      src: bitmapToDataUri(cap.images[cap.images.length - 1]) };
        } else {
          var stdout = (cap.output || [])
            .filter(function (o) { return o.type === 'stdout'; })
            .map(function (o) { return String(o.data); })
            .join('\n');
          if (stdout.trim()) payload = { kind: 'text', text: stdout.replace(/\s+$/, '') };
        }
      }
      return payload;
    } finally {
      try { await shelter.purge(); } catch (e) {}
    }
  }

  // Bygg dashboardene fra R-registeret. Kalles av runHybridR ETTER
  // renderROutputParts (tekst-output først, dashboard appendes under).
  // Venter på førsterenders (idle) så kallerens shelter-purge ikke kan
  // treffe kjøringer i flukt.
  G.mount = async function () {
    if (!_defsP) return;                 // ingen dash-defs denne økten
    await _defsP;
    var reg = null;
    try { reg = JSON.parse(await evalRString('.dash_registry_json()')); }
    catch (e) { console.warn('dash-webr: registry', e); }
    if (!reg || !reg.dashes || !reg.dashes.length) return;
    var q = G.makeQueue();

    reg.dashes.forEach(function (dashDecl, dIdx) {
      var di = dIdx + 1;
      var dashId = global.Dash.create(JSON.stringify(
        { title: dashDecl.title, layout: dashDecl.layout }));
      var sharedRaw = {};
      var cardsMeta = [];

      function effective(cm) {
        var vals = {};
        (cm.params || []).forEach(function (p) {
          if (p in cm.ownRaw) vals[p] = cm.ownRaw[p];
          else if (p in sharedRaw) vals[p] = sharedRaw[p];
        });
        return vals;
      }

      function scheduleRun(cm) {
        global.Dash.setBusy(cm.cid);
        q.schedule(di + ':' + cm.ci, effective(cm), async function (vals) {
          var payload;
          try { payload = await runCard(di, cm.ci, vals); }
          catch (e) {
            payload = { kind: 'error', message: String((e && e.message) || e) };
          }
          global.Dash.updateCard(cm.cid, JSON.stringify(payload), null);
        });
      }

      (dashDecl.cards || []).forEach(function (card, cIdx) {
        var ci = cIdx + 1;
        var opts = { title: card.title || null, area: card.at || null };
        if (!card.func) {
          opts.content = card.payload;
          global.Dash.addCard(dashId, JSON.stringify(opts), null, null);
          return;
        }
        opts.controls = card.controls || [];
        opts.content = null;
        var cm = { ci: ci, params: card.params || [], ownRaw: {}, cid: null };
        var onChange = function (valuesJson) {
          cm.ownRaw = JSON.parse(valuesJson);
          scheduleRun(cm);
        };
        cm.cid = global.Dash.addCard(dashId, JSON.stringify(opts),
                                     opts.controls.length ? onChange : null, null);
        cm.ownRaw = JSON.parse(global.Dash.initialValues(cm.cid) || '{}');
        cardsMeta.push(cm);
      });

      if (dashDecl.shared && dashDecl.shared.length) {
        global.Dash.addControls(dashId, JSON.stringify(dashDecl.shared),
          function (valuesJson) {
            sharedRaw = JSON.parse(valuesJson);
            var names = Object.keys(sharedRaw);
            cardsMeta.forEach(function (cm) {
              if (cm.params.some(function (p) { return names.indexOf(p) !== -1; }))
                scheduleRun(cm);
            });
          });
        sharedRaw = JSON.parse(global.Dash.initialValues(dashId) || '{}');
      }

      // K2: førsterender med effektive startverdier (defaults eller ds-URL)
      cardsMeta.forEach(scheduleRun);
    });

    await q.idle();
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = G;
  global.DashWebR = G;
})(typeof window !== 'undefined' ? window : globalThis);
```

- [ ] **Step 4: Kjør node-testene**

Run: `node --test tests/js/dash-webr.test.js`
Expected: PASS (3 tester)

- [ ] **Step 5: Wire inn i index.html**

Script-tag rett etter `<script src="js/dash.js"></script>` (fra Task 5):

```html
  <script src="js/dash-webr.js"></script>
```

Hook A — i `runHybridR`, RETT FØR Phase 2-kommentaren/løkka (`// ── Phase 2: run R segments via captureR`, ~linje 8637):

```js
      // dash v2: definer R-adapteret + nullstill registeret FØR segmentene
      // kjører (scriptet kaller dashboard()/add() under kjøringen). Gates på
      // en billig tekst-sjekk så vanlige R-kjøringer ikke betaler fetch/eval.
      if (window.DashWebR && /\bdashboard\s*\(/.test(src)) {
        try {
          await window.DashWebR.ensureDefs();
          await window.DashWebR.reset();
        } catch (e) {
          outputParts.push({ type: 'error', text: 'dash: ' + ((e && e.message) || e) });
        }
      }
```

Hook B — RETT ETTER `renderROutputParts(outputParts);` (~linje 8699), FØR `webRShelter.purge()`:

```js
      // dash v2: bygg dashboardet (om noe) etter at tekst-output er rendret.
      // mount() venter på førsterenders i egen Shelter, så purgen under er trygg.
      if (window.DashWebR) {
        try { await window.DashWebR.mount(); }
        catch (e) { console.warn('dash-webr mount:', e); }
      }
```

- [ ] **Step 6: Kjør alle testene**

Run: `node --test tests/js/ && python3 -m pytest tests/test_pyodide_dash.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add js/dash-webr.js tests/js/dash-webr.test.js index.html
git commit -m "feat(dash): webR-glue — mount fra R-register, async re-kjøring med siste-vinner-kø"
```

---

### Task 8: Eksempler — py06 og r09 (samme dashboard som bry18)

**Files:**
- Create: `examples/py06_dashboard.txt`, `examples/r09_dashboard.txt`
- Modify: `index.html` (eksempel-knapper: python-blokken ved linje 45, r-blokken — finn med `grep -n 'data-mode="r"' index.html`)

**Interfaces:**
- Consumes: hele kjeden (Task 1-7).

- [ ] **Step 1: `examples/py06_dashboard.txt`**

Innholdsmessig lik `bry18_dashboard_fordeling.txt` slik at likheten på tvers av moduser er synlig:

```
#options.mode = python
#options.title = "Dashboard — fordelingsutforsker (pyodide)"
#options.description = "scipy.stats i et interaktivt dashboard — normalfordeling med terskel"
import dash
import plotly.express as px
from scipy.stats import norm

d = dash.dashboard("Normalfordelingen", layout="""
    kurve kurve kurve over
    kurve kurve kurve kvantil
""")

def xakse(mu, sigma):
    lo, hi = mu - 4 * sigma, mu + 4 * sigma
    n = 120
    return [lo + i * (hi - lo) / n for i in range(n + 1)]

d.controls(mu=dash.slider(-5, 5, step=1, default=0, label="Forventning (mu)"),
           sigma=dash.slider(1, 4, step=1, label="Standardavvik (sigma)"),
           terskel=dash.play(-5, 10, step=1, label="Terskel (spill av)"))

def tetthet(mu, sigma, terskel):
    xs = xakse(mu, sigma)
    ys = [float(norm.pdf(x, loc=mu, scale=sigma)) for x in xs]
    fig = px.line(x=xs, y=ys, title="Tetthet")
    fig.add_vline(x=terskel)
    return fig

d.add(tetthet, at="kurve")

d.add(lambda mu, sigma, terskel:
          round(100 * float(norm.sf(terskel, loc=mu, scale=sigma)), 1),
      title="P(X > terskel)", unit="%", at="over")

d.add(lambda mu, sigma, terskel:
          round(float(norm.ppf(0.975, loc=mu, scale=sigma)), 2),
      title="97,5 %-kvantilen", at="kvantil")
```

- [ ] **Step 2: `examples/r09_dashboard.txt`**

```
#options.mode = r
#options.title = "Dashboard — fordelingsutforsker (R)"
#options.description = "Samme dashboard som bry18/py06, i R — base-plot fanges som bilde"
#options.show_commands = False
d <- dashboard("Normalfordelingen", layout = "
    kurve kurve kurve over
    kurve kurve kurve kvantil
")

d$controls(mu = slider(-5, 5, step = 1, default = 0, label = "Forventning (mu)"),
           sigma = slider(1, 4, step = 1, label = "Standardavvik (sigma)"),
           terskel = play(-5, 10, step = 1, label = "Terskel (spill av)"))

tetthet <- function(mu, sigma, terskel) {
  xs <- seq(mu - 4 * sigma, mu + 4 * sigma, length.out = 121)
  plot(xs, dnorm(xs, mean = mu, sd = sigma), type = "l",
       xlab = "", ylab = "", main = "Tetthet")
  abline(v = terskel, col = "red")
}
d$add(tetthet, at = "kurve")

d$add(function(mu, sigma, terskel)
        round(100 * pnorm(terskel, mean = mu, sd = sigma, lower.tail = FALSE), 1),
      title = "P(X > terskel)", unit = "%", at = "over")

d$add(function(mu, sigma, terskel)
        round(qnorm(0.975, mean = mu, sd = sigma), 2),
      title = "97,5 %-kvantilen", at = "kvantil")
```

- [ ] **Step 3: Knapper i index.html**

I python-eksempelblokken (ved `data-example="py05_duckdb_block.txt"`, linje 45), legg til under:

```html
              <button type="button" data-example="py06_dashboard.txt" data-mode="python" data-i18n>Dashboard &mdash; fordelingsutforsker</button>
```

I r-eksempelblokken (finn `data-example="r08_across_sample.txt"` e.l. med grep), legg til:

```html
              <button type="button" data-example="r09_dashboard.txt" data-mode="r" data-i18n>Dashboard &mdash; fordelingsutforsker</button>
```

(Ingen en.js-nøkler: eksisterende dashboard-knapper (bry18) er heller ikke oversatt — labels faller tilbake til norsk.)

- [ ] **Step 4: Kjør testene (regresjon)**

Run: `node --test tests/js/ && python3 -m pytest tests/test_pyodide_dash.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add examples/py06_dashboard.txt examples/r09_dashboard.txt index.html
git commit -m "feat(dash): eksempler py06/r09 — samme fordelingsutforsker i pyodide og R"
```

---

### Task 9: Samlet browser-verifisering + M2PY_VERSION-bump

**Files:**
- Modify: `index.html:842` (`window.M2PY_VERSION = '2026-07-12a'`)
- Modify: `.superpowers/sdd/progress.md` (ny ledger-seksjon)

- [ ] **Step 1: Bump M2PY_VERSION**

`index.html:842`: `window.M2PY_VERSION = '2026-07-12a';` (cache-bust for `pyodide/dash.py` og `webr/dash.R`).

- [ ] **Step 2: Browser-røyk (start lokal server: `python3 -m http.server 8000` i repo-rota; avregistrer service worker / hard reload først)**

Sjekkliste — alle punkter må PASSE:

1. **Pyodide:** last `py06_dashboard.txt` i python-modus, Kjør. Dashboard vises med KPI-er (norsk format, U+202F), plotly-kurve. Slider/play-endringer oppdaterer kortene. Ingen konsollfeil. `import dash` trigget IKKE micropip-install av PyPI-dash (sjekk konsoll/nettverk).
2. **Pyodide re-run:** kjør scriptet 3× — ingen duplisering, ingen «proxy destroyed»-feil, ingen akkumulering i DOM.
3. **Pyodide matplotlib:** kjør et minimalt script (`import dash, matplotlib.pyplot as plt; d=dash.dashboard("T"); fig,ax=plt.subplots(); ax.plot([1,2,3]); d.add(fig)`) → bildekort.
4. **R:** last `r09_dashboard.txt` i R-modus, Kjør. Dashboard bygges etter kjøringen; kort viser shimmer under re-kjøring; slider-endring oppdaterer plott (base-plot som bilde) og KPI-er; raske endringer gir ingen stale render.
5. **R feilkort:** endre en funksjon til å kalle `stop("x")` i konsollen-testscript → rødt feilkort, resten av dashboardet virker.
6. **Brython-regresjon:** kjør bry17-22 — KPI-format/delta ser riktig ut (v3-kontrakten), duckdb-dashboardet (bry22) virker.
7. **URL-state:** endre widgets i py06, kopier URL med `;ds=`, åpne i ny fane → samme tilstand. Samme for r09.
8. **Tema:** bytt lys/mørk med åpent dashboard i hver modus — lesbart, plotly-font følger med.
9. **Output-only-visning:** `#options.view = output-only` i py06 → bare dashboard.
10. **Strukturert tabell:** i r09-konsollen: `d$add(head(mtcars))`-variant (legg midlertidig til i scriptet) → stylet tabell (zebra, sticky header).

Stopp og feilsøk (superpowers:systematic-debugging) ved avvik — IKKE huk av før alt passerer.

- [ ] **Step 3: Ledger-notat**

Append i `.superpowers/sdd/progress.md` en ny seksjon `# dash v2 fase 2 (runtimes) — ledger (branch dash-v2-runtimes)` med status per task + kjente avvik (minst: brython-Series-punktet fra spec §7 var alt dekket av S1; pyodide-Series bruker to_frame().to_html() i stedet for strukturert tabell — begge bevisste avvik).

- [ ] **Step 4: Commit**

```bash
git add index.html .superpowers/sdd/progress.md
git commit -m "chore(dash): M2PY_VERSION-bump + verifisering fase 2-runtimes"
```

---

### Task 10: Openstat-synk

**Files (openstat-repoet, `~/Documents/GitHub/openstat/`):**
- Copy verbatim: `js/dash.js`, `js/dash-webr.js`, `pyodide/dash.py`, `webr/dash.R`, `brython/dash.py`, `examples/py06_dashboard.txt`, `examples/r09_dashboard.txt`, `tests/js/dash.test.js`, `tests/js/dash-webr.test.js`, `tests/test_pyodide_dash.py`
- Hand-port: `index.html`-endringene (anker-basert — openstats index.html har annen linjenummerering; finn ankrene med grep: `js/brython-engine.js"></script>`, `preRun: async function`, `__ensureDuckBridge`, `// ── Phase 2: run R segments`, `renderROutputParts(outputParts);`, `M2PY_VERSION =`, eksempel-knappblokkene)

- [ ] **Step 1: Branch + kopier filer**

```bash
cd ~/Documents/GitHub/openstat && git checkout main && git pull && git checkout -b dash-v2-runtimes
for f in js/dash.js js/dash-webr.js brython/dash.py tests/js/dash.test.js tests/js/dash-webr.test.js tests/test_pyodide_dash.py examples/py06_dashboard.txt examples/r09_dashboard.txt; do
  mkdir -p "$(dirname "$f")" && cp ~/Documents/GitHub/safestat/"$f" "$f"; done
mkdir -p pyodide webr
cp ~/Documents/GitHub/safestat/pyodide/dash.py pyodide/dash.py
cp ~/Documents/GitHub/safestat/webr/dash.R webr/dash.R
```

- [ ] **Step 2: Hand-port index.html-endringene**

Samme syv endringer som Task 5/7/8/9 (script-tags, `__ensurePyDash`, preRun-hook, runHybridR hook A+B, eksempel-knapper, M2PY_VERSION-bump) — via ankrene over. VIKTIG: openstat = safestat minus funksjoner — sjekk at python- og r-modus finnes i openstats modeRegistry før porting; mangler en modus, port kun det som gjelder. IKKE rør openstats LIB_REGISTRY-dash-oppføring (js-deps er `{url, global}`-objekter — kjent felle).

- [ ] **Step 3: Kjør testene i openstat**

Run: `cd ~/Documents/GitHub/openstat && node --test tests/js/ && python3 -m pytest tests/test_pyodide_dash.py -q`
Expected: PASS

- [ ] **Step 4: Browser-røyk i openstat (kortversjon)**

py06 + r09 + ett bry-dashboard — bygger, interagerer, ingen konsollfeil.

- [ ] **Step 5: Commit (begge repoer er nå på umergede feature-brancher)**

```bash
git add -A && git commit -m "feat(dash): dash v2 fase 2 — pyodide- og webR-runtime (synk fra safestat)"
```

Merk i safestat-ledgeren at begge brancher er komplette og venter på Hans' testing før merge/push (konvensjon).

---

## Self-Review (utført ved planskriving)

- **Spec-dekning:** §3.1→T1, §3.2/3.3→T2, §7-slanking→T3, §4→T4, §4.1→T5, §5.1/5.2→T6, §5.3→T7, §8-eksempler→T8, §8-røyk+§9→T9, synk→T10. Suksesskriterium 4 (netto Python-linjer ned i brython/dash.py) verifiseres i T3 (≈60 linjer slettet, ~8 inn).
- **Kjente bevisste avvik fra spec:** brython-Series-punktet (§7) er alt dekket av S1-arbeidet (to_html finnes); pyodide-Series bruker `to_frame().to_html()` i stedet for strukturert tabell (enklere, samme resultat). Begge noteres i ledgeren (T9).
- **Typekonsistens:** payload-feltene `{value, unit, fmt, ref, bra}` er identiske i T1 (motor), T3 (brython), T4 (pyodide), T6 (R). `.dash_run(di, ci, values_json)`-signaturen i T6 matcher kallet i T7 (`runCard`). `makeQueue().schedule(key, args, run)` i T7 matcher testene.
