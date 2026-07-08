# jamovi-modus 2.0 fase 1 — implementeringsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** jamovi-modus kjører ekte `jmv`/`scatr`-analyser i webR med autogenererte dialoger, live-oppdatering og jamovi-identiske tabeller/figurer.

**Architecture:** Build-time generator (Python) leser jamovi sine YAML-definisjoner → `js/modes/jmv_specs.js`. Runtime-motor i `js/modes/jamovi.js` installerer jmv lazy, bygger R-kall fra dialogtilstand, serialiserer resultattreet til JSON via en R-hjelper og rendrer med eksisterende jamovi-CSS. Designdokument: `docs/PLAN_jamovi_jmv_engine.md`.

**Tech Stack:** Vanilla JS (IIFE, `window.M2PY`-API), webR (`shelter.captureR` med `captureGraphics`), R-pakkene jmv/scatr/jsonlite (wasm), Python 3 + PyYAML (generator), pytest.

## Global Constraints

- Appen har **ikke** byggesystem: alle JS-filer lastes direkte; generator kjøres manuelt.
- `js/modes/jamovi_v1.js` + `css/modes/jamovi_v1.css` er fredet (sikkerhetskopi) — rør dem aldri.
- Databroen `ensureJamoviDataInWebR()` (aktivt datasett → webR `data` med verdietiketter) gjenbrukes uendret.
- Data-fanen, Variabler-fanen, Beregn/Omkod/Filter-dialogene og eksempeldatasett-velgeren beholdes uendret fra dagens jamovi.js.
- All brukersynlig norsk tekst wrappes i `T(...)` som i dag.
- Kodestil: `var`, IIFE, ingen moduler — match eksisterende jamovi.js.
- Verifisering i nettleser: `python3 -m http.server 8791` fra repo-rot + Chrome mot `http://127.0.0.1:8791/…`.

---

### Task 1: Vendore YAML + spec-generator

**Files:**
- Create: `tools/jmv_yaml/jmv.yaml` (kopi av jamovi sin definisjonsfil)
- Create: `tools/jmv_yaml/scatr.yaml`
- Create: `tools/gen_jmv_specs.py`
- Create: `js/modes/jmv_specs.js` (generert)
- Test: `tests/test_gen_jmv_specs.py`

**Interfaces:**
- Produces: `window.JMV_SPECS` — objekt `{ <analysenavn>: { name, ns, title, menuGroup, menuSubgroup, menuTitle, menuSubtitle, options: [ { name, type, title, default, suggested?, permitted?, choices?, min?, max? } ] } }`. Task 3–5 leser dette.

- [ ] **Step 1: Kopier YAML-kildene inn i repoet**

```bash
mkdir -p tools/jmv_yaml
cp "/Applications/jamovi.app/Contents/Resources/modules/jmv/jamovi-full.yaml" tools/jmv_yaml/jmv.yaml
cp "/Applications/jamovi.app/Contents/Resources/modules/scatr/jamovi-full.yaml" tools/jmv_yaml/scatr.yaml
```

- [ ] **Step 2: Skriv den feilende testen** (`tests/test_gen_jmv_specs.py`)

```python
"""Tester for tools/gen_jmv_specs.py — genererer js/modes/jmv_specs.js fra jamovi-YAML."""
import json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_specs():
    subprocess.run([sys.executable, str(ROOT / 'tools/gen_jmv_specs.py')], check=True)
    txt = (ROOT / 'js/modes/jmv_specs.js').read_text()
    return json.loads(txt[txt.index('=') + 1:].rstrip().rstrip(';'))


def test_alle_fase1_analyser_er_med():
    s = load_specs()
    for n in ['descriptives', 'ttestIS', 'ttestPS', 'ttestOneS', 'anovaOneW', 'anova',
              'anovaNP', 'corrMatrix', 'linReg', 'logRegBin', 'propTestN', 'contTables',
              'scat', 'pareto']:
        assert n in s, n


def test_ttestIS_opsjoner():
    s = load_specs()
    opts = {o['name']: o for o in s['ttestIS']['options']}
    assert opts['welchs']['type'] == 'Bool' and opts['welchs']['default'] is False
    assert opts['vars']['type'] == 'Variables'
    assert opts['hypothesis']['type'] == 'List'
    assert any(c['value'] == 'different' for c in opts['hypothesis']['choices'])
    assert 'data' not in opts  # Data-typen skal filtreres bort


def test_descriptives_har_statistikk_og_plottopsjoner():
    s = load_specs()
    names = [o['name'] for o in s['descriptives']['options']]
    for n in ['hist', 'box', 'violin', 'bar', 'sd', 'skew', 'kurt', 'pcValues', 'splitBy']:
        assert n in names, n


def test_menygrupper():
    s = load_specs()
    assert s['descriptives']['menuGroup'] == 'Exploration'
    assert s['scat']['menuGroup'] == 'Exploration'     # ikke '.'-oppføringen
    assert s['anovaNP']['menuSubgroup'] == 'Non-Parametric'
```

- [ ] **Step 3: Kjør testen — skal feile**

Kjør: `python3 -m pytest tests/test_gen_jmv_specs.py -v`
Forventet: FAIL (`tools/gen_jmv_specs.py` finnes ikke)

- [ ] **Step 4: Skriv generatoren** (`tools/gen_jmv_specs.py`)

```python
#!/usr/bin/env python3
"""Genererer js/modes/jmv_specs.js fra jamovi sine YAML-definisjoner.

Kjøring:  python3 tools/gen_jmv_specs.py
Kilder:   tools/jmv_yaml/{jmv,scatr}.yaml — kopier av jamovi-full.yaml fra
          jamovi-appen (samme filer ligger i jamovi sine GitHub-repoer).
"""
import json
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = {'jmv': ROOT / 'tools/jmv_yaml/jmv.yaml',
           'scatr': ROOT / 'tools/jmv_yaml/scatr.yaml'}
PHASE1 = ['descriptives', 'ttestIS', 'ttestPS', 'ttestOneS', 'anovaOneW', 'anova',
          'anovaNP', 'corrMatrix', 'linReg', 'logRegBin', 'propTestN', 'contTables',
          'scat', 'pareto']
ROLE_TYPES = {'Variable', 'Variables', 'Pairs'}
SKIP_TYPES = {'Data', 'Output'}


def convert_option(o):
    t = o.get('type')
    if t in SKIP_TYPES or o.get('hidden'):
        return None
    out = {'name': o['name'], 'type': t,
           'title': o.get('title') or o['name'], 'default': o.get('default')}
    if t in ROLE_TYPES:
        out['suggested'] = o.get('suggested') or []
        out['permitted'] = o.get('permitted') or []
    if t == 'List':
        out['choices'] = [
            {'value': c.get('name'), 'title': c.get('title', c.get('name'))}
            if isinstance(c, dict) else {'value': c, 'title': c}
            for c in (o.get('options') or [])]
    if t in ('Number', 'Integer'):
        if o.get('min') is not None:
            out['min'] = o.get('min')
        if o.get('max') is not None:
            out['max'] = o.get('max')
    return out


def main():
    specs = {}
    for ns, path in SOURCES.items():
        for doc in yaml.safe_load_all(path.read_text()):
            if not isinstance(doc, dict):
                continue
            for a in doc.get('analyses', []):
                name = a.get('name')
                # scatr har duplikate menyoppføringer med menuGroup '.'/'More'
                if name not in PHASE1 or a.get('menuGroup') in ('.', 'More'):
                    continue
                if name in specs:
                    continue
                opts = [convert_option(o) for o in a.get('options', [])]
                specs[name] = {
                    'name': name, 'ns': ns, 'title': a.get('title'),
                    'menuGroup': a.get('menuGroup'),
                    'menuSubgroup': a.get('menuSubgroup') or '',
                    'menuTitle': a.get('menuTitle'),
                    'menuSubtitle': a.get('menuSubtitle') or '',
                    'options': [o for o in opts if o],
                }
    missing = [n for n in PHASE1 if n not in specs]
    if missing:
        raise SystemExit(f'Mangler analyser i YAML: {missing}')
    js = ('// GENERERT av tools/gen_jmv_specs.py — ikke rediger for hånd.\n'
          'window.JMV_SPECS = '
          + json.dumps(specs, ensure_ascii=False, indent=1) + ';\n')
    (ROOT / 'js/modes/jmv_specs.js').write_text(js)
    print(f'Skrev {len(specs)} analyser til js/modes/jmv_specs.js')


if __name__ == '__main__':
    main()
```

