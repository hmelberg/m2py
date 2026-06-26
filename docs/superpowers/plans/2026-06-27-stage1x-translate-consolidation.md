# Stage 1.x — Translate Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `plugin.translate` the single registry-routed translate path: route `btnTranslate` through it, remove the duplicate `oversettBtn` button, and delete the dead translate code.

**Architecture:** Inline edits to `index.html`. The live `btnTranslate` handler (currently `if activeEditorMode === '…' → doTranslate*`) becomes `currentMode().translate.run()`. The redundant `oversettBtn` + `initOversettBtn` and the dead `translateAndSwitchToMicrodata` / `doTranslateMicrodataToPython` are removed.

**Tech Stack:** Static HTML/JS (no build, classic scripts). No front-end unit-test harness.

## Global Constraints

- **Behavior-preserving for reachable paths.** Python/R → microdata translation must still work via the surviving **Translate** button, rendered via `renderTranslationResult` exactly as `btnTranslate` does today. Microdata mode still shows no translate button.
- The only removals are **dead** functions and the **unreachable** `oversettBtn` path (both translate buttons were already hidden in microdata, so microdata→Python was unreachable).
- Inline only — `index.html`; no new file, no `type="module"`, no build, no `window.*` change.
- Front-end verification = structural greps + manual browser; `pytest` unaffected (no Python change) — run once at the end as a sanity check.

### Local verification setup

```bash
cd /Users/hom/Documents/GitHub/m2py
python3 -m http.server 8000   # open http://localhost:8000/, watch the Console
```

---

### Task 1: Consolidate translate — route btnTranslate, remove the Oversett button

**Files:**
- Modify: `index.html` — `modeRegistry` translate descriptors; `updateModeButtonsUi`; `btnTranslate` click handler; delete `initOversettBtn` IIFE; delete `oversettBtn` `<button>`.

**Interfaces:**
- Consumes: `currentMode()`, existing `doTranslatePythonToMicrodata`, `doTranslateRToMicrodata`.
- Produces: `plugin.translate = { showsButton, btnLabel, run? }` on all three plugins. After this task, `translateAndSwitchToMicrodata` and `doTranslateMicrodataToPython` have no callers (deleted in Task 2).

- [ ] **Step 1: Replace the three `plugin.translate` descriptors.** In `modeRegistry`, change microdata/python/r so their `translate` reads (keep every OTHER field — id/label/hlConfig/handleTab/onActivate/runDefault/preRun/runSelf — untouched):

```js
      microdata: { id: 'microdata', label: 'Microdata', handleTab: microdataHandleTab,
        translate: { showsButton: false, btnLabel: 'Translate' } },
      python:    { id: 'python',    label: 'Python', hlConfig: PY_HL_CFG, handleTab: handlePythonTab,
        translate: { showsButton: true, btnLabel: '→ Microdata', run: doTranslatePythonToMicrodata },
        runDefault: 'pyodide',
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
      r:         { id: 'r',         label: 'R', hlConfig: R_HL_CFG, onActivate: function () { if (!webRReady && !webRLoading) loadWebR(); }, handleTab: handleRTab,
        translate: { showsButton: true, btnLabel: '→ Microdata', run: doTranslateRToMicrodata },
        runSelf: async function (script, ctx) {
          await runHybridR(script, ctx.py, { showCommands: ctx.showCommands });
        } },
```
(The only changes vs current: microdata loses `toPython`; python's `translate` loses `toMicrodata` and gains `run: doTranslatePythonToMicrodata`; r's `translate` loses `toMicrodata` and gains `run: doTranslateRToMicrodata`. preRun/runSelf/runDefault are unchanged — shown for context.)

- [ ] **Step 2: Route the `btnTranslate` handler.** Replace the current handler:

