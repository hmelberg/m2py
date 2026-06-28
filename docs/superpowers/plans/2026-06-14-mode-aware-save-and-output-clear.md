# Mode-aware Save Guard + Output Clearing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the editor from silently overwriting a GitHub file with a different-mode buffer, and clear stale output when a new script loads.

**Architecture:** Two small, additive changes in `index.html`. The GitHub binding (`cur`) stays global; save + the save indicator become mode-aware by checking `langFromPath(cur.path) === currentLang()`. Output is cleared at the genuine "load a new script" entry points. Cross-IIFE calls use `window.*` exports, matching the existing `window.mdGithubClearCurrent` idiom.

**Tech Stack:** Vanilla JS in a single `index.html`; verified with `node --check` on inline scripts + a browser load check (no JS unit-test harness in this project).

---

## Scope / verified facts

- `currentLang()` (index.html:10371) returns `activeEditorMode` (or `microdata`).
- `langFromPath(p)` (10386): `.py`→python, `.r`→r, else→microdata.
- GitHub binding + indicator + save live in the `initScriptSharing` IIFE
  (10358–11170): `getCurrent`/`setCurrent` (10611), `updateCurrentIndicator`
  (10749), `doSave` (10961), `openSaveAs` (10978), `setEditor` (10375). Exports
  via `window.mdGithubClearCurrent` (11162).
- `switchEditorMode` (4103) is in a DIFFERENT scope → reach the indicator only
  through a `window.*` export.
- `clearOutput()` (3291) exists, is idempotent.
- Example loaders set `scriptInput` directly (microdata examples ~2871,
  web_examples `loadSelected` ~2966) and don't clear output; `setEditor` doesn't
  either. `setEditor` is used only by load paths (not by "Oversett").
- `ensureExt` (11002) appends the correct extension by `currentLang()` on
  Save-As, so a name without extension becomes mode-correct automatically.

## File structure

Single file: `index.html`. Two independent tasks (output clearing; save guard).

---

## Task 1: Clear output when a new script loads

**Files:**
- Modify: `index.html` (clearOutput export ~3297; `setEditor` ~10375; examples loader ~2887; web_examples `loadSelected` ~2975)

- [ ] **Step 1: Export `clearOutput` on `window` for cross-scope callers**

In `index.html`, the `clearOutput` function ends at line 3297 with `}`. Immediately AFTER that closing `}` (before `const _menuClearOutput = ...` on 3298), insert:

```javascript
      window.mdClearOutput = clearOutput;
```

- [ ] **Step 2: Clear output in `setEditor` (covers URL/GitHub/recent/shared loads)**

In `setEditor` (10375), change the body start. Replace:

```javascript
      function setEditor(text, lang) {
        lang = (lang === 'python' || lang === 'r') ? lang : 'microdata';
```

with:

```javascript
      function setEditor(text, lang) {
        if (window.mdClearOutput) window.mdClearOutput();
        lang = (lang === 'python' || lang === 'r') ? lang : 'microdata';
```

- [ ] **Step 3: Clear output in the microdata examples loader**

In the examples-button handler (~2887), replace:

```javascript
            scriptInput.value = text;
            scriptName.value = title;
            if (window.mdGithubClearCurrent) window.mdGithubClearCurrent();
```

with:

```javascript
            scriptInput.value = text;
            scriptName.value = title;
            if (window.mdClearOutput) window.mdClearOutput();
            if (window.mdGithubClearCurrent) window.mdGithubClearCurrent();
```

- [ ] **Step 4: Clear output in the web_examples loader**

In `loadSelected` (~2975), replace:

```javascript
            scriptInput.value = text;
            scriptName.value = selectedScript.label;
            if (window.updateLineNumbers) window.updateLineNumbers();
            closeOverlay();
```

with:

```javascript
            scriptInput.value = text;
            scriptName.value = selectedScript.label;
            if (window.mdClearOutput) window.mdClearOutput();
            if (window.updateLineNumbers) window.updateLineNumbers();
            closeOverlay();
```

- [ ] **Step 5: Syntax-check inline scripts**

Run (from repo root):
```bash
python3 - <<'PY'
import re, subprocess, tempfile, os
html = open('index.html', encoding='utf-8').read()
blocks=[b for a,b in re.findall(r'<script\b([^>]*)>(.*?)</script>', html, re.S|re.I) if 'src=' not in a.lower()]
bad=0
for i,b in enumerate(blocks):
    f=tempfile.NamedTemporaryFile('w',suffix='.js',delete=False,encoding='utf-8'); f.write(b); f.close()
    r=subprocess.run(['node','--check',f.name],capture_output=True,text=True); os.unlink(f.name)
    if r.returncode: bad+=1; print(f"block {i}:\n{r.stderr[:800]}")
print("OK" if not bad else f"{bad} failed")
PY
```
Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "fix(ui): clear output container when loading a new script"
```

---

## Task 2: Mode-aware GitHub save guard + indicator

**Files:**
- Modify: `index.html` (`doSave` ~10969; `updateCurrentIndicator` ~10754; `openSaveAs` ~10985; `switchEditorMode` ~10122; refresh export ~11162)

- [ ] **Step 1: Guard `doSave` against overwriting a different-mode file**

In `doSave` (10961), after the existing repo/branch guard line, add a mode guard. Replace:

```javascript
        if (!cur || !cur.path || cur.repo !== s.repo || cur.branch !== s.branch) { openSaveAs(); return; }
        const si = $('scriptInput');