- [ ] **Step 5: Kjør testene — skal passere**

Kjør: `python3 -m pytest tests/test_gen_jmv_specs.py -v`
Forventet: 4 PASS. Hvis `test_menygrupper` feiler på `anovaNP`: åpne `tools/jmv_yaml/jmv.yaml`, sjekk feltets faktiske verdi og juster asserten til YAML-ens sannhet (YAML-en er fasit).

- [ ] **Step 6: Commit**

```bash
git add tools/ js/modes/jmv_specs.js tests/test_gen_jmv_specs.py
git commit -m "jamovi 2.0: spec-generator fra jamovi sine YAML-definisjoner"
```

---

### Task 2: R-serialiserer + røyktestside

**Files:**
- Create: `js/modes/jmv_helpers.R`
- Create: `tests/manual/jmv_smoke.html`

**Interfaces:**
- Produces (R): `.jmv_serialize(results)` → R-liste klar for `jsonlite::toJSON(auto_unbox=TRUE, na='null')` med struktur
  `{type:'group', title, items:[ {type:'table', title, colNames:[...], columns:[{name,title,superTitle,format}], rows:[[...]], notes:[...]} | {type:'image', title} | {type:'text', title, text} | {type:'group', ...} ]}`.
  Bilder serialiseres KUN som plassholdere — selve PNG-ene kommer fra `captureGraphics` i samme rekkefølge som `print(results)` tegner dem (= traverseringsrekkefølgen).
- Konvensjon (brukes av Task 3): motoren kjører `print(.r); cat("\n##JMV##"); cat(jsonlite::toJSON(.jmv_serialize(.r), auto_unbox=TRUE, na='null'))` og JS parser alt etter siste `##JMV##`.

- [ ] **Step 1: Skriv `js/modes/jmv_helpers.R`**

```r
# Hjelpere for jamovi-modus 2.0. Lastes én gang av ensureJmvLoaded().
# .jmv_serialize går rekursivt gjennom et jmvcore-resultattre og returnerer
# en liste som jsonlite::toJSON kan sende til JS. Bilder blir plassholdere;
# selve grafikken fanges av captureGraphics når print(results) tegner dem,
# i samme rekkefølge som traverseringen her.
.jmv_serialize <- function(x) {
  walk <- function(it) {
    if (is.null(it)) return(NULL)
    vis <- tryCatch(it$visible, error = function(e) TRUE)
    if (identical(vis, FALSE)) return(NULL)
    if (inherits(it, 'Image'))
      return(list(type = 'image', title = it$title))
    if (inherits(it, 'Table')) {
      df <- tryCatch(it$asDF, error = function(e) NULL)
      if (is.null(df)) return(NULL)
      cols <- tryCatch(
        lapply(Filter(function(co) !identical(co$visible, FALSE), it$columns),
               function(co) list(
                 name = co$name,
                 title = if (nzchar(co$title %||% '')) co$title else co$name,
                 superTitle = co$superTitle %||% '',
                 format = paste(co$format %||% '', collapse = ','))),
        error = function(e) lapply(names(df), function(n)
          list(name = n, title = n, superTitle = '', format = '')))
      rows <- lapply(seq_len(nrow(df)), function(i)
        unname(lapply(as.list(df[i, , drop = FALSE]), function(v)
          if (is.numeric(v) && !is.finite(v)) NA else v)))
      notes <- tryCatch(
        unname(lapply(it$notes, function(n) if (is.list(n)) n$note else as.character(n))),
        error = function(e) list())
      return(list(type = 'table', title = it$title, colNames = as.list(names(df)),
                  columns = cols, rows = rows, notes = notes))
    }
    kids <- tryCatch(it$items, error = function(e) NULL)
    if (!is.null(kids)) {
      out <- Filter(Negate(is.null), lapply(kids, walk))
      if (!length(out)) return(NULL)
      return(list(type = 'group', title = it$title, items = out))
    }
    txt <- tryCatch(paste(capture.output(print(it)), collapse = '\n'),
                    error = function(e) '')
    if (!nzchar(txt)) return(NULL)
    list(type = 'text', title = it$title, text = txt)
  }
  `%||%` <- function(a, b) if (is.null(a)) b else a
  walk(x)
}
```

Merk: `%||%` må defineres FØR bruk i R < 4.4-stil — flytt `\`%||%\` <- ...`-linjen øverst i filen (før `.jmv_serialize`), ikke nederst i funksjonen slik utkastet viser.

- [ ] **Step 2: Skriv røyktestsiden** (`tests/manual/jmv_smoke.html`)

Selvstendig side (samme mønster som fase 0-spiken): laster webR, installerer `c('jmv','scatr','jsonlite')`, `library()`, henter `../../js/modes/jmv_helpers.R` og evaluerer den, og kjører så disse tre serialiserings-testene med sentinel-konvensjonen:

```html
<!DOCTYPE html>
<html lang="no"><head><meta charset="utf-8"><title>jmv røyktest</title>
<style>body{font:14px/1.5 -apple-system,sans-serif;margin:20px;max-width:900px}
pre{background:#f6f7f9;border:1px solid #ddd;padding:8px;overflow-x:auto;font-size:12px}
img{border:1px solid #ddd;max-width:100%}.ok{color:#15803d}.feil{color:#b91c1c}</style>
</head><body>
<h1>jmv-serialiserer: røyktest</h1>
<div id="status">Starter…</div><div id="out"></div>
<script type="module">
const st = document.getElementById('status'), out = document.getElementById('out');
const put = (h) => out.insertAdjacentHTML('beforeend', h);
window.__SMOKE = { done: false, failures: [] };
try {
  const { WebR } = await import('https://webr.r-wasm.org/latest/webr.mjs');
  const webR = new WebR(); await webR.init();
  st.textContent = 'Installerer jmv/scatr/jsonlite…';
  await webR.evalRVoid(`webr::install(c('jmv','scatr','jsonlite'))`);
  await webR.evalRVoid(`suppressMessages({library(jmv);library(scatr);library(jsonlite)})`);
  const helpers = await fetch('../../js/modes/jmv_helpers.R').then(r => r.text());
  await webR.evalRVoid(helpers);
  const shelter = await new webR.Shelter();
  const CASES = [
    ['ttestIS', `d <- subset(ToothGrowth, dose != 1)
      .r <- jmv::ttestIS(data=d, vars='len', group='supp', welchs=TRUE, desc=TRUE, qq=TRUE)`,
      { minTables: 2, minImages: 1 }],
    ['descriptives', `d <- ToothGrowth; d$dose <- factor(d$dose)
      .r <- jmv::descriptives(data=d, vars='len', splitBy='dose', hist=TRUE, box=TRUE, freq=TRUE)`,
      { minTables: 1, minImages: 2 }],
    ['contTables', `d <- data.frame(a=rep(c('x','y'),30), b=rep(c('u','v','u'),20))
      .r <- jmv::contTables(data=d, rows='a', cols='b', exp=TRUE, phiCra=TRUE)`,
      { minTables: 2, minImages: 0 }],
  ];
  for (const [name, setup, want] of CASES) {
    st.textContent = 'Kjører ' + name + '…';
    const cap = await shelter.captureR(
      `local({\n${setup}\nprint(.r)\ncat('\\n##JMV##')\ncat(jsonlite::toJSON(.jmv_serialize(.r), auto_unbox=TRUE, na='null'))\n})`,
      { captureGraphics: { width: 520, height: 380 } });
    const text = cap.output.filter(m => m.type === 'stdout').map(m => m.data).join('\n');
    const payload = JSON.parse(text.slice(text.lastIndexOf('##JMV##') + 7));
    const count = (n, t) => (n.type === t ? 1 : 0) + (n.items || []).reduce((s, k) => s + count(k, t), 0);
    const nT = count(payload, 'table'), nI = count(payload, 'image');
    const ok = nT >= want.minTables && nI >= want.minImages && nI === (cap.images || []).length;
    if (!ok) window.__SMOKE.failures.push(name);
    put(`<h2 class="${ok ? 'ok' : 'feil'}">${name}: ${ok ? 'OK' : 'FEIL'} — ${nT} tabeller, ${nI} image-noder, ${(cap.images||[]).length} bilder fanget</h2><pre>${JSON.stringify(payload, null, 1).slice(0, 4000)}</pre>`);
    for (const bmp of cap.images || []) {
      const c = document.createElement('canvas'); c.width = bmp.width; c.height = bmp.height;
      c.getContext('2d').drawImage(bmp, 0, 0);
      put(`<img src="${c.toDataURL('image/png')}">`);
    }
    if (cap.cleanup) await cap.cleanup();
  }
  st.textContent = window.__SMOKE.failures.length ? 'RØYKTEST FEIL: ' + window.__SMOKE.failures.join(', ') : 'RØYKTEST OK';
} catch (e) { st.textContent = 'RØYKTEST FEIL: ' + (e.message || e); window.__SMOKE.failures.push(String(e.message || e)); }
window.__SMOKE.done = true;
</script></body></html>
```

- [ ] **Step 3: Kjør røyktesten — verifiser**

```bash
python3 -m http.server 8791   # fra repo-rot
```

Åpne `http://127.0.0.1:8791/tests/manual/jmv_smoke.html` i Chrome. Vent til statusen viser «RØYKTEST OK» (første gang tar nedlastingen ~1 min).

Forventet: alle tre casene OK; antall image-noder == antall fangede bilder (bekrefter rekkefølge-antakelsen); tabell-JSON har `columns` med `title`/`format` (se at p-kolonnen har format som inneholder `pvalue` eller `zto`).

Hvis `it$columns`-uthentingen feiler (kolonne-metadata mangler): fallback-grenen i `.jmv_serialize` (colNames som titler) skal slå inn automatisk — casene skal fortsatt bli OK. Noter i commitmeldingen hvis fallbacken ble brukt.

- [ ] **Step 4: Commit**

```bash
git add js/modes/jmv_helpers.R tests/manual/jmv_smoke.html
git commit -m "jamovi 2.0: R-serialiserer for jmvcore-resultattre + røyktest"
```

---

### Task 3: Motorkjerne i jamovi.js + modul-laster

**Files:**
- Modify: `index.html:4006` (MODE_MODULES) og `index.html:4008-4020` (loadModeModule)
- Modify: `js/modes/jamovi.js` (nye motorfunksjoner; røret ikke v1-registeret ennå)

**Interfaces:**
- Consumes: `window.JMV_SPECS` (Task 1), `.jmv_serialize`/sentinel-konvensjonen (Task 2), eksisterende `M.ensureWebRShelter()`, `M.getWebR()`, `ensureJamoviDataInWebR()`, `jamoviVariables()`, `fmtNum`/`fmtP`-logikken i `renderJamoviResult`.
- Produces (JS, brukes av Task 4/5):
  - `ensureJmvLoaded(): Promise<void>`
  - `buildJmvCall(spec, values): string` — `values = { <optName>: verdi }`; roller er array av variabelnavn (Variable = array med maks 1)
  - `runJmvAnalysis(spec, values, cardWrap): Promise<void>` — kjører og rendrer inn i eksisterende kort-div
  - `renderJmvResults(cardWrap, payload, images, callString): void`

- [ ] **Step 1: Utvid modul-lasteren til å ta liste av JS-filer**

I `index.html`, erstatt linje 4006:

```js
var MODE_MODULES = { jamovi: { js: ['js/modes/jmv_specs.js', 'js/modes/jamovi.js'], css: 'css/modes/jamovi.css' } };
```

og i `loadModeModule` erstatt script-blokken (linjene med `var s = document.createElement('script')` t.o.m. `document.body.appendChild(s);`) med sekvensiell lasting:

```js
        var files = Array.isArray(m.js) ? m.js.slice() : [m.js];
        (function next() {
          var f = files.shift();
          if (!f) { resolve(); return; }
          var s = document.createElement('script'); s.src = f;
          s.onload = next;
          s.onerror = function(){ reject(new Error('mode module load failed: ' + id + ' (' + f + ')')); };
          document.body.appendChild(s);
        })();
```

- [ ] **Step 2: Legg motorfunksjonene inn i `js/modes/jamovi.js`** (over `// Inject ribbon DOM`-kommentaren)