```js
    btnTranslate.addEventListener('click', async () => {
      if (btnTranslate.disabled || scriptRunInProgress) return;
      btnTranslate.disabled = true;
      try {
        if (activeEditorMode === 'microdata') {
          await doTranslateMicrodataToPython();
        } else if (activeEditorMode === 'python') {
          await doTranslatePythonToMicrodata();
        } else {
          await doTranslateRToMicrodata();
        }
      } catch (e) {
        const errMsg = (e && e.message) ? e.message : String(e);
        purgePlots(outputArea);
        outputArea.innerHTML = '';
        const pre = document.createElement('pre');
        pre.className = 'error';
        pre.textContent = 'Translation error:\n' + errMsg;
        outputArea.appendChild(pre);
        setStatus(rightStatus, 'Translation failed.', true);
      }
      btnTranslate.disabled = false;
    });
```

with:

```js
    btnTranslate.addEventListener('click', async () => {
      if (btnTranslate.disabled || scriptRunInProgress) return;
      const t = currentMode().translate;
      if (!t || !t.run) return;
      btnTranslate.disabled = true;
      try {
        await t.run();
      } catch (e) {
        const errMsg = (e && e.message) ? e.message : String(e);
        purgePlots(outputArea);
        outputArea.innerHTML = '';
        const pre = document.createElement('pre');
        pre.className = 'error';
        pre.textContent = 'Translation error:\n' + errMsg;
        outputArea.appendChild(pre);
        setStatus(rightStatus, 'Translation failed.', true);
      }
      btnTranslate.disabled = false;
    });
```
(The `if (!t.run) return` runs BEFORE `disabled = true`, so no re-enable is needed in that branch — microdata has no `run` and its button is hidden anyway.)

- [ ] **Step 3: Drop the `oversettBtn` visibility in `updateModeButtonsUi`.** Replace:

```js
      // Oversett-knapp: kun synlig i Python/R-modus
      var _shows = !!(currentMode().translate && currentMode().translate.showsButton);
      var oBtn = document.getElementById('oversettBtn');
      if (oBtn) oBtn.style.display = _shows ? '' : 'none';
      var tBtn = document.getElementById('btnTranslate');
      if (tBtn) tBtn.style.display = _shows ? '' : 'none';
```

with:

```js
      // Translate-knapp: kun synlig i Python/R-modus
      var _shows = !!(currentMode().translate && currentMode().translate.showsButton);
      var tBtn = document.getElementById('btnTranslate');
      if (tBtn) tBtn.style.display = _shows ? '' : 'none';
```

- [ ] **Step 4: Delete the `initOversettBtn` IIFE.** Remove the entire `(function initOversettBtn() { … })();` block (from `    (function initOversettBtn() {` through its matching `    })();`). Delete the whole block including its surrounding blank line.

- [ ] **Step 5: Delete the `oversettBtn` button element.** Remove this line from the HTML:

```html
      <button type="button" class="oversett-btn" id="oversettBtn" style="display:none">Oversett</button>
```

- [ ] **Step 6: Structural check**

```bash
grep -c 'oversettBtn' index.html                 # 0
grep -c 'initOversettBtn' index.html             # 0
grep -c "activeEditorMode === 'microdata'" index.html  # (unchanged elsewhere; the btnTranslate branch is gone — see next)
grep -c 'currentMode().translate.run\|t.run()' index.html  # >=1
grep -c 'toPython\|toMicrodata' index.html        # 0  (Task-5 fields removed)
grep -c 'doTranslatePythonToMicrodata\|doTranslateRToMicrodata' index.html  # 4  (each: def + registry ref)
```
Expected: `0`, `0`, a count (no longer including the btnTranslate microdata branch), `>=1`, `0`, `4`.

- [ ] **Step 7: Browser check** — Python mode: **one** Translate button ("→ Microdata"), click → microdata rendered in output as before; no "Oversett" button. R mode: same via r2m. Microdata mode: no translate button. No console errors.

- [ ] **Step 8: Commit**