```

with:

```javascript
        if (!cur || !cur.path || cur.repo !== s.repo || cur.branch !== s.branch) { openSaveAs(); return; }
        // Don't overwrite a file whose extension belongs to a different editor
        // mode (e.g. saving a Python buffer over a microdata .txt) — route to Save As.
        if (langFromPath(cur.path) !== currentLang()) { openSaveAs(); return; }
        const si = $('scriptInput');
```

- [ ] **Step 2: Show the save indicator only when the bound file matches the mode**

In `updateCurrentIndicator` (10749), replace:

```javascript
        if (cur && cur.path) {
          const dirty = ghIsDirty();
```

with:

```javascript
        if (cur && cur.path && langFromPath(cur.path) === currentLang()) {
          const dirty = ghIsDirty();
```

(The existing `else { if (save) save.style.display = 'none'; }` then hides the floppy in a non-matching mode — no overwrite invitation, no false "dirty".)

- [ ] **Step 3: Make Save-As pre-fill mode-appropriate on a mode mismatch**

In `openSaveAs` (10978), replace:

```javascript
          if (cur && cur.path && cur.repo === s.repo) {
            input.value = cur.path;
          } else {
```

with:

```javascript
          if (cur && cur.path && cur.repo === s.repo && langFromPath(cur.path) === currentLang()) {
            input.value = cur.path;
          } else {
```

(On a mismatch this falls to the `scriptName` branch; `ensureExt` then appends the
correct extension for the current mode at save time.)

- [ ] **Step 4: Export an indicator-refresh hook**

Next to the existing export `window.mdGithubClearCurrent = function () { setCurrent(null); };` (11162), add on the following line:

```javascript
      window.mdGithubRefreshIndicator = function () { updateCurrentIndicator(); };
```

- [ ] **Step 5: Refresh the indicator on every mode switch**

In `switchEditorMode` (4103), at the END of the function — replace:

```javascript
      // Trigger lazy WebR load when switching to R
      if (newMode === 'r' && !webRReady && !webRLoading) loadWebR();
    }
```

with:

```javascript
      // Trigger lazy WebR load when switching to R
      if (newMode === 'r' && !webRReady && !webRLoading) loadWebR();
      // Refresh the GitHub save indicator: hide the floppy when the bound file's
      // extension no longer matches the active mode (cross-IIFE via window).
      if (window.mdGithubRefreshIndicator) window.mdGithubRefreshIndicator();
    }
```

- [ ] **Step 6: Syntax-check inline scripts**

Run the same `node --check` snippet as Task 1 Step 5.
Expected: `OK`.

- [ ] **Step 7: Browser load check**

Serve and load:
```bash
(python3 -m http.server 8779 >/tmp/h.log 2>&1 &) ; sleep 1
```
Navigate to `http://localhost:8779/index.html` (Playwright MCP). Confirm: only the
benign `favicon.ico` 404 in the console; the page loads. Then in the page console
(`browser_evaluate`) confirm the hooks exist:
```javascript
() => ({ clear: typeof window.mdClearOutput, refresh: typeof window.mdGithubRefreshIndicator })
```
Expected: `{ clear: "function", refresh: "function" }`. Stop the server
(`pkill -f "http.server 8779"`).

- [ ] **Step 8: Commit**

```bash
git add index.html
git commit -m "fix(ui): mode-aware GitHub save guard + indicator (no cross-mode overwrite)"
```

---

## Self-review notes

- **Spec coverage:**
  - B / `doSave` guard → Task 2 Step 1.
  - B / indicator gated on mode → Task 2 Step 2 + Step 5 (refresh on switch).
  - B / Save-As mode-appropriate pre-fill → Task 2 Step 3 (+ `ensureExt`).
  - B / `cur` never cleared on switch → nothing clears it; only the indicator hides.
  - Output clearing in `setEditor` + both example loaders → Task 1.
  - Not in `switchEditorMode` → confirmed (Task 2 Step 5 only refreshes the indicator).
- **Placeholder scan:** none; every step shows the exact edit.
- **Consistency:** the predicate `langFromPath(<cur>.path) === currentLang()` is
  used identically in `doSave`, `updateCurrentIndicator`, and `openSaveAs`;
  cross-IIFE calls use `window.mdClearOutput` / `window.mdGithubRefreshIndicator`,
  matching `window.mdGithubClearCurrent`.

## Discovered, NOT in scope (flag to user)

`loadSelected` (web_examples) does not call `mdGithubClearCurrent`, so loading a
web_example while bound to a GitHub file of the SAME mode leaves the binding
pointing at the old file (a non-mode overwrite risk that this plan's guard does
not catch). The microdata examples loader already clears the binding. This is a
one-line consistency fix but is outside the approved spec — surface it to the
user as a follow-up rather than implementing unasked.
