# Phase 0: Drop Jamovi light + Gate Microdata out of Openstat — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the jamovi light mode from all three repos (safestat, openstat, microdata) and gate the microdata mode out of openstat's UI (default becomes python), as phase 0 of the DuckDB-data-layer direction.

**Architecture:** Jamovi light is a full removal (button, module wiring, files) — it was a stepping stone to the real jamovi/webR mode and has no users to protect. Microdata in openstat is a **soft drop via gating**: the dropdown button goes away and persisted `microdata` mode migrates to the hostname default (python), but the `modeRegistry.microdata` entry, hybrid `#micro` support, `data-mode-only="microdata"` elements, and the microdata examples HTML all stay — they are auto-hidden by existing gating and keep the change reversible and sync-friendly. Safestat and the microdata repo keep microdata mode untouched.

**Tech Stack:** Vanilla JS single-file `index.html` per repo (no build step), `js/i18n/en.js` key-based translations, `node --test` for the JS unit tests, manual browser smoke test via `python3 -m http.server`.

## Global Constraints

- Do NOT touch the sync-checked core files (`m2py.py`, `functions.py`, `protect.py`, `m2py_translate.py`, `mockdata_*.py`, `static_source.py`, `command_help.js`, `variable_metadata.json`, `codelists/`). `scripts/sync_check.sh` excludes `index.html` and `js/` — UI files drift freely by design.
- In openstat, do NOT remove: `modeRegistry.microdata` (it is `currentMode()`'s fallback at `index.html:3054`), `RUNTIME_FOR_MODE.microdata`, `STARTUP_EXAMPLES.microdata`, the `data-section-mode="microdata"` examples block, `data-mode-only="microdata"` elements, or the `menuRunnerMode` button (already permanently `display:none`).
- The three `index.html` files are near-identical in structure but differ in line numbers and small text details (safestat says "Velg språk", the others "Velg modus"; safestat's title list ends "…Brython, SafeStat"). Always match on the exact strings given per task, not line numbers.
- Each repo is committed separately on its current branch (safestat: `master`, openstat: `main`, microdata: `main`).
- i18n rule: `js/i18n/en.js` keys are the literal Norwegian strings from `index.html`. When an attribute text changes, the en.js key AND value must change to match, or the English translation silently breaks.

---

### Task 1: Remove jamovi light from safestat

**Files:**
- Modify: `/Users/hom/Documents/GitHub/safestat/index.html` (lines ~509, ~519, ~3616–3627, ~3638, ~3863, ~3909)
- Modify: `/Users/hom/Documents/GitHub/safestat/js/i18n/en.js` (line ~94)
- Delete: `/Users/hom/Documents/GitHub/safestat/js/modes/jamovi_light.js`
- Delete: `/Users/hom/Documents/GitHub/safestat/css/modes/jamovi_light.css`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: a safestat build with no `jamovilight` mode. Persisted `md_editor_mode === 'jamovilight'` is handled by the existing fallback in `restoreEditorMode()` (jamovi modes self-register after boot, so the saved value fails the `modeRegistry` check and falls back to the hostname default).

- [ ] **Step 1: Remove the dropdown button**

In `index.html`, delete this whole line (~519):

```html
          <button type="button" data-mode="jamovilight">Jamovi light</button>
```

- [ ] **Step 2: Update the mode-picker tooltip**

Replace (~509):

```
title="Velg språk (Microdata, Python, R, Statx, Jamovi, Jamovi light, SQL - DuckDB, Brython, SafeStat)"
```

with:

```
title="Velg språk (Microdata, Python, R, Statx, Jamovi, SQL - DuckDB, Brython, SafeStat)"
```

- [ ] **Step 3: Simplify the jamovi visibility conditionals**

Three exact-string replacements in `index.html` (the first two occur once each, the third occurs twice — replace both):

1. Comment (~3616): replace `// Input-panel visibility: jamovi/jamovilight hide it by default; other modes use the user pref.` with `// Input-panel visibility: jamovi hides it by default; other modes use the user pref.`
2. (~3618): replace `if (activeEditorMode !== 'jamovi' && activeEditorMode !== 'jamovilight')` with `if (activeEditorMode !== 'jamovi')`
3. (~3619 and ~3627, replace ALL): replace `(mode === 'jamovi' || mode === 'jamovilight')` with `(mode === 'jamovi')`
4. Comment (~3621): replace `// Topbar visibility: jamovi/jamovilight hide the fixed app topbar by default` with `// Topbar visibility: jamovi hides the fixed app topbar by default`
5. Comment (~3863): replace `(jamovi/jamovilight with the topbar toggled off)` with `(jamovi with the topbar toggled off)`

- [ ] **Step 4: Remove runtime and module wiring**

1. In `RUNTIME_FOR_MODE` (~3638): replace `jamovi: 'pyodide', jamovilight: 'pyodide', statx: 'pyodide',` with `jamovi: 'pyodide', statx: 'pyodide',`
2. In `MODE_MODULES` (~3909): replace

```js
var MODE_MODULES = { jamovi: { js: ['js/modes/jmv_specs.js', 'js/modes/jamovi.js'], css: 'css/modes/jamovi.css' }, jamovilight: { js: 'js/modes/jamovi_light.js', css: 'css/modes/jamovi_light.css' } };
```

with:

```js
var MODE_MODULES = { jamovi: { js: ['js/modes/jmv_specs.js', 'js/modes/jamovi.js'], css: 'css/modes/jamovi.css' } };
```

- [ ] **Step 5: Update the en.js tooltip key**

In `js/i18n/en.js` (~94), replace:

```js
  "Velg språk (Microdata, Python, R, Statx, Jamovi, Jamovi light, SQL - DuckDB, Brython, SafeStat)": "Select language (Microdata, Python, R, Statx, Jamovi, Jamovi light, SQL - DuckDB, Brython, SafeStat)",
```

with:

```js
  "Velg språk (Microdata, Python, R, Statx, Jamovi, SQL - DuckDB, Brython, SafeStat)": "Select language (Microdata, Python, R, Statx, Jamovi, SQL - DuckDB, Brython, SafeStat)",
```

- [ ] **Step 6: Delete the mode files**

```bash
git -C /Users/hom/Documents/GitHub/safestat rm js/modes/jamovi_light.js css/modes/jamovi_light.css
```

- [ ] **Step 7: Verify no references remain**

```bash
grep -rn "jamovilight\|jamovi_light" /Users/hom/Documents/GitHub/safestat/index.html /Users/hom/Documents/GitHub/safestat/js /Users/hom/Documents/GitHub/safestat/css
```

Expected: no output. (Historical plan docs under `docs/superpowers/plans/` may still mention it — that is fine, do not edit history.)

- [ ] **Step 8: Run the JS unit tests**

```bash
cd /Users/hom/Documents/GitHub/safestat && node --test tests/js/
```

Expected: all tests pass (none reference jamovilight — verified during planning).

- [ ] **Step 9: Commit**

```bash
git -C /Users/hom/Documents/GitHub/safestat add index.html js/i18n/en.js
git -C /Users/hom/Documents/GitHub/safestat commit -m "feat: drop jamovi light mode (superseded by jamovi/webR)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

(The `git rm` from Step 6 is already staged.)

---

### Task 2: Remove jamovi light from openstat

**Files:**
- Modify: `/Users/hom/Documents/GitHub/openstat/index.html` (lines ~363, ~373, ~3057–3068, ~3079, ~3167, ~3213)
- Modify: `/Users/hom/Documents/GitHub/openstat/js/i18n/en.js` (line ~94)
- Delete: `/Users/hom/Documents/GitHub/openstat/js/modes/jamovi_light.js`
- Delete: `/Users/hom/Documents/GitHub/openstat/css/modes/jamovi_light.css`

**Interfaces:**
- Consumes: nothing.
- Produces: the tooltip string `"Velg modus (Microdata, Python, R, Statx, Jamovi, SQL - DuckDB, Brython)"` in `index.html` and as the en.js key — Task 4 edits this exact string again.

Openstat's `index.html` is structurally identical to safestat's here, with two text differences: the tooltip says **"Velg modus"** (not "Velg språk") and its list has **no trailing ", SafeStat"**.

- [ ] **Step 1: Remove the dropdown button**

Delete this whole line (~373):

```html
          <button type="button" data-mode="jamovilight">Jamovi light</button>
```

- [ ] **Step 2: Update the mode-picker tooltip**

Replace (~363):

```
title="Velg modus (Microdata, Python, R, Statx, Jamovi, Jamovi light, SQL - DuckDB, Brython)"
```

with:

```
title="Velg modus (Microdata, Python, R, Statx, Jamovi, SQL - DuckDB, Brython)"
```

- [ ] **Step 3: Simplify the jamovi visibility conditionals**

Identical replacements to Task 1 Step 3, restated in full:

1. Replace `// Input-panel visibility: jamovi/jamovilight hide it by default; other modes use the user pref.` with `// Input-panel visibility: jamovi hides it by default; other modes use the user pref.`
2. Replace `if (activeEditorMode !== 'jamovi' && activeEditorMode !== 'jamovilight')` with `if (activeEditorMode !== 'jamovi')`
3. Replace ALL (2 occurrences): `(mode === 'jamovi' || mode === 'jamovilight')` with `(mode === 'jamovi')`
4. Replace `// Topbar visibility: jamovi/jamovilight hide the fixed app topbar by default` with `// Topbar visibility: jamovi hides the fixed app topbar by default`
5. Replace `(jamovi/jamovilight with the topbar toggled off)` with `(jamovi with the topbar toggled off)`

- [ ] **Step 4: Remove runtime and module wiring**

1. In `RUNTIME_FOR_MODE` (~3079): replace `jamovi: 'pyodide', jamovilight: 'pyodide', statx: 'pyodide',` with `jamovi: 'pyodide', statx: 'pyodide',`
2. In `MODE_MODULES` (~3213): replace

```js
var MODE_MODULES = { jamovi: { js: ['js/modes/jmv_specs.js', 'js/modes/jamovi.js'], css: 'css/modes/jamovi.css' }, jamovilight: { js: 'js/modes/jamovi_light.js', css: 'css/modes/jamovi_light.css' } };
```

with:

```js
var MODE_MODULES = { jamovi: { js: ['js/modes/jmv_specs.js', 'js/modes/jamovi.js'], css: 'css/modes/jamovi.css' } };
```

- [ ] **Step 5: Update the en.js tooltip key**

In `js/i18n/en.js` (~94), replace:

```js
  "Velg modus (Microdata, Python, R, Statx, Jamovi, Jamovi light, SQL - DuckDB, Brython)": "Select mode (Microdata, Python, R, Statx, Jamovi, Jamovi light, SQL - DuckDB, Brython)",
```

with:

```js
  "Velg modus (Microdata, Python, R, Statx, Jamovi, SQL - DuckDB, Brython)": "Select mode (Microdata, Python, R, Statx, Jamovi, SQL - DuckDB, Brython)",
```

- [ ] **Step 6: Delete the mode files**

```bash
git -C /Users/hom/Documents/GitHub/openstat rm js/modes/jamovi_light.js css/modes/jamovi_light.css
```

- [ ] **Step 7: Verify no references remain**

```bash
grep -rn "jamovilight\|jamovi_light" /Users/hom/Documents/GitHub/openstat/index.html /Users/hom/Documents/GitHub/openstat/js /Users/hom/Documents/GitHub/openstat/css
```

Expected: no output.

- [ ] **Step 8: Run the JS unit tests**

```bash
cd /Users/hom/Documents/GitHub/openstat && node --test tests/js/
```

Expected: all tests pass.

- [ ] **Step 9: Commit**

```bash
git -C /Users/hom/Documents/GitHub/openstat add index.html js/i18n/en.js
git -C /Users/hom/Documents/GitHub/openstat commit -m "feat: drop jamovi light mode (superseded by jamovi/webR)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Remove jamovi light from microdata

**Files:**
- Modify: `/Users/hom/Documents/GitHub/microdata/index.html` (lines ~382, ~392, ~3390–3401, ~3412, ~3501, ~3547)
- Modify: `/Users/hom/Documents/GitHub/microdata/js/i18n/en.js` (line ~94)
- Delete: `/Users/hom/Documents/GitHub/microdata/js/modes/jamovi_light.js`
- Delete: `/Users/hom/Documents/GitHub/microdata/css/modes/jamovi_light.css`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing other tasks rely on.

Microdata's `index.html` uses the same "Velg modus" tooltip text as openstat. Steps are identical to Task 2 with microdata paths — restated in full:

- [ ] **Step 1: Remove the dropdown button**

Delete this whole line (~392):

```html
          <button type="button" data-mode="jamovilight">Jamovi light</button>
```

- [ ] **Step 2: Update the mode-picker tooltip**

Replace (~382):

```
title="Velg modus (Microdata, Python, R, Statx, Jamovi, Jamovi light, SQL - DuckDB, Brython)"
```

with:

```
title="Velg modus (Microdata, Python, R, Statx, Jamovi, SQL - DuckDB, Brython)"
```

- [ ] **Step 3: Simplify the jamovi visibility conditionals**

1. Replace `// Input-panel visibility: jamovi/jamovilight hide it by default; other modes use the user pref.` with `// Input-panel visibility: jamovi hides it by default; other modes use the user pref.`
2. Replace `if (activeEditorMode !== 'jamovi' && activeEditorMode !== 'jamovilight')` with `if (activeEditorMode !== 'jamovi')`
3. Replace ALL (2 occurrences): `(mode === 'jamovi' || mode === 'jamovilight')` with `(mode === 'jamovi')`
4. Replace `// Topbar visibility: jamovi/jamovilight hide the fixed app topbar by default` with `// Topbar visibility: jamovi hides the fixed app topbar by default`
5. Replace `(jamovi/jamovilight with the topbar toggled off)` with `(jamovi with the topbar toggled off)`

- [ ] **Step 4: Remove runtime and module wiring**

1. In `RUNTIME_FOR_MODE` (~3412): replace `jamovi: 'pyodide', jamovilight: 'pyodide', statx: 'pyodide',` with `jamovi: 'pyodide', statx: 'pyodide',`
2. In `MODE_MODULES` (~3547): replace

```js
var MODE_MODULES = { jamovi: { js: ['js/modes/jmv_specs.js', 'js/modes/jamovi.js'], css: 'css/modes/jamovi.css' }, jamovilight: { js: 'js/modes/jamovi_light.js', css: 'css/modes/jamovi_light.css' } };
```

with:

```js
var MODE_MODULES = { jamovi: { js: ['js/modes/jmv_specs.js', 'js/modes/jamovi.js'], css: 'css/modes/jamovi.css' } };
```

- [ ] **Step 5: Update the en.js tooltip key**

In `js/i18n/en.js` (~94), replace:

```js
  "Velg modus (Microdata, Python, R, Statx, Jamovi, Jamovi light, SQL - DuckDB, Brython)": "Select mode (Microdata, Python, R, Statx, Jamovi, Jamovi light, SQL - DuckDB, Brython)",
```

with:

```js
  "Velg modus (Microdata, Python, R, Statx, Jamovi, SQL - DuckDB, Brython)": "Select mode (Microdata, Python, R, Statx, Jamovi, SQL - DuckDB, Brython)",
```

- [ ] **Step 6: Delete the mode files**

```bash
git -C /Users/hom/Documents/GitHub/microdata rm js/modes/jamovi_light.js css/modes/jamovi_light.css
```

- [ ] **Step 7: Verify no references remain**

```bash
grep -rn "jamovilight\|jamovi_light" /Users/hom/Documents/GitHub/microdata/index.html /Users/hom/Documents/GitHub/microdata/js /Users/hom/Documents/GitHub/microdata/css
```

Expected: no output.

- [ ] **Step 8: Run the JS unit tests (if the repo has them)**

```bash
cd /Users/hom/Documents/GitHub/microdata && [ -d tests/js ] && node --test tests/js/ || echo "no tests/js in this repo"
```

Expected: pass, or the no-tests message.

- [ ] **Step 9: Commit**

```bash
git -C /Users/hom/Documents/GitHub/microdata add index.html js/i18n/en.js
git -C /Users/hom/Documents/GitHub/microdata commit -m "feat: drop jamovi light mode (superseded by jamovi/webR)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Gate microdata mode out of openstat (default: python)

**Files:**
- Modify: `/Users/hom/Documents/GitHub/openstat/index.html` (lines ~363, ~364, ~368, ~3474–3480)
- Modify: `/Users/hom/Documents/GitHub/openstat/js/i18n/en.js` (line ~94)

**Interfaces:**
- Consumes: Task 2's tooltip string `"Velg modus (Microdata, Python, R, Statx, Jamovi, SQL - DuckDB, Brython)"` (this task edits it again). If Task 2 was somehow skipped, adjust the old-strings accordingly — the intent is only to drop "Microdata, " from the list.
- Produces: openstat where microdata is unreachable from the UI but still present in `modeRegistry` (hybrid `#micro` blocks keep working).

**What deliberately stays (see Global Constraints):** `modeRegistry.microdata`, `RUNTIME_FOR_MODE.microdata`, `STARTUP_EXAMPLES.microdata`, `let activeEditorMode = 'microdata'` (transient boot value only — `restoreEditorMode()` always switches off it), the `data-section-mode="microdata"` examples block (auto-hidden by `index.html:1539` once the mode is never active), `data-mode-only="microdata"` elements (`menuOfflineBtn`, `btnDmQuick` — auto-hidden by `applyModeVisibility()`), and `menuRunnerMode` (already permanently `display:none`).

- [ ] **Step 1: Remove the microdata dropdown button**

Delete this whole line (~368):

```html
          <button type="button" data-mode="microdata" class="active">Microdata</button>
```

(The `class="active"` marker is redundant — `updateModeButtonsUi()` re-toggles `active` on every switch, and `restoreEditorMode()` always runs at boot.)

- [ ] **Step 2: Fix the boot label flash**

Replace (~364):

```html
          <span id="editorModeLabel">Microdata</span>
```

with:

```html
          <span id="editorModeLabel">Python</span>
```

(Cosmetic: the label the user sees for the instant before `restoreEditorMode()` sets the real one.)

- [ ] **Step 3: Migrate persisted microdata mode to the default**

In the `restoreEditorMode` IIFE (~3474), replace:

```js
      var saved = null;
      try { saved = localStorage.getItem('md_editor_mode'); } catch (e) {}
```

with:

```js
      var saved = null;
      try { saved = localStorage.getItem('md_editor_mode'); } catch (e) {}
      // Microdata-modus er gated av i openstat (fase 0, 2026-07-11): emulatoren
      // bor i microdata-repoen og safestat beholder modusen for beskyttede
      // data. Lagret microdata-modus faller tilbake til hostname-default.
      if (saved === 'microdata') saved = null;
```

(With `saved = null` the existing line below picks `NotebookLinks.hostnameMode(location.hostname)`, which returns `'python'` except on the `py.`/`r.`/`duck.` subdomains — that IS the new default, no further change needed.)

- [ ] **Step 4: Update the mode-picker tooltip**

Replace (~363, as produced by Task 2):

```
title="Velg modus (Microdata, Python, R, Statx, Jamovi, SQL - DuckDB, Brython)"
```

with:

```
title="Velg modus (Python, R, Statx, Jamovi, SQL - DuckDB, Brython)"
```

- [ ] **Step 5: Update the en.js tooltip key**

In `js/i18n/en.js` (~94), replace:

```js
  "Velg modus (Microdata, Python, R, Statx, Jamovi, SQL - DuckDB, Brython)": "Select mode (Microdata, Python, R, Statx, Jamovi, SQL - DuckDB, Brython)",
```

with:

```js
  "Velg modus (Python, R, Statx, Jamovi, SQL - DuckDB, Brython)": "Select mode (Python, R, Statx, Jamovi, SQL - DuckDB, Brython)",
```

- [ ] **Step 6: Verify the gating is complete but the registry survives**

```bash
grep -c "data-mode=\"microdata\"" /Users/hom/Documents/GitHub/openstat/index.html
grep -c "microdata: { id: 'microdata'" /Users/hom/Documents/GitHub/openstat/index.html
```

Expected: first command prints `6` (the six example buttons — kept, auto-hidden), second prints `1` (registry entry kept). The dropdown button is gone (it was the only `data-mode="microdata"` *inside `editorModeMenu`* — spot-check with `grep -n "editorModeMenu" -A 10` if in doubt).

- [ ] **Step 7: Run the JS unit tests**

```bash
cd /Users/hom/Documents/GitHub/openstat && node --test tests/js/
```

Expected: all pass — `notebook-links.test.js` already asserts `hostnameMode()` defaults to `'python'`, which this task now relies on.

- [ ] **Step 8: Commit**

```bash
git -C /Users/hom/Documents/GitHub/openstat add index.html js/i18n/en.js
git -C /Users/hom/Documents/GitHub/openstat commit -m "feat: gate microdata mode out of openstat UI, default python

Microdata stays in the registry (hybrid #micro still works) and in
safestat/microdata repos; persisted microdata mode falls back to the
hostname default. Phase 0 of the DuckDB-data-layer plan.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Cross-repo smoke test (manual, in browser)

**Files:** none modified — verification only.

**Interfaces:**
- Consumes: Tasks 1–4 committed.
- Produces: go/no-go for pushing/deploying.

- [ ] **Step 1: Serve each repo locally**

```bash
cd /Users/hom/Documents/GitHub/openstat && python3 -m http.server 8001
```

(Repeat with safestat on 8002 and microdata on 8003, or check one at a time.)

- [ ] **Step 2: Openstat checks (http://localhost:8001)**

1. DevTools → Application → clear Local Storage for the origin → reload. Expected: mode label shows **Python**, python startup example is seeded, no console errors.
2. Open the mode dropdown. Expected: **no Microdata, no Jamovi light**; entries are Python, R, Statx, Jamovi, SQL - DuckDB, Brython.
3. In the console: `localStorage.setItem('md_editor_mode', 'microdata')` → reload. Expected: lands in Python mode (migration line), no errors.
4. Same with `'jamovilight'` → reload. Expected: lands in Python mode, no errors.
5. Examples menu shows no microdata section (auto-hidden — section only shows for the active mode).
6. Switch to Jamovi mode. Expected: module loads, topbar hides as before (the simplified conditionals still fire for jamovi).
7. Run one SQL example and one python example. Expected: both run as before.

- [ ] **Step 3: Safestat checks (http://localhost:8002)**

1. Mode dropdown: **Microdata still present**, Jamovi light gone.
2. `localStorage.setItem('md_editor_mode', 'jamovilight')` → reload. Expected: falls back to default mode, no errors.
3. Microdata mode still runs an example script (unchanged behavior).
4. Jamovi mode still loads.

- [ ] **Step 4: Microdata repo checks (http://localhost:8003)**

1. Mode dropdown: Microdata present and default, Jamovi light gone.
2. One microdata example runs.

- [ ] **Step 5: Deploy note**

No push/deploy in this plan — Hans pushes when satisfied. Remember the CDN-cache trap on the deploy branches: `index.html` changes can be served stale; verify on the live site after deploy with a hard reload.
