# Dashboard View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `#options.view = dashboard` turns a plain py/r script into a shareable interactive dashboard (widgets → live cell re-runs → cards in a grid), with `#navn` registry lookup in the URL hash.

**Architecture:** All new logic in `js/dashboard.js` + `css/dashboard.css` + `js/names.js`. Four narrow integration surfaces: (1) an activation branch in the `btnRun` click handler that mounts the skeleton and truncates `effectiveScript` to the setup zone (same trick as the existing breakpoint truncation), (2) `buildDashboardCtx()` in index.html wrapping the forklar chunk-run machinery (`_exec_pyodide_block` / `webRShelter.captureR`) and output builders, (3) a `name` case in `classifyHash` + `openFromFragment`, (4) `buildROutputNodes` refactor (fragment builder extracted from `renderROutputParts`).

**Tech Stack:** Vanilla JS (IIFE + `module.exports` fallback, house style), `node:test` for pure units (`tests/js/`), Pyodide/webR chunk execution already present in index.html.

**Spec:** `docs/superpowers/specs/2026-07-09-dashboard-design.md` — read it first.

## Global Constraints

- Removing `<script src="js/dashboard.js">` must leave the app identical to today (isolation test, spec §6).
- v1 modes: `python` and `r` only. No remote/strict/encrypted sources, no free-text widget, no nested containers (spec §7).
- Widget values serialized safely: slider → number, checkbox → boolean, dropdown → JSON-encoded string (spec §5).
- DOM text via `textContent`, never `innerHTML`, for author-controlled strings (titles, labels) (spec §5).
- Module files follow house style: `(function (global) { 'use strict'; … })(typeof window !== 'undefined' ? window : globalThis);` with `module.exports` fallback like `js/notebook-links.js`.
- Comment markers everywhere: `#`, `//`, `--` (the triple `extractScriptOptions` uses).
- All user-facing strings in the module go through `ctx.t` / injected `t`.
- Run js tests with `node --test tests/js/` from repo root.

**Deliberate v1 simplification vs spec §1.3:** code between the widget block and the first `#%%` (or a script with no `#%%` at all) becomes **one** unnamed card, not one card per output segment. The floor semantics (re-run everything below on any change) still hold because it is a single cell. Segment splitting can come later without syntax changes.

---

### Task 1: `js/dashboard.js` — parsing + assignment statements (pure core)

**Files:**
- Create: `js/dashboard.js`
- Test: `tests/js/dashboard.test.js`

**Interfaces:**
- Produces: `Dashboard.parse(script) → {title, description, inputs, setupCode, cells, errors}`;
  `Dashboard.assignStatement(mode, name, value) → string`.
  - `inputs`: `[{name, type: 'slider'|'dropdown'|'checkbox', label, min, max, step, default, choices}]`
  - `cells`: `[{name, wide: bool, row: string|null, tab: string|null, deps: string[]|null, code}]`
  - `setupCode`: every line above the first `#input` line (directives included, `#options.*` lines included — the pipeline strips them itself).

- [ ] **Step 1: Write failing tests**

```js
// tests/js/dashboard.test.js
const test = require('node:test');
const assert = require('node:assert');
const D = require('../../js/dashboard.js');

const SCRIPT = [
  '#options.view = dashboard',
  '#options.title = "Dødsårsaker"',
  '# load https://x.example/d.csv as df',
  'prep = 1',
  '',
  '#input year = slider(1990, 2024, step=1, default=2020)',
  '#input cause = dropdown("Kreft", "Hjertesykdom", "Ulykker")',
  '#input per100k = checkbox(default=True, label="Per 100k")',
  '',
  'mellom = year * 2',
  '',
  '#%% Utvikling, wide',
  'sub = df[df.cause == cause]',
  'print(sub)',
  '',
  '#%% Topp 10, row=nokkeltall, deps=year',
  'print(year)',
].join('\n');

test('parse: options, setup zone, inputs, cells', () => {
  const p = D.parse(SCRIPT);
  assert.equal(p.title, 'Dødsårsaker');
  assert.ok(p.setupCode.includes('prep = 1'));
  assert.ok(!p.setupCode.includes('#input'));
  assert.deepEqual(p.inputs.map(i => i.name), ['year', 'cause', 'per100k']);
  assert.equal(p.inputs[0].type, 'slider');
  assert.equal(p.inputs[0].min, 1990);
  assert.equal(p.inputs[0].max, 2024);
  assert.equal(p.inputs[0].default, 2020);
  assert.deepEqual(p.inputs[1].choices, ['Kreft', 'Hjertesykdom', 'Ulykker']);
  assert.equal(p.inputs[1].default, 'Kreft');          // first choice
  assert.equal(p.inputs[2].default, true);
  assert.equal(p.inputs[2].label, 'Per 100k');
  assert.equal(p.cells.length, 3);                     // unnamed pre-cell + 2 named
  assert.equal(p.cells[0].name, '');                   // "mellom = year * 2"
  assert.equal(p.cells[1].name, 'Utvikling');
  assert.equal(p.cells[1].wide, true);
  assert.equal(p.cells[2].row, 'nokkeltall');
  assert.deepEqual(p.cells[2].deps, ['year']);
  assert.equal(p.errors.length, 0);
});

test('parse: norwegian alias bred, tab attr, // and -- markers', () => {
  const p = D.parse([
    '//input x = slider(0, 10)',
    '//%% A, bred, tab=Oversikt',
    'x',
    '-- %% B, tab=Detaljer',
    'x',
  ].join('\n'));
  assert.equal(p.inputs[0].default, 0);                // default = min
  assert.equal(p.cells[0].wide, true);
  assert.equal(p.cells[0].tab, 'Oversikt');
  assert.equal(p.cells[1].tab, 'Detaljer');
});

test('parse: errors on bad input line and duplicate name', () => {
  const p = D.parse('#input 9bad = slider(0,1)\n#input a = slider(0,1)\n#input a = slider(0,1)\n#%% C\na');
  assert.ok(p.errors.length >= 2);
});

test('assignStatement: python and r serialization', () => {
  assert.equal(D.assignStatement('python', 'year', 2021), 'year = 2021');
  assert.equal(D.assignStatement('python', 'ok', true), 'ok = True');
  assert.equal(D.assignStatement('python', 'c', 'Kreft "x"'), 'c = "Kreft \\"x\\""');
  assert.equal(D.assignStatement('r', 'year', 2021), 'year <- 2021');
  assert.equal(D.assignStatement('r', 'ok', false), 'ok <- FALSE');
  assert.equal(D.assignStatement('r', 'c', 'Kreft'), 'c <- "Kreft"');
});
```