```bash
git add index.html
git commit -m "refactor(translate): consolidate to plugin.translate.run; remove duplicate Oversett button

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Delete dead translate functions + fix help text

**Files:**
- Modify: `index.html` — delete `translateAndSwitchToMicrodata` and `doTranslateMicrodataToPython`; update the variable-detail help string.

**Interfaces:**
- Consumes: nothing new. After Task 1 both functions have zero callers.

- [ ] **Step 1: Confirm both functions are now dead.** Run:

```bash
grep -n 'translateAndSwitchToMicrodata' index.html       # only the definition line
grep -n 'doTranslateMicrodataToPython' index.html        # only the definition line
```
Expected: each appears exactly once (its `async function …` definition), no call-sites.

- [ ] **Step 2: Delete `translateAndSwitchToMicrodata`.** Remove the entire `async function translateAndSwitchToMicrodata() { … }` block (from that line through its matching closing `}` at the same 4-space indent).

- [ ] **Step 3: Delete `doTranslateMicrodataToPython`.** Remove the entire `async function doTranslateMicrodataToPython() { … }` block (from that line through its matching closing `}`). Leave `renderTranslationResult`, `doTranslatePythonToMicrodata`, and `doTranslateRToMicrodata` intact.

- [ ] **Step 4: Update the help text.** In the variable-detail prose string, change `<strong>Oversett</strong>-knappen konverterer Python/R til microdata-syntaks.` to `<strong>Translate</strong>-knappen konverterer Python/R til microdata-syntaks.` (only the button name changes).

- [ ] **Step 5: Structural check**

```bash
grep -c 'translateAndSwitchToMicrodata' index.html   # 0
grep -c 'doTranslateMicrodataToPython' index.html    # 0
grep -c 'function renderTranslationResult\|function doTranslatePythonToMicrodata\|function doTranslateRToMicrodata' index.html  # 3 (kept)
grep -c '>Oversett<\|Oversett</strong>' index.html   # 0
```
Expected: `0`, `0`, `3`, `0`.

- [ ] **Step 6: Engine sanity + browser check**

```bash
.venv/bin/python -m pytest tests/ -q   # expect: 165 passed, 1 xfailed (baseline; no Python change)
```
Then in the browser: translate still works in Python and R; the variable-detail modal help reads "Translate"; no console errors.

- [ ] **Step 7: Commit**

```bash
git add index.html
git commit -m "refactor(translate): delete dead translate functions; help text → Translate

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage** (`2026-06-27-stage1x-translate-consolidation-design.md`):
- Consolidated `plugin.translate = { showsButton, btnLabel, run? }` → T1 Step 1. ✓
- Route `btnTranslate` via `currentMode().translate.run` → T1 Step 2. ✓
- `updateModeButtonsUi` drops `oversettBtn`; `updateTranslateBtnLabel` unchanged → T1 Step 3 (label fn untouched). ✓
- Delete `initOversettBtn` + `oversettBtn` button → T1 Steps 4–5. ✓
- Delete `translateAndSwitchToMicrodata` + `doTranslateMicrodataToPython` → T2 Steps 2–3. ✓
- Remove Task-5 `toPython`/`toMicrodata` fields → T1 Step 1 (replaced). ✓
- Help text → T2 Step 4. ✓
- Keep `doTranslatePythonToMicrodata` / `doTranslateRToMicrodata` / `renderTranslationResult` → preserved; verified in T2 Step 5. ✓

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to". T1 Step 1's preRun/runSelf are shown in full (context) so the editor reproduces the registry block exactly, not from memory.

**Type/name consistency:** `plugin.translate.run` / `showsButton` / `btnLabel` used identically across T1 Steps 1–3 and the handler. Deleted names (`oversettBtn`, `initOversettBtn`, `translateAndSwitchToMicrodata`, `doTranslateMicrodataToPython`, `toPython`, `toMicrodata`) are consistently the removal targets and appear in the grep checks. Kept names (`doTranslatePythonToMicrodata`, `doTranslateRToMicrodata`, `renderTranslationResult`) consistent.
