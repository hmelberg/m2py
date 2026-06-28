# Stage 1 — Mode Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the scattered `activeEditorMode === '…'` editor-level dispatch in `index.html` with one inline mode registry, with zero behavior change for microdata/python/r.

**Architecture:** Add an inline `modeRegistry` (map of `id → ModePlugin`) plus a `currentMode()` helper near `switchEditorMode`. Each task adds one plugin field and rewires the matching call-site together (no dormant duplication). The fragile shared run pipeline is left intact; only its R short-circuit and Python pip-prelude move behind per-plugin `runSelf` / `preRun` hooks.

**Tech Stack:** Static HTML/JS (no build, classic scripts), Pyodide, webR. No front-end unit-test harness.

## Global Constraints

- **Zero behavior change.** The three existing modes must highlight, autocomplete (Tab), run, and translate identically. This is a refactor of *where dispatch lives*, never *what it does*.
- **Inline only.** Registry + plugins live inline in `index.html` next to `switchEditorMode`. Do NOT create a `js/modes.js`. No build step, no `type="module"`, no `window.*` surface change.
- **Category-2 sites stay.** Per-segment `seg.kind` / `mode` params in hybrid-script and forklar parsing are a different axis — do NOT touch them. Only route the editor-level `activeEditorMode` dispatch sites named in the tasks.
- **Define + consume together.** Each task adds the plugin field(s) it needs AND rewires the call-site in the same task. No field is added before the task that uses it (exception: T1 seeds `id`+`label`).
- **Preserve translate behavior verbatim.** Translate/Oversett wiring is NOT uniform across modes (e.g. `oversettBtn` is hidden in microdata via `updateModeButtonsUi`, yet its handler still contains a microdata→Python branch). Reproduce exactly; do not "fix".
- Front-end verification = structural greps + manual browser checks (engine `pytest` is unaffected; run it once at the end as a no-regression sanity check).

### Local verification setup (used by every task)

```bash
cd /Users/hom/Documents/GitHub/m2py
python3 -m http.server 8000   # open http://localhost:8000/, watch the Console
```
"No console errors" = no `ReferenceError`/`TypeError`/`SyntaxError` after load. (AI send failing at the backend is unrelated — see the netlify-dev memory.)

---

### Task 1: Introduce `modeRegistry` + `currentMode()`, route the mode label

**Files:**
- Modify: `index.html` — add registry block immediately above `function switchEditorMode` (the `// ── Editor mode switching ──` comment); modify `updateModeButtonsUi`.

**Interfaces:**
- Produces: global `modeRegistry` (object `{ microdata, python, r }`), each value a `ModePlugin` with at least `{ id, label }`; helper `function currentMode()` returning `modeRegistry[activeEditorMode]`. Later tasks add fields `hlConfig`, `handleTab`, `translate`, `onActivate`, `runSelf`, `preRun`, `runDefault` to these same objects.

- [ ] **Step 1: Add the registry block** above `// ── Editor mode switching ──` / `function switchEditorMode`:

```js
// ── Mode registry ────────────────────────────────────────────────────────
// One plugin per editor language mode. Fields are added across Stage 1 tasks.
// Behavior-preserving: this only centralizes dispatch that was previously
// scattered as `activeEditorMode === '…'` branches.
const modeRegistry = {
  microdata: { id: 'microdata', label: 'Microdata' },
  python:    { id: 'python',    label: 'Python' },
  r:         { id: 'r',         label: 'R' },
};
function currentMode() {
  return modeRegistry[activeEditorMode] || modeRegistry.microdata;
}
```

- [ ] **Step 2: Route the label in `updateModeButtonsUi`.** Replace:

```js
      var labels = { microdata: 'Microdata', python: 'Python', r: 'R' };
      var lbl = document.getElementById('editorModeLabel');
      if (lbl) lbl.textContent = labels[activeEditorMode] || activeEditorMode;
```

with:

```js
      var lbl = document.getElementById('editorModeLabel');
      if (lbl) lbl.textContent = currentMode().label;
```

- [ ] **Step 3: Structural check**

```bash
grep -c 'const modeRegistry' index.html        # 1
grep -c 'function currentMode' index.html       # 1
grep -c "labels = { microdata:" index.html      # 0  (old label map gone)
```
Expected: `1`, `1`, `0`.

