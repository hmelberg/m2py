# Stage 1.x — Remove Dead btnTranslate Cluster — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the dead, permanently-hidden `btnTranslate` cluster from `index.html`. Keep the live `oversettBtn` ("Oversett") and its registry routing untouched. Zero change to reachable behavior.

**Architecture:** Pure dead-code deletion in `index.html`. `btnTranslate` lives in a `.toolbar` that is always `display:none` (`.panel-left .toolbar { display:none }`), so its handler + the `doTranslate*` / `renderTranslationResult` / `translateAndSwitchToMicrodata` functions it reaches are never executed. The live path (`oversettBtn` → `currentMode().translate.toPython/toMicrodata`) is unchanged.

**Tech Stack:** Static HTML/JS (no build). No front-end unit-test harness.

## Global Constraints

- **Delete only dead code.** Do NOT touch: `oversettBtn`, `initOversettBtn`, `plugin.translate.{showsButton,toPython,toMicrodata}`, `updateModeButtonsUi`'s `oBtn`/`_shows` lines, and especially `btnRun` / `btnForklar` / `btnRunFooter` (they share the hidden toolbar but are LIVE, proxied by footer buttons).
- Inline only — `index.html`; no new file, no `type="module"`, no build, no `window.*` change.
- Verification = structural greps + manual browser; `pytest` unaffected.

### Local verification

```bash
cd /Users/hom/Documents/GitHub/m2py && python3 -m http.server 8000   # http://localhost:8000/
```

---

### Task 1: Remove the dead btnTranslate UI, handler, label function

**Files:**
- Modify: `index.html` — delete the `btnTranslate` `<button>`, its click handler, its `const`, `updateTranslateBtnLabel` + its call, and the `tBtn` lines in `updateModeButtonsUi`.

**Interfaces:**
- After this task, `doTranslateMicrodataToPython` / `doTranslatePythonToMicrodata` / `doTranslateRToMicrodata` / `renderTranslationResult` have no callers (deleted in Task 2).

- [ ] **Step 1: Delete the `btnTranslate` button element.** Remove ONLY this line (leave the sibling `btnRun` and `btnForklar` buttons in the same toolbar intact):

```html
        <button class="btn btn-primary" id="btnTranslate" type="button">Translate</button>
```

- [ ] **Step 2: Delete the `btnTranslate` click handler.** Remove the entire block:

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

- [ ] **Step 3: Delete the `const btnTranslate` declaration.** Remove the line:

```js
    const btnTranslate = document.getElementById('btnTranslate');
```
(Leave the adjacent `const btnRun = document.getElementById('btnRun');` line intact.)

- [ ] **Step 4: Delete `updateTranslateBtnLabel` and its call.** Remove the function:

```js
    function updateTranslateBtnLabel() {
      var btn = document.getElementById('btnTranslate');
      if (!btn) return;
      btn.textContent = (currentMode().translate && currentMode().translate.btnLabel) || 'Translate';
    }
```
and remove its single call inside `switchEditorMode` (the line `      updateTranslateBtnLabel();`).

- [ ] **Step 5: Remove the `tBtn` lines in `updateModeButtonsUi`.** The block currently reads:

```js
      // Oversett-knapp: kun synlig i Python/R-modus
      var _shows = !!(currentMode().translate && currentMode().translate.showsButton);
      var oBtn = document.getElementById('oversettBtn');
      if (oBtn) oBtn.style.display = _shows ? '' : 'none';
      var tBtn = document.getElementById('btnTranslate');
      if (tBtn) tBtn.style.display = _shows ? '' : 'none';
```
Remove ONLY the last two lines (the `tBtn` declaration and its `if`). Keep the comment, `_shows`, and the `oBtn` lines exactly.

- [ ] **Step 6: Structural check**

```bash
grep -c 'btnTranslate' index.html              # 0
grep -c 'updateTranslateBtnLabel' index.html    # 0
grep -c "id=\"btnRun\"\|id=\"btnForklar\"\|btnRunFooter" index.html  # unchanged (>=3) — sanity that run buttons survive
grep -c 'oversettBtn' index.html                # >=2 (untouched)
```
Expected: `0`, `0`, an unchanged count (≥3), and ≥2.