- [ ] **Step 2: Run to verify fail** — `node --test tests/js/dashboard.test.js` → FAIL (cannot find module).

- [ ] **Step 3: Implement**

```js
// js/dashboard.js — dashboard view (spec docs/superpowers/specs/2026-07-09-dashboard-design.md)
// Ren parsing/planlegging øverst (node-testet); DOM/orkestrering nederst
// (kjører kun i nettleser). Ingen kjennskap til Pyodide/webR — alt går via
// ctx {mode, run, renderOutput, t} bygget i index.html (buildDashboardCtx).
(function (global) {
  'use strict';
  var D = {};

  var CM = '(?:#|\\/\\/|--)';                              // comment markers, as extractScriptOptions
  var INPUT_RE = new RegExp('^[ \\t]*' + CM + '[ \\t]*input[ \\t]+(\\S+)[ \\t]*=[ \\t]*(slider|dropdown|checkbox)\\(([^)]*)\\)[ \\t]*$');
  var CELL_RE = new RegExp('^[ \\t]*' + CM + '?[ \\t]*%%[ \\t]*(.*)$');   // "--" ends with -, so "-- %%" and "#%%" both hit
  var NAME_RE = /^[A-Za-z_]\w*$/;

  // "1990, 2024, step=1, default=2020" / '"A", "B", label="X"' → {pos:[], kw:{}}
  function parseArgs(inner) {
    var pos = [], kw = {}, buf = '', inStr = null, parts = [];
    for (var i = 0; i < inner.length; i++) {
      var ch = inner[i];
      if (inStr) { buf += ch; if (ch === inStr && inner[i - 1] !== '\\') inStr = null; }
      else if (ch === '"' || ch === "'") { inStr = ch; buf += ch; }
      else if (ch === ',') { parts.push(buf); buf = ''; }
      else buf += ch;
    }
    if (buf.trim()) parts.push(buf);
    parts.forEach(function (p) {
      p = p.trim();
      if (!p) return;
      var eq = p.indexOf('=');
      var isKw = eq > 0 && NAME_RE.test(p.slice(0, eq).trim());
      var val = isKw ? p.slice(eq + 1).trim() : p;
      var parsed;
      if (/^(true|True|TRUE)$/.test(val)) parsed = true;
      else if (/^(false|False|FALSE)$/.test(val)) parsed = false;
      else if (val !== '' && !isNaN(Number(val))) parsed = Number(val);
      else parsed = val.replace(/^["']|["']$/g, '');
      if (isKw) kw[p.slice(0, eq).trim()] = parsed; else pos.push(parsed);
    });
    return { pos: pos, kw: kw };
  }

  function parseInput(name, type, inner, errors) {
    if (!NAME_RE.test(name)) { errors.push('ugyldig variabelnavn i #input: «' + name + '»'); return null; }
    var a = parseArgs(inner);
    var inp = { name: name, type: type, label: a.kw.label || name };
    if (type === 'slider') {
      if (typeof a.pos[0] !== 'number' || typeof a.pos[1] !== 'number') {
        errors.push('slider krever min og maks: «' + name + '»'); return null;
      }
      inp.min = a.pos[0]; inp.max = a.pos[1];
      inp.step = (typeof a.kw.step === 'number') ? a.kw.step : 1;
      inp['default'] = (typeof a.kw['default'] === 'number') ? a.kw['default'] : inp.min;
    } else if (type === 'dropdown') {
      inp.choices = a.pos.map(String);
      if (!inp.choices.length) { errors.push('dropdown uten valg: «' + name + '»'); return null; }
      inp['default'] = (a.kw['default'] !== undefined) ? String(a.kw['default']) : inp.choices[0];
    } else { // checkbox
      inp['default'] = a.kw['default'] === true;
    }
    return inp;
  }

  // "#%% Navn, wide, row=x, tab=Y, deps=a+b" → cell header attrs
  function parseCellHeader(rest) {
    var parts = rest.split(','), cell = { name: '', wide: false, row: null, tab: null, deps: null };
    parts.forEach(function (p, i) {
      p = p.trim();
      if (!p) return;
      var eq = p.indexOf('=');
      if (eq > 0) {
        var k = p.slice(0, eq).trim().toLowerCase(), v = p.slice(eq + 1).trim();
        if (k === 'row') cell.row = v;
        else if (k === 'tab') cell.tab = v;
        else if (k === 'deps') cell.deps = v.split('+').map(function (s) { return s.trim(); }).filter(Boolean);
      } else if (/^(wide|bred)$/i.test(p)) cell.wide = true;
      else if (/^(half|halv)$/i.test(p)) cell.wide = false;
      else if (i === 0) cell.name = p;
    });
    return cell;
  }

  D.parse = function (script) {
    var lines = String(script || '').split(/\r?\n/);
    var errors = [], inputs = [], cells = [], seen = {};
    var optRe = new RegExp('^\\s*' + CM + '\\s*options\\.([\\w]+)\\s*=\\s*("[^"]*"|\'[^\']*\'|\\S+)\\s*$');
    var title = '', description = '';
    var firstInput = -1;
    for (var i = 0; i < lines.length; i++) {
      var m = lines[i].match(INPUT_RE);
      if (m && firstInput < 0) firstInput = i;
      var om = lines[i].match(optRe);
      if (om) {
        var ov = om[2].replace(/^["']|["']$/g, '');
        if (om[1] === 'title') title = ov;
        if (om[1] === 'description') description = ov;
      }
    }
    var setupCode = (firstInput < 0 ? lines : lines.slice(0, firstInput)).join('\n');
    // Nedre del: inputs + celler. Kode før første #%% blir én navnløs celle
    // (bevisst forenkling av spec §1.3 — se plan-header).
    var cur = null;
    for (var j = (firstInput < 0 ? lines.length : firstInput); j < lines.length; j++) {
      var line = lines[j];
      var im = line.match(INPUT_RE);
      if (im) {
        var inp = parseInput(im[1], im[2], im[3], errors);
        if (inp) {
          if (seen['i:' + inp.name]) errors.push('#input «' + inp.name + '» er deklarert to ganger');
          seen['i:' + inp.name] = true;
          inputs.push(inp);
        }
        continue;
      }
      var cm = line.match(CELL_RE);
      // CELL_RE matcher også "#%"-løse linjer med %% i seg? Nei: krever %% etter valgfri marker.
      if (cm && /%%/.test(line.split('%%')[0] + '%%')) {
        cur = parseCellHeader(cm[1]);
        cur.code = '';
        cells.push(cur);
        continue;
      }
      if (!cur) {
        if (line.trim()) { cur = { name: '', wide: false, row: null, tab: null, deps: null, code: line }; cells.push(cur); }
      } else {
        cur.code += (cur.code ? '\n' : '') + line;
      }
    }
    cells = cells.filter(function (c) { return (c.code || '').trim(); });
    return { title: title, description: description, inputs: inputs, setupCode: setupCode, cells: cells, errors: errors };
  };

  // Trygg serialisering (spec §5): tall som tall, bool som modus-literal,
  // strenger JSON-enkodet (gyldig i både python og R).
  D.assignStatement = function (mode, name, value) {
    var lit;
    if (typeof value === 'number') lit = String(value);
    else if (typeof value === 'boolean') lit = (mode === 'r') ? (value ? 'TRUE' : 'FALSE') : (value ? 'True' : 'False');
    else lit = JSON.stringify(String(value));
    return (mode === 'r') ? (name + ' <- ' + lit) : (name + ' = ' + lit);
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = D;
  global.Dashboard = D;
})(typeof window !== 'undefined' ? window : globalThis);
```