```js
    // ── jamovi 2.0-motor: ekte jmv/scatr i webR ─────────────────────────────
    var jmvReady = false, jmvLoadingP = null;
    async function ensureJmvLoaded() {
      if (jmvReady) return;
      if (!jmvLoadingP) {
        jmvLoadingP = (async function () {
          M.setStatus(M.rightStatus, T('Laster jamovi-motoren … (~170 MB første gang, sekunder senere)'));
          await M.ensureWebRShelter();
          var webr = M.getWebR();
          await webr.evalRVoid("webr::install(c('jmv','scatr','jsonlite'))");
          await webr.evalRVoid('suppressMessages({library(jmv); library(scatr); library(jsonlite)})');
          var helpers = await fetch('js/modes/jmv_helpers.R').then(function (r) {
            if (!r.ok) throw new Error('jmv_helpers.R: HTTP ' + r.status);
            return r.text();
          });
          await webr.evalRVoid(helpers);
          jmvReady = true;
          M.setStatus(M.rightStatus, '');
        })();
        jmvLoadingP.catch(function () { jmvLoadingP = null; M.setStatus(M.rightStatus, ''); });
      }
      return jmvLoadingP;
    }

    function rQuote(s) { return "'" + String(s).replace(/\\/g, '\\\\').replace(/'/g, "\\'") + "'"; }

    // Dialogtilstand -> R-kall. Opsjoner med default-verdi utelates (ren syntaks).
    function buildJmvCall(spec, values) {
      var args = ['data = data'];
      spec.options.forEach(function (o) {
        var v = values[o.name];
        if (v === undefined || v === null) return;
        if (o.type === 'Variables') {
          if (v.length) args.push(o.name + ' = c(' + v.map(rQuote).join(', ') + ')');
          return;
        }
        if (o.type === 'Variable') {
          if (v.length) args.push(o.name + ' = ' + rQuote(v[0]));
          return;
        }
        if (o.type === 'Pairs') {
          if (v.length >= 2) args.push(o.name + ' = list(list(i1 = ' + rQuote(v[0]) + ', i2 = ' + rQuote(v[1]) + '))');
          return;
        }
        if (JSON.stringify(v) === JSON.stringify(o.default)) return;
        if (o.type === 'Bool') { args.push(o.name + ' = ' + (v ? 'TRUE' : 'FALSE')); return; }
        if (o.type === 'Number' || o.type === 'Integer') {
          if (isFinite(Number(v))) args.push(o.name + ' = ' + Number(v));
          return;
        }
        args.push(o.name + ' = ' + rQuote(v)); // List, String, Level
      });
      return spec.ns + '::' + spec.name + '(' + args.join(', ') + ')';
    }

    async function runJmvAnalysis(spec, values, cardWrap) {
      await ensureJmvLoaded();
      await ensureJamoviDataInWebR();
      // Nominale mål-overstyringer fra Variabler-fanen -> factor() i en lokal kopi
      var factorLines = jamoviVariables()
        .filter(function (v) { return v.type === 'nominal'; })
        .map(function (v) { return 'data[[' + rQuote(v.name) + ']] <- factor(data[[' + rQuote(v.name) + ']])'; })
        .join('\n');
      var call = buildJmvCall(spec, values);
      var rCode = 'local({\n' + factorLines + '\n.r <- ' + call +
        '\nprint(.r)\ncat("\\n##JMV##")\ncat(jsonlite::toJSON(.jmv_serialize(.r), auto_unbox = TRUE, na = "null"))\n})';
      var shelter = await M.ensureWebRShelter();
      var cap = await shelter.captureR(rCode, { captureGraphics: { width: 560, height: 400 } });
      try {
        var text = cap.output.filter(function (m) { return m.type === 'stdout'; })
          .map(function (m) { return m.data; }).join('\n');
        var idx = text.lastIndexOf('##JMV##');
        if (idx === -1) throw new Error(T('Fikk ikke resultat fra jmv'));
        renderJmvResults(cardWrap, JSON.parse(text.slice(idx + 7)), cap.images || [], call);
      } finally { if (cap.cleanup) await cap.cleanup(); }
    }

    // JSON-payload + bildekø -> DOM med eksisterende jamovi-CSS
    function renderJmvResults(cardWrap, payload, images, callString) {
      cardWrap.innerHTML = '';
      var imgQueue = images.slice();
      function fmtCell(v, fmt) {
        if (v === null || v === undefined) return '';
        if (typeof v !== 'number') return String(v);
        if (/pvalue/.test(fmt)) return v < 0.001 ? '< .001' : v.toFixed(3).replace(/^(-?)0\./, '$1.');
        if (Number.isInteger(v)) return String(v);
        var a = Math.abs(v);
        if (a >= 1e9 || (a > 0 && a < 1e-4)) return v.toExponential(2);
        if (a >= 1000) return v.toFixed(0);
        return v.toFixed(a >= 1 ? 2 : 3);
      }
      function walk(node, depth) {
        if (!node) return;
        if (node.type === 'group') {
          if (node.title && depth > 0) {
            var gh = document.createElement('h3'); gh.className = 'jmv-result-title';
            gh.style.fontWeight = '600'; gh.textContent = node.title; cardWrap.appendChild(gh);
          }
          (node.items || []).forEach(function (k) { walk(k, depth + 1); });
          return;
        }
        if (node.type === 'image') {
          var bmp = imgQueue.shift();
          if (bmp) jamoviAppendPlot(node.title || '', bmp, cardWrap);
          return;
        }
        if (node.type === 'text') {
          var pre = document.createElement('pre');
          pre.style.cssText = 'font-size:12px;white-space:pre-wrap;';
          pre.textContent = node.text || ''; cardWrap.appendChild(pre);
          return;
        }
        if (node.type !== 'table') return;
        var h = document.createElement('h3'); h.className = 'jmv-result-title';
        h.textContent = node.title || ''; cardWrap.appendChild(h);
        var cols = (node.columns && node.columns.length) ? node.columns
          : (node.colNames || []).map(function (n) { return { name: n, title: n, superTitle: '', format: '' }; });
        var table = document.createElement('table'); table.className = 'jmv-result-table';
        var thead = document.createElement('thead');
        var hasSuper = cols.some(function (c) { return c.superTitle; });
        if (hasSuper) {
          var trs = document.createElement('tr');
          for (var i = 0; i < cols.length;) {
            var stt = cols[i].superTitle, span = 1;
            while (i + span < cols.length && cols[i + span].superTitle === stt) span++;
            var th0 = document.createElement('th'); th0.colSpan = span; th0.textContent = stt || '';
            if (stt) th0.style.borderBottom = '1px solid #999';
            trs.appendChild(th0); i += span;
          }
          thead.appendChild(trs);
        }
        var trh = document.createElement('tr');
        cols.forEach(function (c) {
          var th = document.createElement('th'); th.textContent = c.title || c.name; trh.appendChild(th);
        });
        thead.appendChild(trh); table.appendChild(thead);
        var tb = document.createElement('tbody');
        var nameToIdx = {}; (node.colNames || []).forEach(function (n, i) { nameToIdx[n] = i; });
        (node.rows || []).forEach(function (row) {
          var tr = document.createElement('tr');
          cols.forEach(function (c) {
            var td = document.createElement('td');
            var ri = (c.name in nameToIdx) ? nameToIdx[c.name] : -1;
            td.textContent = ri === -1 ? '' : fmtCell(row[ri], c.format || '');
            tr.appendChild(td);
          });
          tb.appendChild(tr);
        });
        table.appendChild(tb); cardWrap.appendChild(table);
        (node.notes || []).forEach(function (n) {
          var note = document.createElement('div'); note.className = 'jmv-result-note';
          note.innerHTML = '<i>Note.</i> ' + M.escapeHtml(String(n)); cardWrap.appendChild(note);
        });
      }
      walk(payload, 0);
      if (callString) {
        var syn = document.createElement('pre');
        syn.className = 'jmv-syntax'; syn.textContent = callString;
        cardWrap.appendChild(syn);
      }
    }
```

- [ ] **Step 3: Legg til syntaks-CSS i `css/modes/jamovi.css`**

```css
.jmv-syntax { font: 12px/1.5 ui-monospace, monospace; color: #555; background: #f6f7f9; border: 1px solid var(--jmv-line); border-radius: 4px; padding: 6px 10px; margin: 4px 0 10px; white-space: pre-wrap; }
```

- [ ] **Step 4: Verifiser i konsollen**

Start server, åpne appen, bytt til jamovi-modus, last et eksempeldatasett (hamburger → «Åpne eksempeldatasett…» → `harpo`). I DevTools-konsollen:

```js
var spec = window.JMV_SPECS.ttestIS;
var card = (function(){ var c = document.createElement('div'); c.style.padding='12px';
  document.querySelector('#jamoviResults').appendChild(c); return c; })();
// intern funksjon — eksponer midlertidig for testen: legg 'window.__runJmv = runJmvAnalysis;'
// nederst i jamovi.js under utviklingen (fjernes i Task 5)
__runJmv(spec, { vars: ['grade'], group: ['tutor'], welchs: true, desc: true }, card);
```

Forventet: første kall viser «Laster jamovi-motoren…» i status, deretter dukker ekte jamovi-t-test-tabell + Group Descriptives opp i resultatområdet, med syntakslinjen `jmv::ttestIS(data = data, vars = c('grade'), group = 'tutor', welchs = TRUE, desc = TRUE)` under.

- [ ] **Step 5: Commit**

```bash
git add index.html js/modes/jamovi.js css/modes/jamovi.css
git commit -m "jamovi 2.0: motorkjerne — lazy jmv-lasting, kallbygger, resultatrendrer"
```

---

### Task 4: Dialog-generator, dokket opsjonspanel og live-oppdatering

**Files:**
- Modify: `js/modes/jamovi.js` (ny `openJmvAnalysis(name)`; behold gamle `openJamoviAnalysis` inntil Task 5)
- Modify: `css/modes/jamovi.css` (workspace-layout)

**Interfaces:**
- Consumes: `window.JMV_SPECS`, `runJmvAnalysis`, `jamoviVariables()`, eksisterende rolleboks-CSS (`.jmv-varlist`, `.jmv-rolebox`, `.jmv-section`).
- Produces: `openJmvAnalysis(name: string, presets?: object)` — brukes av menyen i Task 5. `presets` forhåndssetter opsjonsverdier (Figurer-fanen).

- [ ] **Step 1: Workspace-layout (CSS)** — opsjonspanel til venstre for resultatene, som ekte jamovi

```css
#jamoviWorkspace { display: flex; align-items: flex-start; gap: 0; }
#jamoviOptions { flex: 0 0 440px; max-width: 48%; position: sticky; top: 0; background: #fff; border: 1px solid var(--jmv-line); border-radius: 8px; margin: 6px 8px 6px 4px; max-height: calc(100vh - 160px); overflow-y: auto; }
#jamoviOptions .jmv-dialog-head { display: flex; justify-content: space-between; align-items: center; }
#jamoviOptions[hidden] { display: none; }
#jamoviResultsPane { flex: 1; min-width: 0; }
```

- [ ] **Step 2: Ombygg resultatcontaineren** — i `jamoviResultsContainer()`, bytt oppbyggingen slik at strukturen blir `#jamoviWorkspace > #jamoviOptions[hidden] + #jamoviResultsPane > #jamoviResults`:

```js
    function jamoviResultsContainer() {
      var c = M.outputArea.querySelector('#jamoviResults');
      if (!c) {
        M.outputArea.innerHTML = '';
        var ws = document.createElement('div'); ws.id = 'jamoviWorkspace';
        var op = document.createElement('div'); op.id = 'jamoviOptions'; op.hidden = true;
        var pane = document.createElement('div'); pane.id = 'jamoviResultsPane';
        c = document.createElement('div'); c.id = 'jamoviResults';
        pane.appendChild(c); ws.appendChild(op); ws.appendChild(pane);
        M.outputArea.appendChild(ws);
      }
      return c;
    }
```

- [ ] **Step 3: Skriv `openJmvAnalysis`** — dialog fra spec, live-kjøring med debounce

