# Stage 0 — Physical Split of index.html — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Shrink `index.html` from ~11,500 lines to a thin shell by extracting the `<style>` block and the three large, self-contained late IIFEs into separate files, with **zero behavior change**.

**Architecture:** No build step. Extract code verbatim into plain classic `<script src>` / `<link>` files under `js/` and `app.css`. The extracted modules keep the existing `window.*` cross-module contract and also reference script #2's top-level globals (`loadPyodideAndM2py`, `switchEditorMode`, `activeEditorMode`, `editorContent`), which remain reachable because classic top-level declarations share one global environment. Safety therefore hinges on **load order**: extracted module scripts must load immediately after the main inline script, preserving their current end-of-file position.

**Tech Stack:** Static HTML/CSS/JS, Pyodide, service worker (`sw.js`), Netlify static hosting. No bundler, no test framework for the front-end.

## Global Constraints

- No build step. Extracted JS is **classic** scripts (`<script src="…">`, NOT `type="module"`). Move code **verbatim** — no logic edits in Stage 0.
- Extracted JS files live in `js/` (alongside existing `widgets/`).
- Keep the existing ad-hoc `window.md*` / `window.__*` surface **as-is** — do NOT consolidate under `window.M2PY` in this stage.
- Extracted module `<script src>` tags must load **after** the main inline script block (the one that ends at the original `</script>` on line 11183) and after the CDN libs (`pyodide.js`, `plotly`, `markdown-it`, `tabulator`) — i.e. in the same relative order they currently occupy at the end of script #2.
- After changing the precache set, bump the `CACHE` constant in `sw.js` and add the new files to its precache list (README rule: "bump `CACHE` whenever the precache list changes").
- Front-end has **no unit-test harness**; verification is manual in-browser plus grep-based structural checks. Engine pytest/`manual_scripts` suites are irrelevant here (no engine change) — do not expect them to catch front-end regressions.

### Local verification setup (used by every task)

Serve the static site and open it (the app is same-origin static; a plain HTTP server suffices for Pyodide + service worker):

```bash
cd /Users/hom/Documents/GitHub/m2py
python3 -m http.server 8000
# open http://localhost:8000/ in a browser; open devtools Console
```

"No console errors" below means: reload with an empty Console, confirm no red errors after the app finishes loading (a failed optional network fetch unrelated to the change is acceptable; a `ReferenceError`/`SyntaxError`/`is not a function` is NOT).

---

### Task 1: Extract the stylesheet to `app.css`

**Files:**
- Create: `app.css`
- Create: `js/.gitkeep` (establish the folder for later tasks)
- Modify: `index.html` (replace inline `<style>…</style>`, lines ~10–1014, with a `<link>`)