Note: the CELL_RE double-check line in `parse` is defensive scaffolding from drafting — during implementation, verify CELL_RE only matches lines whose first non-space content is a comment marker + `%%` (write it as one regex; drop the redundant `/%%/` re-test if the regex is right).

- [ ] **Step 4: Run tests** — `node --test tests/js/dashboard.test.js` → PASS.
- [ ] **Step 5: Commit** — `git add js/dashboard.js tests/js/dashboard.test.js && git commit -m "feat(dashboard): parse #input/#%% directives + safe assignment statements"`

---

### Task 2: invalidation — `planReruns` (pure)

**Files:**
- Modify: `js/dashboard.js`
- Test: `tests/js/dashboard.test.js` (append)

**Interfaces:**
- Produces: `Dashboard.planReruns(cells, changedVars, mode) → number[]` (cell indexes to re-run, in order). Conservative per spec §3.1: text-mention + transitive assigned-name propagation; opaque cell → that cell and everything after re-runs; `deps` overrides.

- [ ] **Step 1: Write failing tests**

```js
test('planReruns: mention, transitive, deps override, opaque fallback', () => {
  const cells = [
    { name: 'a', deps: null, code: 'sub = df[df.cause == cause]\nprint(sub)' },
    { name: 'b', deps: null, code: 'print(sub)' },                  // transitive via sub
    { name: 'c', deps: null, code: 'print(year)' },
    { name: 'd', deps: ['year'], code: 'print("whatever cause")' }, // deps overrides text
  ];
  assert.deepEqual(D.planReruns(cells, ['cause'], 'python'), [0, 1]);
  assert.deepEqual(D.planReruns(cells, ['year'], 'python'), [2, 3]);
  // opaque: globals() in cell 1 → 1 and everything after
  const op = [
    { name: 'a', deps: null, code: 'x = year' },
    { name: 'b', deps: null, code: 'globals()["y"] = 1' },
    { name: 'c', deps: null, code: 'print(1)' },
  ];
  assert.deepEqual(D.planReruns(op, ['year'], 'python'), [0, 1, 2]);
  // r assignment forms
  const rc = [
    { name: 'a', deps: null, code: 'sub <- df[df$cause == cause,]' },
    { name: 'b', deps: null, code: 'plot(sub)' },
  ];
  assert.deepEqual(D.planReruns(rc, ['cause'], 'r'), [0, 1]);
});
```

- [ ] **Step 2: Run to verify fail** — FAIL (`planReruns is not a function`).

- [ ] **Step 3: Implement** (insert before the export lines)

```js
  // ── Invalidering (spec §3.1): konservativ tekstanalyse ────────────────────
  var OPAQUE = {
    python: /\b(exec|eval|globals|locals|__import__)\s*\(/,
    r: /\b(assign|eval|get|source)\s*\(/
  };
  function assignedNames(code, mode) {
    var names = {}, m;
    if (mode === 'r') {
      var rre = /(?:^|[\n;({])\s*([A-Za-z_.][\w.]*)\s*(?:<<?-|=(?!=))/g;
      while ((m = rre.exec(code)) !== null) names[m[1]] = true;
      var arrow = /(?:->>?)\s*([A-Za-z_.][\w.]*)/g;
      while ((m = arrow.exec(code)) !== null) names[m[1]] = true;
    } else {
      var pre = /^[ \t]*([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*(?:=(?!=)|\+=|-=|\*=|\/=)/gm;
      while ((m = pre.exec(code)) !== null) {
        m[1].split(',').forEach(function (n) { names[n.trim()] = true; });
      }
      var dre = /^[ \t]*(?:def|class)\s+([A-Za-z_]\w*)/gm;
      while ((m = dre.exec(code)) !== null) names[m[1]] = true;
      var fre = /^[ \t]*for\s+([A-Za-z_]\w*)/gm;
      while ((m = fre.exec(code)) !== null) names[m[1]] = true;
    }
    return Object.keys(names);
  }
  function mentionsAny(code, vars) {
    for (var i = 0; i < vars.length; i++) {
      if (new RegExp('\\b' + vars[i].replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b').test(code)) return true;
    }
    return false;
  }
  D.planReruns = function (cells, changedVars, mode) {
    var dirty = {}, out = [], opaqueHit = false;
    changedVars.forEach(function (v) { dirty[v] = true; });
    for (var i = 0; i < cells.length; i++) {
      var c = cells[i], rerun;
      var dirtyList = Object.keys(dirty);
      if (opaqueHit) rerun = true;
      else if (c.deps) rerun = c.deps.some(function (d) { return dirty[d]; });
      else if (OPAQUE[mode === 'r' ? 'r' : 'python'].test(c.code) && mentionsAny(c.code, dirtyList)) { rerun = true; opaqueHit = true; }
      else rerun = mentionsAny(c.code, dirtyList);
      if (rerun) {
        out.push(i);
        assignedNames(c.code, mode).forEach(function (n) { dirty[n] = true; });
        if (!opaqueHit && !c.deps && OPAQUE[mode === 'r' ? 'r' : 'python'].test(c.code)) opaqueHit = true;
      }
    }
    return out;
  };
```