- [ ] **Step 7: Browser check** — Oversett button still visible + translates in Python/R; Run and step-wise-run (Forklar) still work; no console errors.

- [ ] **Step 8: Commit**

```bash
git add index.html
git commit -m "refactor(translate): remove dead hidden btnTranslate button + handler + label

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Delete the orphaned translate functions + drop unused btnLabel

**Files:**
- Modify: `index.html` — delete `doTranslate*`, `renderTranslationResult`, `translateAndSwitchToMicrodata`; drop `btnLabel` from the three `plugin.translate` descriptors.

**Interfaces:**
- Consumes nothing new. After Task 1 these functions and the `btnLabel` field have zero readers.

- [ ] **Step 1: Confirm all are now orphaned.** Run:

```bash
grep -n 'doTranslateMicrodataToPython\|doTranslatePythonToMicrodata\|doTranslateRToMicrodata\|renderTranslationResult\|translateAndSwitchToMicrodata' index.html
```
Expected: each name appears only at its `function …` definition (no call-sites).

- [ ] **Step 2: Delete the five functions.** Remove the complete function bodies of (each from its `async function …`/`function …` line through its matching closing `}` at the same 4-space indent):
- `translateAndSwitchToMicrodata`
- `renderTranslationResult`
- `doTranslateMicrodataToPython`
- `doTranslatePythonToMicrodata`
- `doTranslateRToMicrodata`

(Leave everything between/around them that is unrelated intact — work one function at a time, re-grepping line numbers between deletions.)

- [ ] **Step 3: Drop the now-unused `btnLabel`.** In the three `plugin.translate` descriptors, remove the `btnLabel: '…'` property (it was only read by the deleted `updateTranslateBtnLabel`). Keep `showsButton`, `toPython`, `toMicrodata`. Example — microdata becomes `translate: { showsButton: false, toPython: async function (src, py) { … } }`; python/r keep `{ showsButton: true, toMicrodata: … }`.

- [ ] **Step 4: Structural check**

```bash
grep -c 'doTranslateMicrodataToPython\|doTranslatePythonToMicrodata\|doTranslateRToMicrodata\|renderTranslationResult\|translateAndSwitchToMicrodata' index.html  # 0
grep -c 'btnLabel' index.html        # 0
grep -c 'toPython\|toMicrodata\|showsButton' index.html  # unchanged (live path kept)
```
Expected: `0`, `0`, and a kept count (≥4).

- [ ] **Step 5: Engine sanity + browser check**

```bash
.venv/bin/python -m pytest tests/ -q   # expect: 165 passed, 1 xfailed
```
Browser: Oversett translate still works in Python and R; no console errors.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "refactor(translate): delete orphaned doTranslate*/renderTranslationResult/translateAndSwitch; drop unused btnLabel

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage** (corrected `2026-06-27-stage1x-translate-consolidation-design.md`):
- Delete `btnTranslate` button / handler / const → T1 Steps 1–3. ✓
- Delete `updateTranslateBtnLabel` + call → T1 Step 4. ✓
- Remove `tBtn` lines, keep `oBtn`/`_shows` → T1 Step 5. ✓
- Delete `doTranslate*` / `renderTranslationResult` / `translateAndSwitchToMicrodata` → T2 Step 2. ✓
- Drop unused `btnLabel`, keep `showsButton`/`toPython`/`toMicrodata` → T2 Step 3. ✓
- Keep `oversettBtn`, `btnRun`, `btnForklar` untouched → Global Constraints + T1 Steps 1/3/5 sanity grep. ✓

**Placeholder scan:** No vague steps; each deletion names the exact code. The "leave sibling buttons intact" guards appear at every shared-region deletion (T1 Steps 1, 3, 5).

**Type/name consistency:** Deleted names (`btnTranslate`, `updateTranslateBtnLabel`, `doTranslate*`, `renderTranslationResult`, `translateAndSwitchToMicrodata`, `btnLabel`) are consistent across tasks and grep checks. Kept names (`oversettBtn`, `btnRun`, `btnForklar`, `showsButton`, `toPython`, `toMicrodata`) consistent.