```js
    function openJmvAnalysis(name, presets) {
      var spec = window.JMV_SPECS && window.JMV_SPECS[name];
      if (!spec) { alert(T('Analyse ikke funnet: {id}', { id: name })); return; }
      var vars = jamoviVariables();
      if (!vars.length) { alert(T('Lag/importer data først (kjør et skript eller åpne et eksempeldatasett)')); return; }

      jamoviResultsContainer(); // sikrer workspace-DOM
      var panel = document.getElementById('jamoviOptions');
      panel.hidden = false; panel.innerHTML = '';

      var values = {};
      spec.options.forEach(function (o) {
        if (o.type === 'Variables' || o.type === 'Variable' || o.type === 'Pairs') values[o.name] = [];
        else values[o.name] = (o.default === undefined) ? null : o.default;
      });
      Object.assign(values, presets || {});

      // Resultatkort som live-oppdateres
      var card = jamoviTitleCard(spec.title);
      var cardWrap = card.querySelector('div');

      var runTimer = null, running = false, rerunWanted = false;
      function scheduleRun() {
        clearTimeout(runTimer);
        runTimer = setTimeout(async function () {
          var roles = spec.options.filter(function (o) { return o.type === 'Variables' || o.type === 'Variable' || o.type === 'Pairs'; });
          var firstRole = roles[0];
          if (!firstRole || !(values[firstRole.name] || []).length) return; // ikke nok til å kjøre
          if (running) { rerunWanted = true; return; }
          running = true;
          try { await runJmvAnalysis(spec, values, cardWrap); }
          catch (e) {
            cardWrap.innerHTML = '';
            var pre = document.createElement('pre');
            pre.style.cssText = 'color:#b91c1c;white-space:pre-wrap;font-size:12px;';
            pre.textContent = T('Analysefeil: {msg}', { msg: e.message || e });
            cardWrap.appendChild(pre);
          }
          finally { running = false; if (rerunWanted) { rerunWanted = false; scheduleRun(); } }
        }, 400);
      }

      // Hode med lukkeknapp
      var head = document.createElement('div'); head.className = 'jmv-dialog-head';
      var ht = document.createElement('span'); ht.textContent = spec.title; head.appendChild(ht);
      var x = document.createElement('button'); x.textContent = '✕';
      x.style.cssText = 'border:none;background:none;cursor:pointer;font-size:14px;color:#555;';
      x.addEventListener('click', function () { panel.hidden = true; });
      head.appendChild(x); panel.appendChild(head);

      var body = document.createElement('div'); body.className = 'jmv-dialog-body';
      body.style.display = 'block'; panel.appendChild(body);

      // ── Roller: variabel-liste + rollebokser (gjenbruker v1-markup/CSS) ──
      var roleOpts = spec.options.filter(function (o) { return o.type === 'Variables' || o.type === 'Variable' || o.type === 'Pairs'; });
      var assigned = function () { return roleOpts.reduce(function (a, o) { return a.concat(values[o.name] || []); }, []); };
      var srcSel = null;
      var srcList = document.createElement('ul');
      function typeAllowed(o, v) {
        // suggested/permitted fra YAML: 'continuous'~numeric, ellers nominal/ordinal/factor
        var p = (o.permitted || []).concat(o.suggested || []);
        if (!p.length) return true;
        var wantsNum = p.indexOf('continuous') !== -1 || p.indexOf('numeric') !== -1;
        var wantsNom = p.indexOf('nominal') !== -1 || p.indexOf('ordinal') !== -1 || p.indexOf('factor') !== -1 || p.indexOf('id') !== -1;
        return (v.type === 'numeric' && wantsNum) || (v.type === 'nominal' && wantsNom) || (wantsNum && wantsNom);
      }
      function redraw() {
        srcList.innerHTML = '';
        vars.forEach(function (v) {
          if (assigned().indexOf(v.name) !== -1) return;
          var li = document.createElement('li');
          li.innerHTML = jamoviTypeIcon(v.type) + '<span class="jmv-var-name">' + M.escapeHtml(v.name) + '</span>';
          li.classList.toggle('jmv-selected', srcSel === v.name);
          li.addEventListener('click', function () { srcSel = v.name; redraw(); });
          li.addEventListener('dblclick', function () { assignTo(roleOpts[0], v.name); });
          srcList.appendChild(li);
        });
        roleOpts.forEach(function (o) {
          var ul = o.__ul; ul.innerHTML = '';
          (values[o.name] || []).forEach(function (n) {
            var v = vars.filter(function (x) { return x.name === n; })[0] || { type: 'numeric' };
            var li = document.createElement('li');
            li.innerHTML = jamoviTypeIcon(v.type) + '<span class="jmv-var-name">' + M.escapeHtml(n) + '</span><span class="jmv-remove">✕</span>';
            li.addEventListener('click', function () {
              values[o.name] = values[o.name].filter(function (x) { return x !== n; });
              redraw(); scheduleRun();
            });
            ul.appendChild(li);
          });
        });
      }
      function assignTo(o, name) {
        if (!o || !name) return;
        var v = vars.filter(function (x) { return x.name === name; })[0];
        if (v && !typeAllowed(o, v)) return;
        var max = (o.type === 'Variable') ? 1 : (o.type === 'Pairs' ? 2 : Infinity);
        if ((values[o.name] || []).length >= max) { if (max === 1) values[o.name] = []; else return; }
        values[o.name].push(name); srcSel = null;
        redraw(); scheduleRun();
      }
      var varlistDiv = document.createElement('div'); varlistDiv.className = 'jmv-varlist';
      var vl = document.createElement('div'); vl.className = 'jmv-role-label'; vl.textContent = T('Variabler');
      varlistDiv.appendChild(vl); varlistDiv.appendChild(srcList);
      srcList.style.cssText = 'list-style:none;margin:0;padding:0;border:1px solid #828282;max-height:220px;overflow:auto;background:#fff;';
      body.appendChild(varlistDiv);
      roleOpts.forEach(function (o) {
        var lab = document.createElement('div'); lab.className = 'jmv-role-label'; lab.textContent = o.title;
        var row = document.createElement('div'); row.className = 'jmv-role-row';
        var arrow = document.createElement('button'); arrow.className = 'jmv-arrow'; arrow.textContent = '→';
        arrow.addEventListener('click', function () { assignTo(o, srcSel); });
        var box = document.createElement('ul'); box.className = 'jmv-rolebox';
        box.style.cssText = 'list-style:none;';
        o.__ul = box;
        row.appendChild(arrow); row.appendChild(box);
        body.appendChild(lab); body.appendChild(row);
      });

      // ── Øvrige opsjoner i sammenleggbare seksjoner ──
      var sections = JMV_SECTIONS[spec.name] || null;
      var nonRole = spec.options.filter(function (o) { return roleOpts.indexOf(o) === -1; });
      function control(o) {
        var wrap = document.createElement('label'); wrap.className = 'jmv-opt-item';
        if (o.type === 'Bool') {
          var cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !!values[o.name];
          cb.addEventListener('change', function () { values[o.name] = cb.checked; scheduleRun(); });
          wrap.appendChild(cb); wrap.appendChild(document.createTextNode(' ' + o.title));
        } else if (o.type === 'List') {
          wrap.appendChild(document.createTextNode(o.title + ' '));
          var sel = document.createElement('select'); sel.className = 'jmv-opt-select';
          (o.choices || []).forEach(function (c) {
            var op = document.createElement('option'); op.value = c.value; op.textContent = c.title;
            if (c.value === values[o.name]) op.selected = true; sel.appendChild(op);
          });
          sel.addEventListener('change', function () { values[o.name] = sel.value; scheduleRun(); });
          wrap.appendChild(sel);
        } else if (o.type === 'Number' || o.type === 'Integer') {
          wrap.appendChild(document.createTextNode(o.title + ' '));
          var inp = document.createElement('input'); inp.type = 'number'; inp.value = values[o.name];
          inp.style.cssText = 'width:70px;padding:2px 4px;border:1px solid #828282;border-radius:3px;';
          if (o.min !== undefined) inp.min = o.min;
          if (o.max !== undefined) inp.max = o.max;
          inp.addEventListener('change', function () { values[o.name] = inp.value === '' ? o.default : Number(inp.value); scheduleRun(); });
          wrap.appendChild(inp);
        } else if (o.type === 'String') {
          wrap.appendChild(document.createTextNode(o.title + ' '));
          var ti = document.createElement('input'); ti.type = 'text'; ti.value = values[o.name] || '';
          ti.style.cssText = 'width:130px;padding:2px 4px;border:1px solid #828282;border-radius:3px;';
          ti.addEventListener('change', function () { values[o.name] = ti.value || null; scheduleRun(); });
          wrap.appendChild(ti);
        } else { return null; } // Level/andre: fase 2
        return wrap;
      }
      function addSection(title, opts, open) {
        var found = opts.map(function (n) { return nonRole.filter(function (o) { return o.name === n; })[0]; }).filter(Boolean);
        if (!found.length) return;
        var sec = document.createElement('div'); sec.className = 'jmv-section' + (open ? '' : ' collapsed');
        var hdr = document.createElement('div'); hdr.className = 'jmv-section-hdr';
        hdr.innerHTML = '<span class="jmv-section-caret">▾</span><span class="jmv-section-title">' + M.escapeHtml(title) + '</span>';
        hdr.addEventListener('click', function () { sec.classList.toggle('collapsed'); });
        var sb = document.createElement('div'); sb.className = 'jmv-section-body';
        found.forEach(function (o) { var c = control(o); if (c) sb.appendChild(c); });
        sec.appendChild(hdr); sec.appendChild(sb); body.appendChild(sec);
      }
      if (sections) {
        sections.forEach(function (s, i) { addSection(s.title, s.opts, i === 0); });
        var covered = sections.reduce(function (a, s) { return a.concat(s.opts); }, []);
        addSection(T('Flere valg'), nonRole.map(function (o) { return o.name; })
          .filter(function (n) { return covered.indexOf(n) === -1; }), false);
      } else {
        addSection(T('Valg'), nonRole.map(function (o) { return o.name; }), true);
      }

      redraw(); scheduleRun();
    }
```

- [ ] **Step 4: Legg til seksjonskartet `JMV_SECTIONS`** (over `openJmvAnalysis`) — kuratert gruppering for de viktigste analysene; YAML-rekkefølge for resten:

```js
    var JMV_SECTIONS = {
      descriptives: [
        { title: 'Statistics', opts: ['splitBy','n','missing','mean','median','mode','sum','sd','variance','range','min','max','se','ci','ciWidth','iqr','skew','kurt','sw','pc','pcValues'] },
        { title: 'Plots', opts: ['hist','dens','box','violin','dot','boxMean','boxLabelOutliers','qq','bar','barCounts'] },
        { title: 'Tables', opts: ['freq','desc','extreme','extremeN'] }
      ],
      ttestIS: [
        { title: 'Tests', opts: ['students','welchs','mann','hypothesis'] },
        { title: 'Additional Statistics', opts: ['meanDiff','ci','ciWidth','effectSize','ciES','ciWidthES','desc'] },
        { title: 'Assumption Checks', opts: ['norm','eqv','qq'] },
        { title: 'Plots', opts: ['plots'] }
      ],
      anovaOneW: [
        { title: 'Variances', opts: ['welchs','fishers'] },
        { title: 'Additional Statistics', opts: ['desc','descPlot'] },
        { title: 'Assumption Checks', opts: ['norm','qq','eqv'] },
        { title: 'Post Hoc Tests', opts: ['phMethod','phMeanDif','phSig','phTest','phFlag'] }
      ],
      contTables: [
        { title: 'Statistics', opts: ['chiSq','chiSqCorr','likeRat','fisher','contCoef','phiCra','odds','logOdds','relRisk','ci','ciWidth','gamma','taub'] },
        { title: 'Cells', opts: ['obs','exp','pcRow','pcCol','pcTot'] },
        { title: 'Plots', opts: ['barplot','yaxis','yaxisPc','xaxis','bartype'] }
      ]
    };
```