Care: the opaque rule per spec is "cannot be confident → fall back to everything below". The implementation above: once an opaque cell *re-runs*, everything after re-runs. An opaque cell that doesn't mention any dirty name and has no deps: we cannot know it's unaffected — the test expects `[0,1,2]` for that shape only when it mentions… adjust during implementation so the test in Step 1 passes exactly: an opaque cell re-runs whenever any earlier cell re-ran OR it mentions a dirty name; after an opaque cell re-runs, all subsequent cells re-run. Verify against the test table; the test is the contract.

- [ ] **Step 4: Run tests** — PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(dashboard): conservative cell invalidation (planReruns)"`

---

### Task 3: layout grouping + debounced run queue (pure)

**Files:**
- Modify: `js/dashboard.js`
- Test: `tests/js/dashboard.test.js` (append)

**Interfaces:**
- Produces: `Dashboard.groupLayout(cells) → [{kind:'card', index}|{kind:'row', name, indexes}|{kind:'tabs', tabs:[{label, indexes}]}]`
- Produces: `Dashboard.createQueue(execute, delayMs) → {change(name, value)}` — collects changes `delayMs`, max one pending batch, sequential execution (spec §3 debounce).

- [ ] **Step 1: Write failing tests**

```js
test('groupLayout: cards, rows, tab sets, tab break', () => {
  const cells = [
    { name: 'a', row: null, tab: null }, { name: 'b', row: 'kpi', tab: null },
    { name: 'c', row: 'kpi', tab: null }, { name: 'd', row: null, tab: 'X' },
    { name: 'e', row: null, tab: 'Y' }, { name: 'f', row: null, tab: null },
    { name: 'g', row: null, tab: 'Z' },
  ];
  const g = D.groupLayout(cells);
  assert.deepEqual(g.map(x => x.kind), ['card', 'row', 'tabs', 'card', 'tabs']);
  assert.deepEqual(g[1].indexes, [1, 2]);
  assert.deepEqual(g[2].tabs.map(t => t.label), ['X', 'Y']);
});

test('createQueue: coalesces, one pending batch, sequential', async () => {
  const runs = [];
  let resolveRun;
  const q = D.createQueue(batch => new Promise(res => { runs.push(batch); resolveRun = res; }), 1);
  q.change('year', 2000); q.change('year', 2001);
  await new Promise(r => setTimeout(r, 15));
  assert.deepEqual(runs, [{ year: 2001 }]);            // coalesced before run
  q.change('year', 2005); q.change('cause', 'K');      // arrives while running
  await new Promise(r => setTimeout(r, 15));
  assert.equal(runs.length, 1);                        // still waiting on run 1
  resolveRun();
  await new Promise(r => setTimeout(r, 15));
  assert.deepEqual(runs[1], { year: 2005, cause: 'K' });
});
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement**

```js
  D.groupLayout = function (cells) {
    var out = [], i = 0;
    while (i < cells.length) {
      var c = cells[i];
      if (c.row) {
        var idx = [i], name = c.row;
        while (i + 1 < cells.length && cells[i + 1].row === name) idx.push(++i);
        out.push({ kind: 'row', name: name, indexes: idx });
      } else if (c.tab) {
        var tabs = [], curLabel = null;
        while (i < cells.length && cells[i].tab) {
          if (cells[i].tab !== curLabel) { curLabel = cells[i].tab; tabs.push({ label: curLabel, indexes: [] }); }
          tabs[tabs.length - 1].indexes.push(i); i++;
        }
        i--; out.push({ kind: 'tabs', tabs: tabs });
      } else out.push({ kind: 'card', index: i });
      i++;
    }
    return out;
  };

  // Debounce + maks én ventende batch (spec §3): siste verdier vinner,
  // kjøringer er strengt sekvensielle.
  D.createQueue = function (execute, delayMs) {
    var pending = null, timer = null, running = false;
    function flush() {
      timer = null;
      if (running || !pending) return;
      var batch = pending; pending = null; running = true;
      Promise.resolve(execute(batch))['catch'](function () {}).then(function () {
        running = false;
        if (pending && !timer) flush();
      });
    }
    return { change: function (name, value) {
      pending = pending || {};
      pending[name] = value;
      if (timer) clearTimeout(timer);
      timer = setTimeout(flush, delayMs);
    } };
  };
```

- [ ] **Step 4: Run tests** — PASS. Also run full suite: `node --test tests/js/` → all PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(dashboard): layout grouping + debounced single-pending run queue"`

---

### Task 4: names in `notebook-links.js` (pure)

**Files:**
- Modify: `js/notebook-links.js`
- Test: `tests/js/notebook-links.test.js` (append)

**Interfaces:**
- Produces: `classifyHash('#dodsarsaker') → {action:'name', kind:'name', name:'dodsarsaker'}`;
  `NL.classifyNameValue(value) → {action:'output', kind:'raw'|'dotted', …}|null`.