**Interfaces:**
- Consumes: nothing.
- Produces: `app.css` (the app's stylesheet), `js/` directory.

- [ ] **Step 1: Create the `js/` folder placeholder**

```bash
mkdir -p js && touch js/.gitkeep
```

- [ ] **Step 2: Copy the CSS out of index.html into app.css**

Open `index.html`. The stylesheet is the block from the line `  <style>` (line ~10) to its matching `  </style>` (line ~1014). Copy **only the lines between** `<style>` and `</style>` (not the tags themselves) into a new file `app.css`.

- [ ] **Step 3: Replace the inline block with a link**

In `index.html`, delete the entire `<style>…</style>` block and put in its place:

```html
  <link rel="stylesheet" href="app.css">
```

Place this `<link>` where the `<style>` tag was (inside `<head>`, before the existing `tabulator` stylesheet `<link>` so cascade order is unchanged).

- [ ] **Step 4: Structural check — CSS fully moved, no leftover inline style block**

Run:

```bash
grep -c '<style' index.html          # expect: 0
grep -c 'href="app.css"' index.html  # expect: 1
wc -l app.css                        # expect: ~1000 lines
```

Expected: `0`, `1`, and a ~1000-line `app.css`.

- [ ] **Step 5: Browser check — app looks identical**

Serve (see Local verification setup) and load `http://localhost:8000/`. Expected: layout, fonts, colors, the editor, the mode dropdown, sidebars and modals all render exactly as before; no console errors.

- [ ] **Step 6: Commit**

```bash
git add app.css js/.gitkeep index.html
git commit -m "refactor: extract inline <style> to app.css (no behavior change)"
```

---

### Task 2: Extract the login module to `js/login.js`

**Files:**
- Create: `js/login.js`
- Modify: `index.html` (remove the `authModule` IIFE; add `<script src>`)

**Interfaces:**
- Consumes (at runtime, from the shared global env / window): `window.markdownit` (CDN), and script #2 globals as already used inside the module.
- Produces: `window.mdAuth` (login API used by `ai-chat` and the run gate) — unchanged surface.

- [ ] **Step 1: Move the authModule IIFE into js/login.js**

In `index.html`, locate the IIFE that begins with the comment banner immediately above `    (function authModule() {` (the `/* ===… */` banner, originally line ~8864) and ends at its matching `    })();` (originally line ~9105). Cut **the banner comment + the entire `(function authModule() { … })();`** and paste it into a new file `js/login.js`. Do not edit the code.

- [ ] **Step 2: Add the script tag (after the main inline script)**

In `index.html`, immediately **after** the closing `</script>` of the main inline block (originally line ~11183), add:

```html
  <script src="js/login.js"></script>
```

- [ ] **Step 3: Structural check — module moved, tag added**

Run:

```bash
grep -c 'function authModule' index.html   # expect: 0
grep -c 'function authModule' js/login.js  # expect: 1
grep -c 'js/login.js' index.html           # expect: 1
```

Expected: `0`, `1`, `1`.

- [ ] **Step 4: Browser check — login works**

Serve and load the app. Open the AI panel / trigger login (the "Logg inn" path). Expected: the login modal opens, magic-link/email step renders, `window.mdAuth` exists (in Console: `typeof window.mdAuth` → `"object"`), no console errors on load.

- [ ] **Step 5: Commit**

```bash
git add js/login.js index.html
git commit -m "refactor: extract authModule to js/login.js (no behavior change)"
```

---

### Task 3: Extract the AI chat module to `js/ai-chat.js`

**Files:**
- Create: `js/ai-chat.js`
- Modify: `index.html` (remove the `aiModule` IIFE; add `<script src>`)

**Interfaces:**
- Consumes (runtime): `window.mdAuth` (from `js/login.js`), `window.markdownit`, and script #2 globals it already uses (`loadPyodideAndM2py`, `activeEditorMode`, etc.).
- Produces: `window.mdAskAi`, `window.mdInterpretResults`, `window.mdUpdateAskVisibility` — unchanged surface.

- [ ] **Step 1: Move the aiModule IIFE into js/ai-chat.js**

In `index.html`, locate the IIFE beginning with its `/* ===… */` banner above `    (function aiModule() {` (originally line ~9107) through its matching `    })();` (originally line ~10362). Cut the banner + the whole IIFE and paste into a new file `js/ai-chat.js`. No logic edits.

- [ ] **Step 2: Add the script tag after js/login.js**

In `index.html`, immediately after the `<script src="js/login.js"></script>` line, add:

```html
  <script src="js/ai-chat.js"></script>
```

(Order matters: `ai-chat` consumes `window.mdAuth` — but only at runtime — so being after `login.js` is correct and safe.)

- [ ] **Step 3: Structural check**

Run:

```bash
grep -c 'function aiModule' index.html    # expect: 0
grep -c 'function aiModule' js/ai-chat.js # expect: 1
grep -c 'js/ai-chat.js' index.html        # expect: 1
```

Expected: `0`, `1`, `1`.

- [ ] **Step 4: Browser check — AI chat works**

Serve and load. Open the AI panel; confirm the empty state renders and the input autoresizes. In Console: `typeof window.mdAskAi` → `"function"`. Run a microdata script, then trigger "Tolk resultat" (interpret) if available. Expected: panel functions as before, no console errors on load.

- [ ] **Step 5: Commit**

```bash
git add js/ai-chat.js index.html
git commit -m "refactor: extract aiModule to js/ai-chat.js (no behavior change)"
```

---

### Task 4: Extract the share + GitHub-storage module to `js/github-storage.js`

**Files:**
- Create: `js/github-storage.js`
- Modify: `index.html` (remove the `initScriptSharing` IIFE; add `<script src>`)

**Interfaces:**
- Consumes (runtime): script #2 globals `switchEditorMode`, `activeEditorMode`, `editorContent`, `window.updateLineNumbers`.
- Produces: `window.mdGithubClearCurrent`, `window.mdGithubRefreshIndicator` — unchanged surface.

- [ ] **Step 1: Move the initScriptSharing IIFE into js/github-storage.js**

In `index.html`, locate the IIFE starting at the `// ── Del / Åpne fra URL / Koble til GitHub …` comment above `    (function initScriptSharing() {` (originally line ~10364) through its matching `    })();` (originally line ~11182). Cut the leading comment + the whole IIFE and paste into a new file `js/github-storage.js`. No logic edits.

- [ ] **Step 2: Add the script tag (last of the three modules)**

In `index.html`, immediately after the `<script src="js/ai-chat.js"></script>` line, add:

```html
  <script src="js/github-storage.js"></script>
```

- [ ] **Step 3: Structural check**

Run:

```bash
grep -c 'function initScriptSharing' index.html            # expect: 0
grep -c 'function initScriptSharing' js/github-storage.js  # expect: 1
grep -c 'js/github-storage.js' index.html                  # expect: 1
```

Expected: `0`, `1`, `1`.

- [ ] **Step 4: Browser check — share, open-from-URL, GitHub indicator**

Serve and load. From the hamburger menu: "Del (kopier lenke)" copies a `#s=` link; open that link in a new tab and confirm the script loads into the editor. Open "Åpne fra URL…" modal. Open GitHub "Innstillinger…" modal. Switch editor mode microdata→python and confirm the GitHub save indicator behaves (calls `window.mdGithubRefreshIndicator`). In Console: `typeof window.mdGithubClearCurrent` → `"function"`. Expected: all work as before, no console errors on load.

- [ ] **Step 5: Commit**

```bash
git add js/github-storage.js index.html
git commit -m "refactor: extract initScriptSharing to js/github-storage.js (no behavior change)"
```

---

### Task 5: Update the service-worker precache

**Files:**
- Modify: `sw.js` (bump `CACHE`, add `app.css` + the three `js/*.js` files to the precache list)

**Interfaces:**
- Consumes: the four new asset paths created in Tasks 1–4.
- Produces: an updated precache manifest so the split assets are cached offline like before.

- [ ] **Step 1: Inspect current precache list and CACHE constant**

Run:

```bash
grep -nE "CACHE|PRECACHE|'\./|index.html|command_help" sw.js | head -30
```

Note the `CACHE` version string and the array of precached paths.

- [ ] **Step 2: Bump CACHE and add the new assets**

In `sw.js`, increment the `CACHE` version string (e.g. `m2py-v23` → `m2py-v24`; use the next integer after the current value). Add these entries to the precache list array, matching the existing quoting/path style used for `command_help.js`:

```
'app.css',
'js/login.js',
'js/ai-chat.js',
'js/github-storage.js',
```

- [ ] **Step 3: Structural check**

Run:

```bash
grep -c "js/login.js" sw.js          # expect: 1
grep -c "js/ai-chat.js" sw.js        # expect: 1
grep -c "js/github-storage.js" sw.js # expect: 1
grep -c "app.css" sw.js              # expect: 1
```

Expected: `1` for each.

- [ ] **Step 4: Browser check — service worker installs new cache**

Serve and load. In devtools → Application → Service Workers, confirm the worker activates the new cache version; in Cache Storage, confirm `app.css` and the three `js/*.js` files are present. Reload offline (devtools → Network → Offline) and confirm the app still loads. Expected: new cache version, all four assets cached, offline load works.

- [ ] **Step 5: Commit**

```bash
git add sw.js
git commit -m "chore(sw): precache app.css + extracted js modules, bump CACHE"
```

---

### Task 6: Final regression sweep + line-count confirmation

**Files:**
- None (verification only); optionally Modify `README.md` layout table if you choose to mention `js/`.

**Interfaces:**
- Consumes: the full Stage-0 result.
- Produces: confidence that behavior is unchanged and the file shrank as intended.

- [ ] **Step 1: Confirm index.html shrank**

Run:

```bash
wc -l index.html
```

Expected: roughly 5,500–6,500 lines (down from ~11,497), reflecting ~1000 CSS + ~3,200 module lines removed.

- [ ] **Step 2: Confirm no orphaned references**

Run:

```bash
grep -nE 'authModule|aiModule|initScriptSharing' index.html  # expect: no matches
```

Expected: no output.

- [ ] **Step 3: Full manual smoke in browser**

Serve and load. Exercise, with no console errors: (a) run a Microdata script; (b) switch to Python, run; (c) switch to R, run; (d) open + use the AI panel; (e) login modal opens; (f) Del-lenke round-trip; (g) GitHub settings modal; (h) theme/settings; (i) sidebar datasets after a run; (j) forklar playback on an explain script (forklar remains inline — confirm it still works).

- [ ] **Step 4: Commit (only if README updated)**

```bash
git add README.md
git commit -m "docs: note js/ module split in layout table"
```

---

## Self-Review

**Spec coverage (Stage 0 section of `2026-06-26-split-and-mode-registry-design.md`):**
- `app.css` extraction → Task 1. ✓
- `js/login.js`, `js/ai-chat.js`, `js/github-storage.js` → Tasks 2–4. ✓
- Smaller IIFEs (`csv-recode`, `settings`, `layout`) — spec said "as convenient"; **deferred** to keep Stage 0 low-risk and focused on the three big wins. Documented deviation, not a gap.
- `js/forklar.js` — spec listed it, but investigation showed forklar is **interleaved top-level functions, not a single IIFE**, so a verbatim cut is not possible without a riskier refactor. **Deferred** out of Stage 0; can be its own careful task later. Documented deviation.
- Load order rules → Global Constraints + each task's placement step. ✓
- Namespace left as-is → Global Constraints. ✓
- Service worker `CACHE` bump + precache → Task 5. ✓
- Verification is manual/browser (engine suites irrelevant) → Global Constraints + per-task browser checks. ✓

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to". Each task has concrete grep/browser checks with expected values. (Original line numbers are given as `~N` anchors paired with stable code markers — `(function authModule() {` etc. — because each extraction shifts subsequent line numbers; the markers are the authoritative anchor.)

**Type/name consistency:** Module function names (`authModule`, `aiModule`, `initScriptSharing`), produced globals (`window.mdAuth`, `window.mdAskAi`, `window.mdInterpretResults`, `window.mdGithubClearCurrent`, `window.mdGithubRefreshIndicator`), and file paths (`js/login.js`, `js/ai-chat.js`, `js/github-storage.js`, `app.css`) are used consistently across tasks and the sw.js update.

## Next stages (separate plans)

- **Stage 1 — mode registry.** Written as its own plan *after* Stage 0 lands, because every switch-site edit must be anchored against the post-extraction file. Integration points already identified in the spec: `switchEditorMode`, `updateModeButtonsUi`, `updateTranslateBtnLabel`, `translateAndSwitchToMicrodata`, `initModeSwitcher`/`initOversettBtn`, `highlightScriptPyR`/`renderScriptHighlight`, the Tab dispatch (`handlePythonTab`/`handleRTab`/`microdataSlashSuggest`), and the run/translate dispatch.
- **Stage 2 — `statx` (pdexplorer).** Its own plan, gated on the pdexplorer-in-Pyodide spike (spec's "real risk to verify first").