Merk: opsjonsnavnene i kartet MÅ verifiseres mot generert `jmv_specs.js` (åpne filen og sjekk) — navn som ikke finnes ignoreres stille av `addSection`, men målet er at de fire kartene treffer.

- [ ] **Step 5: Verifiser i nettleseren**

Server + appen + `harpo`-datasettet. Kjør i konsollen: `window.__openJmv('ttestIS')` (eksponer `openJmvAnalysis` midlertidig som `window.__openJmv` nederst i filen).

Forventet: opsjonspanel til venstre (variabelliste, rollebokser, seksjoner), tomt resultatkort til høyre. Dra `grade` → Dependent Variables og `tutor` → Grouping Variable (klikk variabel + pil): t-test-tabellen dukker opp av seg selv etter ~0,5 s. Huk av «Welch's» og «Descriptives Table»: resultatet oppdateres live uten kjøreknapp. Kryss (✕) skjuler panelet; resultatkortet blir stående.

- [ ] **Step 6: Commit**

```bash
git add js/modes/jamovi.js css/modes/jamovi.css
git commit -m "jamovi 2.0: spec-drevet opsjonspanel med live-oppdatering"
```

---

### Task 5: Meny fra specs, Figurer-fane, rydd bort v1-registeret

**Files:**
- Modify: `js/modes/jamovi.js`

**Interfaces:**
- Consumes: `window.JMV_SPECS` (menufelter), `openJmvAnalysis(name, presets)`.
- Produces: Analyser-ribbon og Figurer-fane peker utelukkende på jmv-motoren. Fjernet: `JAMOVI_ANALYSES`, `openJamoviAnalysis`, `jamoviCleanSyntax`, `ensureJamoviDataInWebR` beholdes (brukes av motoren).

- [ ] **Step 1: Bygg menyen fra specs**

Erstatt den hardkodede `catGroups`-strengen (jamovi.js:1208) med generering:

```js
      var GROUP_ORDER = ['Exploration', 'T-Tests', 'ANOVA', 'Regression', 'Frequencies'];
      var CAT_KEYS = { 'Exploration': 'exploration', 'T-Tests': 'ttests', 'ANOVA': 'anova', 'Regression': 'regression', 'Frequencies': 'frequencies' };
      var catGroups = GROUP_ORDER.map(function (g) {
        var items = Object.keys(window.JMV_SPECS || {})
          .map(function (k) { return window.JMV_SPECS[k]; })
          .filter(function (s) { return s.menuGroup === g; })
          .map(function (s) {
            var label = s.menuTitle + (s.menuSubtitle ? ' — ' + s.menuSubtitle : '');
            var sub = s.menuSubgroup ? '<span class="jmv-menu-sub">' + M.escapeHtml(s.menuSubgroup) + '</span>' : '';
            return sub + '<button type="button" data-an="' + s.name + '">' + M.escapeHtml(label) + '</button>';
          }).join('');
        return '<div class="jmv-group"><button type="button" class="jmv-cat" data-cat="' + CAT_KEYS[g] + '">' + g + '</button><div class="jmv-menu">' + items + '</div></div>';
      }).join('');
```

Subgruppe-etiketter trenger CSS (`css/modes/jamovi.css`):

```css
.jmv-menu-sub { display: block; font: 600 11px/1.2 inherit; color: #888; padding: 6px 10px 2px; border-top: 1px solid #eee; }
.jmv-menu-sub:first-child { border-top: none; }
```

Duplikate subgruppe-etiketter (to analyser i samme subgruppe) håndteres slik: generer etiketten kun når subgruppen endrer seg fra forrige element (hold `var lastSub = ''` i map-løkka og nullstill per gruppe).

- [ ] **Step 2: Koble menyklikk til ny motor** — i `initJamoviRibbon`, endre analysemeny-lytterne fra `openJamoviAnalysis(an)` til `openJmvAnalysis(an)`.

- [ ] **Step 3: Figurer-fanen → presets**

Erstatt dagens fire knapper i `data-jpanel="figures"` med:

```js
        + '<div class="jmv-panel" data-jpanel="figures" hidden>'
        +   '<button type="button" class="jmv-ribbon-btn" data-fig="hist">Histogram</button>'
        +   '<button type="button" class="jmv-ribbon-btn" data-fig="box">Box Plot</button>'
        +   '<button type="button" class="jmv-ribbon-btn" data-fig="violin">Violin</button>'
        +   '<button type="button" class="jmv-ribbon-btn" data-fig="bar">Bar Plot</button>'
        +   '<button type="button" class="jmv-ribbon-btn" data-fig="scat">Scatter Plot</button>'
        +   '<button type="button" class="jmv-ribbon-btn" data-fig="pareto">Pareto Plot</button>'
        + '</div>'
```

og wiring (de fire første er descriptives-presets; `violin` krever `box:true` i jmv):

```js
      var FIG_PRESETS = {
        hist:   { an: 'descriptives', preset: { hist: true } },
        box:    { an: 'descriptives', preset: { box: true } },
        violin: { an: 'descriptives', preset: { box: true, violin: true } },
        bar:    { an: 'descriptives', preset: { bar: true } },
        scat:   { an: 'scat', preset: {} },
        pareto: { an: 'pareto', preset: {} }
      };
      rib.querySelectorAll('.jmv-ribbon-btn[data-fig]').forEach(function (b) {
        b.addEventListener('click', function () {
          var f = FIG_PRESETS[b.getAttribute('data-fig')];
          openJmvAnalysis(f.an, f.preset);
        });
      });
```

(Avvik fra designdok: «Line Plot beholdes fra v1» utgår — v1 hadde aldri Line Plot; YAGNI.)

- [ ] **Step 4: Slett v1-registeret** — fjern fra `js/modes/jamovi.js`: `JAMOVI_ANALYSES` (hele objektet), `openJamoviAnalysis`, `jamoviCleanSyntax`, `JAMOVI_ICONS`-oppslagene som peker på slettede id-er (behold `JAMOVI_CAT_ICONS` og `jamoviTypeIcon`). Fjern også de midlertidige `window.__runJmv`/`window.__openJmv`-eksponeringene fra Task 3/4. Behold: alle Data/Variabler-funksjoner, eksempel-picker, `ensureJamoviDataInWebR`, `jamoviAppendPlot`, `jamoviTitleCard`, `jamoviSingletonCard`, `renderJamoviResult` slettes KUN hvis ingen andre kaller den (søk først: `grep -n renderJamoviResult js/modes/jamovi.js`).

- [ ] **Step 5: Full gjennomkjøring i nettleser**