- [ ] **Step 1: Write failing tests**

```js
test('classifyHash: single lowercase token → name lookup', () => {
  assert.deepEqual(NL.classifyHash('#dodsarsaker'), { action: 'name', kind: 'name', name: 'dodsarsaker' });
  assert.deepEqual(NL.classifyHash('#kommune-helse'), { action: 'name', kind: 'name', name: 'kommune-helse' });
  assert.equal(NL.classifyHash('#Has.Dots.x.py').action, 'open');   // dotted untouched
  assert.equal(NL.classifyHash('#s=abc').kind, 'share');            // share untouched
  assert.equal(NL.classifyHash('#UPPER'), null);                    // not a name, not dotted
});

test('classifyNameValue: url and dotted values', () => {
  const r1 = NL.classifyNameValue('https://x.example/a.py');
  assert.deepEqual(r1, { action: 'output', kind: 'raw', raw: 'https://x.example/a.py' });
  const r2 = NL.classifyNameValue('hans.demo.analyser.dod.py');
  assert.equal(r2.action, 'output');
  assert.equal(r2.kind, 'dotted');
  assert.ok(r2.urls[0].includes('raw.githubusercontent.com/hans/demo/main/analyser/dod.py'));
  assert.equal(NL.classifyNameValue('ugyldig'), null);
});
```

- [ ] **Step 2: Run to verify fail** — `node --test tests/js/notebook-links.test.js`.

- [ ] **Step 3: Implement.** In `NL.classifyHash`, after the `mRaw` block and before the dotted-shorthand block, insert:

```js
    // Navneregister (dashboard-spec §4): ett token, små bokstaver/siffer/
    // bindestrek, ingen punktum → slås opp i names.json av openFromFragment.
    if (/^[a-z0-9][a-z0-9-]*$/.test(h)) return { action: 'name', kind: 'name', name: h };
```

After `NL.classifyHash`, add:

```js
  // Registerverdi (streng fra names.json) → samme form som classifyHash,
  // alltid med output-intensjon (mottakere skal se resultat, ikke editor).
  NL.classifyNameValue = function (value) {
    var v = String(value == null ? '' : value).trim();
    if (!v) return null;
    if (/^https?:\/\//i.test(v)) return { action: 'output', kind: 'raw', raw: v };
    var urls = NL.resolveDotted(v);
    if (!urls) return null;
    return { action: 'output', kind: 'dotted', urls: urls };
  };
```

- [ ] **Step 4: Run tests** — PASS (including all pre-existing notebook-links tests).
- [ ] **Step 5: Commit** — `git commit -am "feat(names): classifyHash name case + classifyNameValue"`

---

### Task 5: `js/names.js` — registry fetch + fallbacks; bundled `names.json`

**Files:**
- Create: `js/names.js`, `names.json`
- Test: `tests/js/names.test.js`

**Interfaces:**
- Produces: `DashboardNames.pick(registry, name) → string|null` (pure);
  `DashboardNames.lookup(name) → Promise<string|null>` (fetch remote → localStorage cache → bundled `/names.json`);
  `DashboardNames.showNameError(name, t)` (banner, browser-only).

- [ ] **Step 1: Write failing tests**