- [ ] **Step 4: Browser check** — load app; switch modes via the dropdown; the mode label (`editorModeLabel`) shows Microdata/Python/R correctly. In Console: `currentMode().id` returns the active mode. No console errors.

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "refactor(modes): add modeRegistry + currentMode(), route mode label

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Route lazy-load-on-switch through `plugin.onActivate`

**Files:**
- Modify: `index.html` — `modeRegistry.r`, `switchEditorMode`.

**Interfaces:**
- Consumes: `modeRegistry`, `currentMode()` (Task 1); existing `loadWebR`, `webRReady`, `webRLoading`.
- Produces: `modeRegistry.r.onActivate` (a `function()` run when switching INTO that mode).

- [ ] **Step 1: Add `onActivate` to the R plugin.** Change the `r:` entry in `modeRegistry`:

```js
  r: { id: 'r', label: 'R', onActivate: function () { if (!webRReady && !webRLoading) loadWebR(); } },
```

- [ ] **Step 2: Route it in `switchEditorMode`.** Replace:

```js
      // Trigger lazy WebR load when switching to R
      if (newMode === 'r' && !webRReady && !webRLoading) loadWebR();
```

with (note: `activeEditorMode` is already set to `newMode` above this line, so `currentMode()` is the new mode):

```js
      // Lazy-load this mode's runtime if it needs one (e.g. R → webR).
      var _ma = currentMode(); if (_ma.onActivate) _ma.onActivate();
```

- [ ] **Step 3: Structural check**

```bash
grep -c "newMode === 'r'" index.html   # 0
grep -c 'onActivate' index.html        # 2  (definition + call)
```
Expected: `0`, `2`.

- [ ] **Step 4: Browser check** — switch to R mode; webR begins loading (status/console shows webR init) exactly as before; switching to microdata/python does not trigger webR. No console errors.

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "refactor(modes): route webR lazy-load via plugin.onActivate

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Route syntax highlighting through `plugin.hlConfig`

**Files:**
- Modify: `index.html` — `modeRegistry` (add `hlConfig`), `renderScriptHighlight` (call-site), `highlightScriptPyR` (signature).

**Interfaces:**
- Consumes: `modeRegistry`, `currentMode()`; existing `PY_HL_CFG`, `R_HL_CFG`.
- Produces: `plugin.hlConfig` (an object for python/r, `null`/absent for microdata). `highlightScriptPyR(text, cfg)` now takes a config object instead of a mode string.

- [ ] **Step 1: Add `hlConfig` to plugins.** Update python and r entries so they read (keeping `onActivate` on r from Task 2):

```js
  python: { id: 'python', label: 'Python', hlConfig: PY_HL_CFG },
  r:      { id: 'r', label: 'R', hlConfig: R_HL_CFG, onActivate: function () { if (!webRReady && !webRLoading) loadWebR(); } },
```
(microdata stays without `hlConfig` — i.e. `undefined`.) NOTE: `PY_HL_CFG`/`R_HL_CFG` are defined later in the file than the registry; because the plugin objects are evaluated at script-parse time, confirm `PY_HL_CFG`/`R_HL_CFG` are declared (with `const`/`var`) ABOVE the `modeRegistry` block. If they are declared BELOW it, instead set `hlConfig` lazily: use a getter `get hlConfig() { return PY_HL_CFG; }` so it resolves at call time. Verify with `grep -n 'PY_HL_CFG' index.html` and compare line numbers to the registry block before choosing the direct vs getter form.

- [ ] **Step 2: Change `highlightScriptPyR` to take a config.** Replace its header line:

```js
    function highlightScriptPyR(text, mode) {
      var cfg = mode === 'r' ? R_HL_CFG : PY_HL_CFG;
```

with:

```js
    function highlightScriptPyR(text, cfg) {
```
(The rest of the function already uses `cfg`.)

- [ ] **Step 3: Route the call in `renderScriptHighlight`.** Replace:

```js
          } else if (mode === 'python' || mode === 'r') {
            html = highlightScriptPyR(text, mode);
```

with:

```js
          } else if (currentMode().hlConfig) {
            html = highlightScriptPyR(text, currentMode().hlConfig);
```
(`const mode = activeEditorMode;` a few lines above can stay; it is still used by the microdata branch's surrounding logic — verify it remains referenced, and if not, leave it to avoid scope churn.)

- [ ] **Step 4: Structural check**

```bash
grep -c "mode === 'python' || mode === 'r'" index.html   # 0
grep -c 'function highlightScriptPyR(text, cfg)' index.html  # 1
grep -c 'currentMode().hlConfig' index.html              # 2
```
Expected: `0`, `1`, `2`.

- [ ] **Step 5: Browser check** — in Python mode type `import pandas as pd` → keywords/strings colored as before; switch to R → R highlighting; microdata mode → microdata command highlighting unchanged. No console errors.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "refactor(modes): route syntax highlight via plugin.hlConfig

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Route Tab/autocomplete through `plugin.handleTab`

**Files:**
- Modify: `index.html` — extract the microdata Tab/autocomplete body into `microdataHandleTab(e)`; add `handleTab` to all three plugins; rewire the `keydown` Tab dispatch.

**Interfaces:**
- Consumes: `modeRegistry`, `currentMode()`; existing `handlePythonTab(e)`, `handleRTab(e)`, and the microdata autocomplete code currently inline in the `keydown` handler (`getWordBeforeCursor`, `autocompleteState`, `acceptSelection`, etc.).
- Produces: `function microdataHandleTab(e)`; `plugin.handleTab(e)` on all three modes.

- [ ] **Step 1: Extract the inline microdata Tab logic.** In the `scriptInput.addEventListener('keydown', …)` handler, the current Tab branch is:

```js
      if (e.key === 'Tab') {
        if (activeEditorMode === 'python') { handlePythonTab(e); return; }
        if (activeEditorMode === 'r')      { handleRTab(e);      return; }
        e.preventDefault();
        if (autocompleteState) {
          acceptSelection();
          return;
        }
        const { prefix, start, end } = getWordBeforeCursor();
        …  // (the rest of the microdata autocomplete block, through its end)
      }
```

Create a new top-level function `microdataHandleTab(e)` (place it next to `handlePythonTab`) containing exactly the microdata body — everything from `e.preventDefault();` through the end of the original Tab branch:

```js
    function microdataHandleTab(e) {
      e.preventDefault();
      if (autocompleteState) {
        acceptSelection();
        return;
      }
      const { prefix, start, end } = getWordBeforeCursor();
      …  // VERBATIM the remaining microdata autocomplete body
    }
```
Move the body unchanged (cut/paste). Do not alter logic.

- [ ] **Step 2: Add `handleTab` to plugins.** Update the three entries (keeping existing fields):

```js
  microdata: { id: 'microdata', label: 'Microdata', handleTab: microdataHandleTab },
  python:    { id: 'python', label: 'Python', hlConfig: PY_HL_CFG, handleTab: handlePythonTab },
  r:         { id: 'r', label: 'R', hlConfig: R_HL_CFG, onActivate: function () { if (!webRReady && !webRLoading) loadWebR(); }, handleTab: handleRTab },
```
(`handlePythonTab` / `handleRTab` / `microdataHandleTab` are function declarations, hoisted, so referencing them in the registry object is safe regardless of definition order.)

- [ ] **Step 3: Rewire the Tab dispatch.** The Tab branch becomes just:

```js
      if (e.key === 'Tab') {
        currentMode().handleTab(e);
        return;
      }
```

- [ ] **Step 4: Structural check**

```bash
grep -c 'function microdataHandleTab' index.html          # 1
grep -c "activeEditorMode === 'python') { handlePythonTab" index.html  # 0
grep -c 'currentMode().handleTab' index.html              # 1
```
Expected: `1`, `0`, `1`.

- [ ] **Step 5: Browser check** — microdata mode: type `tab` then a slash-command prefix → autocomplete list appears / accepts as before. Python mode: Tab indents/autocompletes as before. R mode: same. No console errors.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "refactor(modes): route Tab autocomplete via plugin.handleTab

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Route translate (button visibility, label, actions) through `plugin.translate`

**Files:**
- Modify: `index.html` — add `translate` to plugins; rewire `updateModeButtonsUi` (button visibility), `updateTranslateBtnLabel`, `translateAndSwitchToMicrodata`, and the `initOversettBtn` handler.

**Interfaces:**
- Consumes: `currentMode()`; existing `translatePythonThroughPy2m`, `translateRThroughR2m`, `loadPyodideAndM2py`, `loadPy2m`, `py2mReady`, `webRReady`.
- Produces: `plugin.translate` — a small descriptor reproducing each mode's CURRENT translate behavior. Shape:
  `{ showsButton: boolean, btnLabel: string, toMicrodata?: async (src) => {script, warnings}, fromMicrodata?: async (src) => {script} }`
  Exact per-mode values are pinned below from the current code.

- [ ] **Step 1: Read the current translate behavior** (so the reproduction is exact): `updateModeButtonsUi` hides `oversettBtn`+`btnTranslate` when `activeEditorMode === 'microdata'`; `updateTranslateBtnLabel` sets `btnTranslate` text to `'→ Microdata'` (non-microdata) / `'Translate'` (microdata); `translateAndSwitchToMicrodata` translates Python(py2m)/R(r2m)→microdata; the `oversettBtn` handler has microdata→Python, python→microdata, r→microdata branches. Reproduce all of this.

- [ ] **Step 2: Add `translate` descriptors to plugins.** Add to each entry:

```js
  // microdata: button hidden; (handler still has a microdata→Python branch — preserved)
  microdata: { …existing…, translate: { showsButton: false, btnLabel: 'Translate',
    toPython: async function (src, py) {
      var raw = await py.runPythonAsync(
        'from m2py import MicroInterpreter as _MI\n_e_ov = _MI()\n' +
        'str(_e_ov.translate_script_to_python(' + JSON.stringify(src) + '))');
      return String(raw);
    } } },
  python: { …existing…, translate: { showsButton: true, btnLabel: '→ Microdata',
    toMicrodata: async function (src, py) { await loadPy2m(py);
      if (!py2mReady) throw new Error('py2m ikke tilgjengelig.');
      return await translatePythonThroughPy2m(src, py); } } },
  r: { …existing…, translate: { showsButton: true, btnLabel: '→ Microdata',
    toMicrodata: async function (src) {
      if (!webRReady) throw new Error('WebR ikke klar.');
      return await translateRThroughR2m(src); } } },
```

- [ ] **Step 3: Rewire button visibility in `updateModeButtonsUi`.** Replace:

```js
      var isMicro = activeEditorMode === 'microdata';
      var oBtn = document.getElementById('oversettBtn');
      if (oBtn) oBtn.style.display = isMicro ? 'none' : '';
      var tBtn = document.getElementById('btnTranslate');
      if (tBtn) tBtn.style.display = isMicro ? 'none' : '';
```

with:

```js
      var _shows = !!(currentMode().translate && currentMode().translate.showsButton);
      var oBtn = document.getElementById('oversettBtn');
      if (oBtn) oBtn.style.display = _shows ? '' : 'none';
      var tBtn = document.getElementById('btnTranslate');
      if (tBtn) tBtn.style.display = _shows ? '' : 'none';
```

- [ ] **Step 4: Rewire `updateTranslateBtnLabel`.** Replace:

```js
      btn.textContent = activeEditorMode !== 'microdata' ? '→ Microdata' : 'Translate';
```

with:

```js
      btn.textContent = (currentMode().translate && currentMode().translate.btnLabel) || 'Translate';
```

- [ ] **Step 5: Rewire `translateAndSwitchToMicrodata`.** Replace the `if (fromMode === 'python') { … } else { … }` block (the part that produces `script`/`warnings`) with a call through the plugin of `fromMode`:

```js
        const fromPlugin = modeRegistry[fromMode];
        const res = await fromPlugin.translate.toMicrodata(src, py);
        script = res.script;
        warnings = res.warnings;
```
(Keep the surrounding loading-indicator, `editorContent.microdata = script`, warnings rendering, and catch block exactly as-is. The `await loadPyodideAndM2py()` that sets `py` stays.)

- [ ] **Step 6: Rewire the `oversettBtn` handler.** Replace the `if (activeEditorMode === 'microdata') { … } else if … python … else if … r …` chain with:

```js
          var t = currentMode().translate;
          if (activeEditorMode === 'microdata') {
            var py = await loadPyodideAndM2py();
            script = await t.toPython(src, py);
            editorContent.python = script;
          } else if (t && t.toMicrodata) {
            if (activeEditorMode === 'r' && !webRReady) {
              outputArea.innerHTML = '<div class="transl-warn">WebR er ikke klar ennå. Vent litt og prøv igjen.</div>';
              return;
            }
            var py2 = activeEditorMode === 'python' ? await loadPyodideAndM2py() : null;
            var res = await t.toMicrodata(src, py2);
            script = res.script; warnings = res.warnings;
            editorContent.microdata = script;
          }
```
(Reproduces the three original branches: microdata→Python writes `editorContent.python`; python/r→microdata write `editorContent.microdata`, with the R-not-ready guard preserved. Keep the rest of the handler — output rendering, button re-enable in `finally` — unchanged.)

- [ ] **Step 7: Structural check**

```bash
grep -c "isMicro = activeEditorMode === 'microdata'" index.html   # 0
grep -c "activeEditorMode !== 'microdata' ? '→ Microdata'" index.html  # 0
grep -c 'currentMode().translate' index.html                     # >=3
```
Expected: `0`, `0`, and `>=3`.

- [ ] **Step 8: Browser check** — microdata mode: Translate/Oversett buttons hidden (as before). Python mode: button visible labelled "→ Microdata"; write a small pandas script, click it → translates to microdata + switches, warnings shown if any. R mode: same via r2m; with webR not ready, the "WebR er ikke klar" message appears. No console errors.

- [ ] **Step 9: Commit**

```bash
git add index.html
git commit -m "refactor(modes): route translate buttons + actions via plugin.translate

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Route the run-entry preludes through `plugin.runSelf` / `preRun` / `runDefault`

**Files:**
- Modify: `index.html` — add `runSelf`/`preRun`/`runDefault` to plugins; rewire the R short-circuit, Python pip-prelude, and `runDefault` selection inside the `btnRun.addEventListener('click', async () => { … })` handler.

**Interfaces:**
- Consumes: `currentMode()`; existing `runHybridR(src, py, runOpts)`, `getRunnerDefaultMode()`, `extractPythonImports`, and the run-handler locals `py`, `rightStatus`, `_showCmds`, `effectiveScript`.
- Produces: `plugin.runSelf(script, ctx)` (R), `plugin.preRun(script, ctx)` (Python), `plugin.runDefault` (Python `'pyodide'`), where `ctx = { py, rightStatus, showCommands }`.

- [ ] **Step 1: Add run hooks to plugins.**

```js
  python: { …existing…, runDefault: 'pyodide',
    preRun: async function (script, ctx) {
      try {
        setStatus(ctx.rightStatus, 'Sjekker pakker…');
        await ctx.py.loadPackagesFromImports(script, {
          messageCallback: function (msg) { setStatus(ctx.rightStatus, msg); } });
      } catch (e) { console.warn('loadPackagesFromImports:', e); }
      var _pyPkgs = extractPythonImports(script);
      for (var _pkg of _pyPkgs) {
        try {
          var _needInstall = await ctx.py.runPythonAsync(
            'import importlib.util as _iu\n_iu.find_spec(' + JSON.stringify(_pkg) + ') is None');
          if (_needInstall) {
            setStatus(ctx.rightStatus, 'Installerer ' + _pkg + '…');
            await ctx.py.runPythonAsync('import micropip as _mp\nawait _mp.install(' + JSON.stringify(_pkg) + ')');
          }
        } catch (e) { console.warn('micropip install', _pkg, e); }
      }
    } },
  r: { …existing…,
    runSelf: async function (script, ctx) {
      await runHybridR(script, ctx.py, { showCommands: ctx.showCommands });
    } },
```
(This is the verbatim move of the inline R/Python preludes into the plugins.)

- [ ] **Step 2: Rewire the run entry.** In the `btnRun` click handler, find the block that begins `// ── R mode: run natively in WebR ──` and replace the R short-circuit + Python pip block (down through `// ── End auto-install ──`) with:

```js
        var _mr = currentMode();
        var _ctx = { py: py, rightStatus: rightStatus, showCommands: _showCmds };
        if (_mr.runSelf) { await _mr.runSelf(effectiveScript, _ctx); return; }
        if (_mr.preRun)  await _mr.preRun(effectiveScript, _ctx);
```
(`_showCmds` is computed just above this block — keep that line. The R `return` preserves the original short-circuit.)

- [ ] **Step 3: Rewire `runDefault`.** Replace:

```js
        const runDefault = activeEditorMode === 'python' ? 'pyodide' : getRunnerDefaultMode();
```

with:

```js
        const runDefault = currentMode().runDefault || getRunnerDefaultMode();
```

- [ ] **Step 4: Structural check**

```bash
grep -c "if (activeEditorMode === 'r') {" index.html        # 0  (run short-circuit gone)
grep -c "activeEditorMode === 'python' ? 'pyodide'" index.html  # 0
grep -c 'runSelf' index.html   # 2  (def + call)
grep -c 'preRun' index.html    # 2  (def + call)
```
Expected: `0`, `0`, `2`, `2`.

- [ ] **Step 5: Browser check** — Run a microdata script → output as before. Switch to Python, run a script that imports a package (e.g. `import pandas as pd; …`) → packages auto-install, output renders. Switch to R, run an R script → runs via webR. Run a **hybrid** script (mixed microdata + python blocks) in microdata mode → still runs identically. No console errors.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "refactor(modes): route run preludes via plugin.runSelf/preRun/runDefault

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Final sweep, seam note, regression

**Files:**
- Modify: `index.html` — add a one-line comment documenting the authoring-shell seam (no behavior change). Optionally `docs/` note.

**Interfaces:**
- Consumes: the full Stage 1 result.

- [ ] **Step 1: Confirm routed branches are gone.** Run:

```bash
grep -nE "activeEditorMode === '(microdata|python|r)'|newMode === 'r'|mode === 'python' \|\| mode === 'r'" index.html
```
Expected: only **category-2 / non-routed** matches remain (e.g. inside `triggerTolkResultat` reading `activeEditorMode` as a label value, and any `seg.kind`-adjacent logic). There must be NO remaining match in: `switchEditorMode`, `updateModeButtonsUi`, `updateTranslateBtnLabel`, `renderScriptHighlight`, the Tab dispatch, the translate handlers, or the run entry. Eyeball each hit and confirm it is intentionally retained; list them in the commit message.

- [ ] **Step 2: Document the reserved authoring-shell seam.** Add this comment just above the `modeRegistry` block:

```js
// Authoring-shell seam (reserved for a future jamovi-style ribbon, NOT built):
// a shell can drive any mode programmatically via switchEditorMode(id) +
// setEditor(text, lang) (js/github-storage.js) + document.getElementById('btnRun').click().
```

- [ ] **Step 3: Engine no-regression sanity check.** Run:

```bash
.venv/bin/python -m pytest tests/ -q
```
Expected: same as baseline (`165 passed, 1 xfailed`) — Stage 1 touches no Python.

- [ ] **Step 4: Full manual browser smoke** (the behavioral gate). On `http://localhost:8000/`, with no console errors: (a) microdata run; (b) Python highlight + Tab + run + translate→microdata; (c) R highlight + Tab + run + translate→microdata; (d) mode dropdown + labels; (e) switching to R lazy-loads webR; (f) a hybrid script runs.

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "refactor(modes): document authoring-shell seam; finalize mode registry

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage** (`2026-06-26-stage1-mode-registry-design.md`):
- `modeRegistry` + `currentMode()` → T1. ✓
- Routed call-sites: label/dropdown (T1), `onActivate`/loadWebR (T2), highlight (T3), Tab (T4), translate incl. button visibility + label (T5), run entry `runSelf`/`preRun`/`runDefault` (T6). ✓ — covers every site in the spec's "Call-sites routed" list.
- Three plugins registered as pure extraction → fields added across T1–T6 with verbatim behavior. ✓
- Run-hook model (shared pipeline intact; only preludes lifted) → T6. ✓
- Inline placement, no `js/` file, no build → Global Constraints + every task modifies only `index.html`. ✓
- Translate-verbatim caveat (non-uniform; microdata button hidden but handler branch kept) → T5 Steps 1/2/6. ✓
- Category-2 `seg.kind` untouched → Global Constraints + T7 Step 1 explicitly retains them. ✓
- Reserve authoring-shell seam, don't build → T7 Step 2 (doc only); no ribbon/statx/jamovi anywhere. ✓
- Verification = greps + browser; pytest unaffected → per-task checks + T7 Step 3. ✓

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to Task N". The two `…` ellipses (T4 Step 1, T5 Step 2) explicitly mean "the existing body, moved verbatim" and name the boundary — not vague instructions. T3 Step 1 flags a real ordering check (PY_HL_CFG declaration position) with a concrete decision rule rather than assuming.

**Type/name consistency:** `modeRegistry`, `currentMode()`, and plugin fields `id`/`label`/`hlConfig`/`handleTab`/`translate`/`onActivate`/`runSelf`/`preRun`/`runDefault` are used identically across tasks. `ctx = { py, rightStatus, showCommands }` matches between T6 Step 1 (consumers) and Step 2 (construction). `translate` sub-shape (`showsButton`/`btnLabel`/`toMicrodata`/`toPython`) is consistent between T5 Steps 2, 3, 4, 5, 6.

**Risk note for the executor:** This is behavior-preserving refactoring of fragile, coupled code with no front-end unit tests. The per-task structural greps + browser checks are the gate; do not skip the browser check, and prefer cut/paste (not retyping) when a step says "verbatim".