Server + appen + jamovi-modus. Sjekkliste:
- Alle fem menygruppene viser jamovi-navnene (inkl. «One-Way ANOVA — Kruskal-Wallis» under Non-Parametric-etiketten)
- `harpo`: ttestIS ende-til-ende; `clinicaltrial`: anovaOneW med post hoc (Tukey); `parenthood`: corrMatrix + linReg + scat; `agpp`: contTables med Expected counts; `cards`: propTestN
- Figurer-fanen: alle seks knappene åpner riktig panel og gir figur når variabel tilordnes
- Data-fanen og Variabler-fanen virker som før; bytte til nominal i Variabler → variabelen får ball-ikon i dialogene og `factor()` i syntaksen

- [ ] **Step 6: Commit**

```bash
git add js/modes/jamovi.js css/modes/jamovi.css
git commit -m "jamovi 2.0: meny fra jamovi-specs, Figurer-presets, v1-register fjernet"
```

---

### Task 6: Service worker-caching + pinnet webR-versjon

**Files:**
- Modify: `sw.js:6-12` (CACHE-bump + hosts)
- Modify: `index.html:9326` (pinnet webR-URL)

**Interfaces:**
- Produces: webR-runtime og alle wasm-pakker caches permanent (offline + overlever nettleseropprydding bedre); webR-versjonen endrer seg ikke under føttene på oss.

- [ ] **Step 1: Finn gjeldende webR-versjon**

```bash
curl -sI https://webr.r-wasm.org/latest/webr.mjs | grep -i location || \
curl -s https://webr.r-wasm.org/latest/webr.mjs | grep -om1 "version *= *['\"][^'\"]*"
```

Noter versjonen (f.eks. `v0.5.5`). Verifiser at `https://webr.r-wasm.org/<versjon>/webr.mjs` svarer 200.

- [ ] **Step 2: Pin i `index.html`** — erstatt `https://webr.r-wasm.org/latest/webr.mjs` med den versjonerte URL-en, med kommentar:

```js
        // Pinnet webR-versjon (jamovi-modus avhenger av at R-versjon/pakke-ABI
        // ikke endrer seg). Oppgradering: test tests/manual/jmv_smoke.html først.
        const { WebR } = await import('https://webr.r-wasm.org/v0.5.5/webr.mjs');
```

- [ ] **Step 3: `sw.js`** — legg webR-hostene i `CDN_HOSTS` og bump cache:

```js
const CACHE = 'm2py-v7';
const CDN_HOSTS = new Set([
  'cdn.jsdelivr.net',
  'cdn.plot.ly',
  'files.pythonhosted.org',
  'pypi.org',
  'webr.r-wasm.org',    // webR-runtime (jamovi-modus)
  'repo.r-wasm.org'     // wasm-R-pakker: jmv, scatr m.fl. (~170 MB, cache-first)
]);
```

- [ ] **Step 4: Verifiser** — server + appen: DevTools → Application → Service Workers → «Update». Kjør en jamovi-analyse (laster pakkene). Sjekk Application → Cache Storage → `m2py-v7` inneholder `repo.r-wasm.org/...tgz`-oppføringer. Sett så DevTools → Network → «Offline» og last appen på nytt: jamovi-analysen skal fortsatt kjøre (Pyodide-delen krever også cache — det holder å verifisere at *webR-kallene* ikke går på nett: Network-fanen viser `(ServiceWorker)` som kilde for tgz-ene).

- [ ] **Step 5: Commit**

```bash
git add sw.js index.html
git commit -m "jamovi 2.0: sw-caching av webR/wasm-pakker + pinnet webR-versjon"
```

---

### Task 7: Side-om-side-verifisering mot ekte jamovi + synk til openstat

**Files:**
- Modify: `docs/jamovi-validation.md` (verifiseringslogg)
- Synk: kopier endrede filer til `../openstat/`

- [ ] **Step 1: Side-om-side-kontroll** — åpne ekte jamovi (`/Applications/jamovi.app`) og appen ved siden av hverandre. For hvert par under: samme datasett (lsj-CSV-ene i `examples/lsj/`), samme opsjoner, sammenlign tall/kolonner/figurtype:

| Datasett | Analyse | Opsjoner |
|---|---|---|
| harpo | Independent Samples T-Test | Welch's + effect size + descriptives |
| chico | Paired Samples T-Test | Wilcoxon rank |
| clinicaltrial | One-Way ANOVA | Tukey post hoc + Levene |
| parenthood | Correlation Matrix + Linear Regression | CI + std. estimate |
| agpp | Contingency Tables | Expected + Cramér's V |
| cards | Proportion Test (N Outcomes) | — |
| ToothGrowth (jamovi-innebygd → eksporter CSV) | Descriptives | splitBy + hist + violin |

Avvik i formatering (desimaler o.l.) noteres; avvik i TALL er blokkerende feil som må løses før commit.

- [ ] **Step 2: Oppdater `docs/jamovi-validation.md`** med dato, jmv-versjon (2.7.7), tabellen over og resultat per rad (OK / avvik + beskrivelse).

- [ ] **Step 3: Synk til openstat**

```bash
cd /Users/hom/Documents/GitHub/safestat
cp js/modes/jamovi.js js/modes/jmv_specs.js js/modes/jmv_helpers.R ../openstat/js/modes/
cp css/modes/jamovi.css ../openstat/css/modes/
cp -r tools/ ../openstat/tools/
cp tests/test_gen_jmv_specs.py ../openstat/tests/
mkdir -p ../openstat/tests/manual && cp tests/manual/jmv_smoke.html ../openstat/tests/manual/
```

`index.html` og `sw.js` er IKKE identiske filer å blindkopiere — gjør de samme tre punkt-endringene manuelt i openstat (MODE_MODULES-listen, loadModeModule-løkka, webR-pin, CDN_HOSTS+CACHE-bump) og verifiser med `diff <(grep -A8 'MODE_MODULES' index.html) <(grep -A8 'MODE_MODULES' ../openstat/index.html)`.

- [ ] **Step 4: Røyktest openstat** — server openstat på annen port (`python3 -m http.server 8792`), kjør harpo/ttestIS ende-til-ende.

- [ ] **Step 5: Commit (begge repoer)**

```bash
git add docs/jamovi-validation.md && git commit -m "jamovi 2.0: side-om-side-validering mot ekte jamovi"
cd ../openstat && git add -A js/modes css/modes tools tests index.html sw.js && git commit -m "jamovi 2.0: synk fra safestat (jmv-motor)"
```

---

## Self-review-notater (utført ved planskriving)

- **Spec-dekning:** Alle designdok-komponentene har task (generator=1, serialiserer=2, motor=3, dialog/live=4, meny/figurer=5, caching/pinning=6, verifisering/synk=7). Avvik fra designdok: «Line Plot beholdes fra v1» er strøket — v1 hadde aldri Line Plot (feil i designdokumentet); Level-opsjonstypen og u.yaml-layout er eksplisitt fase 2.
- **Typekonsistens:** `values`-formen (roller som array, andre som skalar) brukes likt i Task 3 (`buildJmvCall`) og Task 4 (dialog). Sentinel `##JMV##` lik i Task 2 og 3. `openJmvAnalysis(name, presets)` lik i Task 4 og 5.
- **Kjente usikkerheter implementereren må validere mot virkeligheten:** eksakte opsjonsnavn i `JMV_SECTIONS` (Task 4 Step 4), `it$columns`-API-et (Task 2 Step 3 har fallback), `anovaNP`-menyfelter (Task 1 Step 5).