```js
// tests/js/names.test.js
const test = require('node:test');
const assert = require('node:assert');
const N = require('../../js/names.js');

test('pick: string values, object values, miss', () => {
  const reg = { a: 'hans.demo.x.py', b: { url: 'https://x.example/b.py' }, c: 42 };
  assert.equal(N.pick(reg, 'a'), 'hans.demo.x.py');
  assert.equal(N.pick(reg, 'b'), 'https://x.example/b.py');
  assert.equal(N.pick(reg, 'c'), null);   // unknown shape → miss, not crash
  assert.equal(N.pick(reg, 'nope'), null);
  assert.equal(N.pick(null, 'a'), null);
});
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement**

```js
// js/names.js — navneregister-oppslag (dashboard-spec §4). Rene pick() +
// tynn lookup() med tre kilder: remote registry → localStorage-cache →
// medfølgende names.json. Ingen avhengigheter til resten av appen.
(function (global) {
  'use strict';
  var N = {};
  N.REGISTRY_URL = 'https://raw.githubusercontent.com/hmelberg/dashstatlink/main/names.json';
  var LS_KEY = 'm2py_names_cache';

  N.pick = function (registry, name) {
    if (!registry || typeof registry !== 'object') return null;
    var v = registry[name];
    if (typeof v === 'string') return v;
    if (v && typeof v === 'object' && typeof v.url === 'string') return v.url;
    return null;
  };

  N.lookup = async function (name) {
    var reg = null;
    try {
      var res = await fetch(N.REGISTRY_URL, { cache: 'no-cache' });
      if (res.ok) {
        reg = await res.json();
        try { localStorage.setItem(LS_KEY, JSON.stringify(reg)); } catch (_) {}
      }
    } catch (_) {}
    if (!reg) { try { reg = JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch (_) {} }
    if (!reg) { try { var r2 = await fetch('names.json'); if (r2.ok) reg = await r2.json(); } catch (_) {} }
    return N.pick(reg, name);
  };

  // Vennlig feilbanner (spec §4, ukjent navn) — selvforsynt DOM, ingen modal.
  N.showNameError = function (name, t) {
    if (typeof document === 'undefined') return;
    var tf = t || function (s) { return s; };
    var bar = document.createElement('div');
    bar.className = 'names-error-banner';
    bar.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:9999;padding:10px 16px;'
      + 'background:#b23;color:#fff;font:14px system-ui;display:flex;justify-content:space-between';
    var span = document.createElement('span');
    span.textContent = tf('Fant ikke navnet i navneregisteret:') + ' «' + name + '»';
    var x = document.createElement('button');
    x.textContent = '×';
    x.style.cssText = 'background:none;border:none;color:#fff;font-size:16px;cursor:pointer';
    x.onclick = function () { bar.remove(); };
    bar.appendChild(span); bar.appendChild(x);
    document.body.appendChild(bar);
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = N;
  global.DashboardNames = N;
})(typeof window !== 'undefined' ? window : globalThis);
```

Create `names.json` at repo root (bundled fallback + local testing; the example path is finalized in Task 9):

```json
{
  "demo": "hansmelberg.safestat.examples.dashboard-demo.py"
}
```

- [ ] **Step 4: Run tests** — PASS.
- [ ] **Step 5: Commit** — `git add js/names.js names.json tests/js/names.test.js && git commit -m "feat(names): registry lookup with cache + bundled fallback"`

---

### Task 6: skeleton DOM + `css/dashboard.css`

**Files:**
- Modify: `js/dashboard.js` (browser-only section, guarded by `typeof document !== 'undefined'`)
- Create: `css/dashboard.css`

**Interfaces:**
- Produces: `Dashboard.mountSkeleton(parsed, ui)` — `ui = {container, hideNode, t, onShowCode}`; renders header/controls/grid/footer into a `div.dash-root` inserted before `ui.hideNode` (which gets `hidden`), controls disabled until `start()`. Stores internal state (`_state`) with per-cell `{card, body}` nodes.
- Produces: `Dashboard.unmount()` — removes `.dash-root`, unhides `hideNode`, calls `ui.onShowCode()`.
- Produces: `Dashboard.showSetupError(message)` — replaces grid with one error card + "Åpne i editor" button (calls `unmount`).
- Produces: `Dashboard.setProgress(text)` — footer progress line.

Widget DOM per input: slider → `<label>` + `<input type=range>` + live value `<output>`; dropdown → `<select>`; checkbox → `<input type=checkbox>`. Each control calls `Dashboard._onChange(name, coercedValue)` (wired to the queue in Task 7; before `start()`, changes only update the stored value). All author strings via `textContent`.

Layout rendering follows `groupLayout`: `card` → `.dash-card` (`.dash-card--wide` if wide), `row` → `.dash-row` wrapper with cards `flex:1`, `tabs` → `.dash-tabs` with a button bar and one panel per tab (hidden panels get `hidden`; tab click calls `Dashboard._onTabShown(indexes)` for lazy runs).

- [ ] **Step 1: Implement DOM section** (no node test — browser-facing; the pure `groupLayout` it consumes is already tested). Cards start with `.dash-card--loading` (CSS shimmer).

- [ ] **Step 2: Create `css/dashboard.css`** — builds on existing `app.css` custom properties (inspect `:root` in `app.css` and reuse its color/font vars; fall back to sensible literals where no var exists):

```css
/* dashboard view (spec 2026-07-09-dashboard-design.md §3) */
.dash-root { max-width: 1100px; margin: 0 auto; padding: 16px; }
.dash-header h1 { margin: 0 0 4px; font-size: 1.5rem; }
.dash-header p { margin: 0 0 12px; opacity: .75; }
.dash-controls { display: flex; flex-wrap: wrap; gap: 16px; align-items: end;
  padding: 12px; border: 1px solid var(--border-color, #ddd); border-radius: 8px; margin-bottom: 16px; }
.dash-controls--loading { opacity: .5; pointer-events: none; }
.dash-widget { display: flex; flex-direction: column; gap: 4px; font-size: .85rem; }
.dash-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.dash-card { border: 1px solid var(--border-color, #ddd); border-radius: 8px; padding: 12px; min-height: 80px; overflow-x: auto; }
.dash-card h3 { margin: 0 0 8px; font-size: 1rem; }
.dash-card--wide, .dash-row, .dash-tabs { grid-column: 1 / -1; }
.dash-row { display: flex; gap: 16px; }
.dash-row .dash-card { flex: 1; min-width: 0; }
.dash-tabs .dash-tabbar { display: flex; gap: 4px; margin-bottom: 8px; }
.dash-tabs .dash-tabbar button { padding: 6px 14px; border: 1px solid var(--border-color, #ddd);
  border-radius: 6px 6px 0 0; background: none; cursor: pointer; }
.dash-tabs .dash-tabbar button[aria-selected="true"] { font-weight: 600; border-bottom-color: transparent; }
.dash-card--loading .dash-card-body { min-height: 40px; border-radius: 4px;
  background: linear-gradient(90deg, rgba(127,127,127,.10), rgba(127,127,127,.22), rgba(127,127,127,.10));
  background-size: 200% 100%; animation: dashShimmer 1.2s infinite; }
@keyframes dashShimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
.dash-card--running { opacity: .55; }
.dash-card--stale::after { content: attr(data-stale-label); display: block; font-size: .75rem; opacity: .7; margin-top: 6px; }
.dash-card--stale { opacity: .55; }
.dash-card img, .dash-card canvas { max-width: 100%; height: auto; }
.dash-footer { margin-top: 16px; display: flex; justify-content: space-between; font-size: .85rem; opacity: .8; }
.dash-footer a { cursor: pointer; text-decoration: underline; }
@media (max-width: 700px) {
  .dash-grid { grid-template-columns: 1fr; }
  .dash-row { flex-direction: column; }
  .dash-controls { align-items: stretch; flex-direction: column; }
}
```

- [ ] **Step 3: Verify no test regressions** — `node --test tests/js/` (the DOM section must not break `require('js/dashboard.js')` in node: guard every DOM reference behind `typeof document !== 'undefined'` or inside functions never called by tests).
- [ ] **Step 4: Commit** — `git add -A && git commit -m "feat(dashboard): skeleton DOM + grid/tabs/rows CSS"`

---

### Task 7: orchestration — `Dashboard.start(ctx)`

**Files:**
- Modify: `js/dashboard.js`

**Interfaces:**
- Consumes: `ctx = {mode: 'python'|'r', run(code) → Promise<{kind, text?|parts?, error}>, renderOutput(result, node), t}` (built in Task 8).
- Produces: `Dashboard.start(ctx) → Promise<void>`; internal `Dashboard._onChange` becomes queue-wired.

Behavior (spec §3):

1. Assign all widget defaults in one `ctx.run` (joined `assignStatement` lines).
2. Run visible cells in document order: card → `--running`, `ctx.run(cell.code)`, `ctx.renderOutput(result, body)`, clear loading/running. Cells inside non-active tabs: mark `cell._dirty = true`, skip (lazy).
3. Enable controls; `setProgress('')`; create `queue = createQueue(executeBatch, 250)`; `_onChange` routes to `queue.change`.
4. `executeBatch(batch)`: one `ctx.run` with the batch assignments → `planReruns(cells, keys, mode)` → visible cells re-run in order (`--running` while waiting); hidden-tab cells in the set only get `_dirty = true`. Cells after a *failed* cell in the same batch (per the rerun set) get `--stale` + `data-stale-label = t('Utdatert')`.
5. `_onTabShown(indexes)`: any `_dirty` cell runs now (sequentially, via the same single-flight discipline — simplest: `queue.change('__tab__' + Date.now(), true)` is WRONG; instead expose an internal `runDirty(indexes)` that awaits the queue idle: keep a module-level `chain = chain.then(...)` promise so tab-runs and batch-runs serialize on one chain).
6. Cell error → `ctx.renderOutput` renders `pre.error` inside the card (result.error is set); dashboard continues.

Single-flight rule: ALL executions (initial fill, batches, lazy tab fills) append to one promise chain — never two `ctx.run` in flight.

- [ ] **Step 1: Implement** per above.
- [ ] **Step 2: Run full test suite** — `node --test tests/js/` → PASS (orchestration itself is browser-verified in Task 9).
- [ ] **Step 3: Commit** — `git commit -am "feat(dashboard): start/orchestration with single-flight run chain"`

---

### Task 8: index.html integration — activation, ctx, R-output refactor

**Files:**
- Modify: `index.html`

Four edits, each anchored to a unique existing string:

- [ ] **Step 1: Includes.** Next to `<script src="widgets/forklar-widgets.js"></script>` (index.html:827) add:

```html
  <script src="js/names.js"></script>
  <script src="js/dashboard.js"></script>
```

and next to the `app.css` `<link>` add `<link rel="stylesheet" href="css/dashboard.css">`.

- [ ] **Step 2: `buildROutputNodes` refactor.** In `renderROutputParts` (anchor: `function renderROutputParts(outputParts) {`, index.html:7932): extract the whole per-part `forEach` body into a new `function buildROutputNodes(outputParts)` that appends to a `DocumentFragment` and returns it (including the `(ingen output)` empty case as a fragment). `renderROutputParts` becomes:

```js
    function renderROutputParts(outputParts) {
      purgePlots(outputArea);
      outputArea.innerHTML = '';
      outputArea.appendChild(buildROutputNodes(outputParts));
    }
```

Verify R mode still renders identically (manual run of an R plot script).

- [ ] **Step 3: Activation branch.** In the `btnRun` click handler, immediately after the breakpoint truncation block (anchor: `const scriptTrim = effectiveScript.trim();` — insert BEFORE that line so the empty-setup guard below controls what runs):

```js
      // Dashboard-visning (spec 2026-07-09-dashboard-design.md): monter
      // skjelettet FØR runtime laster, og la pipelinen kjøre KUN setup-sonen
      // (alt over første #input) — samme trunkeringstriks som breakpoints
      // over. Cellene kjøres inkrementelt via buildDashboardCtx() når denne
      // kjøringen har satt seg (se hooken i finally-blokken).
      dashboardPendingParsed = null;
      if (window.Dashboard && (activeEditorMode === 'python' || activeEditorMode === 'r')) {
        var _dOpts = extractScriptOptions(effectiveScript);
        if (String(_dOpts.view || '').toLowerCase() === 'dashboard') {
          var _dp = window.Dashboard.parse(effectiveScript);
          window.Dashboard.mountSkeleton(_dp, {
            container: outputArea.parentNode, hideNode: outputArea, t: t,
            onShowCode: function () { if (window.mdSetInputHidden) window.mdSetInputHidden(false); }
          });
          window.Dashboard.setProgress(t('Laster kjøremiljø og data …'));
          if (window.mdSetInputHidden) window.mdSetInputHidden(true);
          dashboardPendingParsed = _dp;
          // Tom setup-sone må fortsatt gi en gyldig pipeline-kjøring (den
          // etablerer _g/_exec_pyodide_block for python-chunkene).
          effectiveScript = _dp.setupCode.trim() ? _dp.setupCode
            : (activeEditorMode === 'r' ? 'invisible(0)' : 'pass');
        }
      }
```

Declare `var dashboardPendingParsed = null;` next to `scriptRunInProgress`'s declaration (find `let scriptRunInProgress` / `var scriptRunInProgress`).

- [ ] **Step 4: End-of-run hook.** In the same click handler's `finally` block (locate it: the block that sets `scriptRunInProgress = false` and `setRunButtonsUi('idle')` at the end of the handler), append:

```js
        if (dashboardPendingParsed) {
          var _dparsed = dashboardPendingParsed;
          dashboardPendingParsed = null;
          var _setupErrNode = outputArea.querySelector('pre.error');   // ai-chat.js-presedensen
          if (_setupErrNode) {
            window.Dashboard.showSetupError(_setupErrNode.textContent);
          } else {
            window.Dashboard.start(buildDashboardCtx()).catch(function (e) {
              window.Dashboard.showSetupError((e && e.message) || String(e));
            });
          }
        }
```

- [ ] **Step 5: `buildDashboardCtx`.** Add near the forklar chunk helpers (anchor: place directly above `async function forklarRunOnePyodideBlock`):

```js
    // Dashboard-kontrakten (spec §2): kjør en chunk i vedvarende scope og
    // returner resultatet — python via _exec_pyodide_block/_g (samme som
    // forklar), R via shelter.captureR. renderOutput gjenbruker appens
    // output-byggere så kort ser identiske ut med vanlig visning.
    function buildDashboardCtx() {
      var mode = (activeEditorMode === 'r') ? 'r' : 'python';
      async function runPy(code) {
        var py = await loadPyodideAndM2py();
        var buf = '';
        if (typeof py.setStdout === 'function') py.setStdout({ batched: function (s) { buf += s + '\n'; } });
        if (typeof py.setStderr === 'function') py.setStderr({ batched: function (s) { buf += s + '\n'; } });
        try {
          await py.runPythonAsync(
            'import json\n' +
            'try:\n    _g\nexcept NameError:\n    _g = globals()\n' +
            '_st = json.loads(' + JSON.stringify(JSON.stringify(code)) + ')\n' +
            '_exec_pyodide_block(_st, _g)');
          await new Promise(function (r) { setTimeout(r, 0); });
          return { kind: 'py', text: buf, error: null };
        } catch (e) {
          return { kind: 'py', text: buf, error: (e && e.message) || String(e) };
        }
      }
      async function runR(code) {
        try {
          if (!webRReady) await loadWebR();
          if (!webRShelter) webRShelter = await new webR.Shelter();
          var captured = await webRShelter.captureR(code, { withAutoprint: true });
          var parts = [];
          var lines = (captured.output || []).filter(function (o) { return o.type === 'stdout'; })
            .map(function (o) { return String(o.data); }).join('\n');
          var errLines = (captured.output || []).filter(function (o) { return o.type === 'stderr'; })
            .map(function (o) { return String(o.data); }).join('\n');
          if (lines.trim()) parts.push({ type: 'text', text: lines, className: 'm2py-stmt-output' });
          (captured.images || []).forEach(function (bm) { parts.push({ type: 'image', bitmap: bm }); });
          return { kind: 'r', parts: parts, error: /error/i.test(errLines) ? errLines : null };
        } catch (e) {
          return { kind: 'r', parts: [], error: (e && e.message) || String(e) };
        }
      }
      function renderInto(result, node) {
        purgePlots(node);
        node.innerHTML = '';
        if (result.kind === 'r') node.appendChild(buildROutputNodes(result.parts || []));
        else node.appendChild(buildOutputNodes(result.text || '', false, false));
        if (result.error) {
          var pre = document.createElement('pre');
          pre.className = 'error';
          pre.textContent = result.error;
          node.appendChild(pre);
        }
      }
      return { mode: mode, run: (mode === 'r') ? runR : runPy, renderOutput: renderInto, t: t };
    }
```

During implementation, verify `buildOutputNodes`'s exact signature/defaults (anchor: `function renderOutput(raw, asHtml, suppress)` at index.html:6402 → `buildOutputNodes(raw, asHtml, suppress)`) and match how forklar calls it. Verify R error semantics against `forklarRunOneRBlock`'s handling (index.html:10224+) and mirror it.

- [ ] **Step 6: Manual verification** (see Task 9 script). Run node suite: `node --test tests/js/` → PASS.
- [ ] **Step 7: Commit** — `git commit -am "feat(dashboard): index.html activation, ctx, R output builder refactor"`

---

### Task 9: name-lookup wiring + example script + end-to-end verification

**Files:**
- Modify: `js/github-storage.js` (in `openFromFragment`, anchor index `js/github-storage.js:162`)
- Create: `examples/dashboard-demo.py`
- Modify: `names.json` (point `demo` at the final raw URL of the example)

- [ ] **Step 1: Wire name case in `openFromFragment`.** After `const cls = window.NotebookLinks && window.NotebookLinks.classifyHash(location.hash);` and the share guard, insert:

```js
        let effCls = cls;
        if (cls.action === 'name') {
          const target = window.DashboardNames ? await window.DashboardNames.lookup(cls.name) : null;
          const ncls = target && window.NotebookLinks.classifyNameValue(target);
          if (!ncls) {
            if (window.DashboardNames) window.DashboardNames.showNameError(cls.name, window.t);
            return;
          }
          effCls = ncls;
        }
```

and use `effCls` instead of `cls` in the rest of the function. (Check how `t` is reachable in github-storage.js — it uses `T(...)`; pass that.)

- [ ] **Step 2: Example script** `examples/dashboard-demo.py` (also serves as the manual test; uses a small open CSV that already works in existing examples — pick one from `examples/` during implementation):

```python
#options.view = dashboard
#options.title = "Dashboard-demo"
#options.description = "Interaktiv demo av dashboard-visningen"
# load https://ourworldindata.org/grapher/co2.csv as co2   # byttes til en kjent-god kilde fra examples/

#input year = slider(1990, 2020, step=5, default=2010)
#input logscale = checkbox(default=False, label="Log-skala")

#%% Utvikling, wide
sub = co2[co2.Year <= year]
print(sub.tail())

#%% Antall rader, row=kpi
print(len(sub))

#%% Siste år, row=kpi
print(sub.Year.max())
```

- [ ] **Step 3: End-to-end verification** (local server, e.g. `python3 -m http.server`):
  1. Open `index.html`, paste the example, Kjør → skeleton appears instantly, cards fill, editor hidden.
  2. Move the slider → only affected cards re-run (watch `--running` class), values update.
  3. "Vis koden" → editor returns with the script intact.
  4. Introduce an error in the setup zone → single error card + "Åpne i editor".
  5. `#demo` in the URL hash (with `names.json` served locally) → dashboard loads via name (safestat gate prompt appears first — accept).
  6. R-mode smoke: small R dashboard (slider + `plot`) → cards render plots.
  7. Isolation: comment out the `dashboard.js` script tag → normal scripts and forklar behave exactly as before.
- [ ] **Step 4: Run full suite** — `node --test tests/js/` → PASS.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(dashboard): name wiring, example, e2e verified"`

---

## Self-review checklist (run after Task 9)

1. Spec coverage: §1 syntax → Task 1; §2 contract → Tasks 6–8; §3 execution/debounce/errors → Tasks 3, 7, 8; §3.1 invalidation → Task 2; §4 names → Tasks 4, 5, 9; §5 security (serialization, textContent, no free-text) → Tasks 1, 6; §6 testing/isolation → every task + Task 9; §7 exclusions respected.
2. The `dashstatlink` registry repo was created and published (hmelberg/dashstatlink).
3. OpenStat port is a separate follow-up (copy the same files + integration lines).
