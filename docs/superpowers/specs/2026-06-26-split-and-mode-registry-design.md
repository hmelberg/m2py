# Design: split index.html (Stage 0) + mode registry (Stage 1) + statx mode (Stage 2)

Status: **design** — first concrete piece of a larger staged arc. jamovi is
**out of scope** for this spec; it gets its own spec later. This document
covers **Stage 0** (physical split, zero behavior change), **Stage 1** (mode
registry refactor), and **Stage 2** (a new `statx` language plugin, powered by
pdexplorer — folded in because, once Stage 1 exists, it is a registration plus a
runtime rather than a core change).

> Naming: the mode is called **`statx`** everywhere (id and user-facing label).
> It is *powered by* pdexplorer (a pandas-based emulator of Stata-style
> commands), but the mode is not branded "Stata".

## Context

`index.html` is an ~11,500-line monolith: a `<style>` block, the HTML body, and
two inline `<script>` blocks (the second is ~8,860 lines). It is **not** a
tangle — it is already organized into ~15 named IIFE modules that communicate
through an explicit `window.*` surface (`window.mdAuth`, `window.updateLineNumbers`,
`window.mdClearOutput`, `window.lastDatasetInfo`, `window.__getDisclosureControl`,
…). The split below **finishes the modularization the code already started**
rather than introducing a new paradigm.

### Build model: stay no-build

The app deploys as static files on Netlify with a service-worker precache list
(`sw.js`, `CACHE` constant). That simplicity is a deliberate virtue. This spec
keeps it: extracted code is loaded via ordered plain `<script src>` tags (no
`type="module"`, no bundler). The planned extensions need a **mode registry**
(an in-code pattern), not a build step. Adopting ESM/Vite is explicitly
deferred to a possible later stage, only if the module graph demands it.

### The two-axis mental model (informs Stage 1's seams)

Future work distinguishes two different kinds of "mode":

1. **Language/runtime plugins** — microdata, python, r (today); `statx` via
   pdexplorer (Stage 2 of this spec). Each provides `{ highlight, handleTab,
   run, translateToMicrodata? }`.
2. **Authoring shells** — the text editor (today), the AI chat panel
   (`mdAskAi`, already exists), and a jamovi-style point-and-click ribbon
   (later). A shell does not run code itself; it **emits code into a language
   plugin**.

Directional decision recorded for the later jamovi spec: **jamovi = an
authoring shell that emits standard R** (base/stats/tidyverse, via our own
codegen templates — *not* literal `jmv::` calls, which depend on the `jmv`
package loading in webR, an unverified bet) and runs it through the **existing
R/webR language plugin**. R is chosen as the intermediate because it is the
portable/teachable artifact, reuses the existing webR runner, and sits
*upstream* of microdata via the existing `r2m` translator (so jamovi actions
become microdata for free if desired). Stage 1 only needs to leave clean
`run` / `setEditor` seams a future ribbon can call; it builds none of this.

## Stage 0 — Physical split (no behavior change)

**Goal:** shrink `index.html` to a thin shell by extracting already-isolated
units. **Net effect:** `index.html` drops to ~5–6k lines; deploy model
unchanged.

### Extractions

- **`app.css`** ← the `<style>` block (~lines 10–1014). Linked from `<head>`.
- **`js/` folder** for extracted scripts (alongside existing `widgets/`).
  Extract the self-contained IIFE subsystems, each to its own file, preserving
  the existing `window.*` contract verbatim:
  - `js/login.js` — the `mdAuth` IIFE (login/magic-link/session).
  - `js/ai-chat.js` — the kode-svar AI chat panel (`mdAskAi`, `mdInterpretResults`).
  - `js/github-storage.js` — share-link + GitHub file storage
    (`mdGithubClearCurrent`, `mdGithubRefreshIndicator`).
  - `js/forklar.js` — the explain/TTS playback subsystem (pairs with the
    existing `widgets/forklar-widgets.js`).
  - As convenient, the smaller already-IIFE'd units: `js/csv-recode.js`
    (`initCsvRecodeTool`), `js/settings.js` (`initSettings`),
    `js/layout.js` (`initLayoutAndResizer`).

What stays inline in `index.html` for now: the editor core, mode system, run
pipeline, output rendering, variable catalog/sidebar — these are the tightly
coupled core that Stage 1 reshapes. Extracting them physically is **not**
attempted in Stage 0 (it would be a behavior-risk refactor); Stage 1 makes them
a registry first, and physical extraction of the core can follow later.

### Namespace

Keep the ad-hoc `window.md*` / `window.__*` surface **as-is** during Stage 0
(no consolidation under a single `window.M2PY` object — that would add churn for
no Stage-0 benefit). Tidy later if desired.

### Load order (no bundler resolves this)

Plain `<script src>` tags execute in document order. Producers of a `window.*`
symbol must load before consumers. The implementation plan will pin an explicit
order; the governing rules:

- Existing third-party CDN scripts and `widgets/forklar-widgets.js` /
  `command_help.js` keep their current relative position.
- Extracted modules that only **define** `window.*` and **wire on
  `DOMContentLoaded`** can load in any order among themselves, as long as they
  load before any inline code that calls them at parse time.
- Each extracted IIFE is moved **wholesale** (no logic edits) so its internal
  references and its `window.*` exports are unchanged.

### Service worker

`sw.js` precaches assets. Bump the `CACHE` constant and add `app.css` and every
new `js/*.js` file to the precache list (per the README rule: "bump `CACHE`
whenever the precache list changes").

### Verification (Stage 0)

This stage adds **zero behavior**; success = byte-for-byte-equivalent runtime
behavior. The pytest suite and manual smoke suite cover the **engine**, not the
front-end, so they neither help nor regress here. Front-end verification is
manual in-browser:

- App loads with no console errors; service worker registers.
- Each extracted subsystem works: login flow, AI chat send + interpret,
  GitHub share-link + open/save, forklar playback, CSV-recode import, settings
  (theme/font/runner mode/disclosure), layout resizer.
- A microdata script, a Python script, and an R script each still run.

## Stage 1 — Mode registry (the keystone)

**Goal:** replace `activeEditorMode` + the scattered `=== 'python' / 'r' /
'microdata'` switch-sites with one registry, so adding a language mode becomes a
registration rather than editing ~6 call-sites.

### Interface

```js
// A language/runtime plugin.
{
  id,                       // 'microdata' | 'python' | 'r'
  label,                    // dropdown label
  highlight(text),          // syntax highlight  (← highlightScriptPyR / renderScriptHighlight)
  handleTab(e),             // autocomplete on Tab (← handlePythonTab / handleRTab / microdataSlashSuggest)
  run(src, opts),           // execute            (← the run dispatch)
  translateToMicrodata(src) // optional           (← doTranslate{Python,R}ToMicrodata)
}
```

A `modeRegistry` maps `id → plugin`. `activeEditorMode` remains the current-mode
string; the dispatch sites resolve `modeRegistry.get(activeEditorMode)` and call
the method instead of branching on the string.

### Call-sites to route through the registry

(Line numbers are from the pre-split file; the implementation plan re-locates
them post-Stage-0.)

- `switchEditorMode(newMode)` (~4107) — central mode switch.
- Highlight: `highlightScriptPyR(text, mode)` (~3694), `renderScriptHighlight`
  (~2666).
- Tab/autocomplete dispatch (~5629): `handlePythonTab` (~5485), `handleRTab`
  (~5554), `microdataSlashSuggest` (~5472).
- Run dispatch: the `activeEditorMode` branches (~5802, ~7812, ~7848) and the
  hybrid R / py2m / webR paths.
- Translate: `doTranslateMicrodataToPython` (~7794),
  `doTranslatePythonToMicrodata` (~7820), `doTranslateRToMicrodata` (~7833);
  `updateTranslateBtnLabel` (~4150), `translateAndSwitchToMicrodata` (~4156).
- Dropdown UI: `updateModeButtonsUi` (~4132), `initModeSwitcher` (~4216).

### Registering the three existing modes

This is a **pure extraction**: today's `microdata` / `python` / `r` logic moves
verbatim into three plugin objects. No new behavior. The three existing modes
exercise every registry path before any new mode exists, so the registry is
fully covered by current functionality.

### Reserve the second axis (do not build)

Leave a clean seam for authoring shells without implementing one:

- Ensure there is a single function to set editor content + active mode that a
  future ribbon can call (today's `setEditor(text, lang)` / `switchEditorMode`).
- Ensure `run(src, opts)` is callable programmatically (not only from the run
  button handler), so a future shell can "emit R and run" without touching core.

No ribbon, no jamovi in this spec. (statx is added in Stage 2 below.)

### Verification (Stage 1)

- microdata / python / r each highlight, autocomplete, run, and translate
  identically to before.
- Mode dropdown switches correctly; translate button label updates per mode.
- No `=== 'python'` / `=== 'r'` / `=== 'microdata'` branches remain in the
  routed call-sites (they now go through `modeRegistry`).

## Stage 2 — `statx` language plugin (pdexplorer)

**Goal:** add a 4th language mode, `statx`, that lets the user write
Stata-style commands and run them in the browser via **pdexplorer** in Pyodide.
Because Stage 1 made modes a registry, this is a **registration + a runtime**,
not a core edit. `statx` mirrors the existing `python` plugin most closely
(both run in Pyodide).

### Plugin shape

Register `statx` in `modeRegistry`:

```js
{
  id: 'statx',
  label: 'Statx',
  highlight(text),            // Stata-style keyword highlighter (new, can start minimal)
  handleTab(e),               // autocomplete (can start minimal — keyword list)
  run(src, opts),             // execute the script through pdexplorer in Pyodide
  // translateToMicrodata: omitted initially — no statx→microdata translator yet
}
```

- **Dropdown:** add a `statx` entry beside Microdata / Python / R.
- **Highlight / autocomplete:** can launch minimal (a Stata keyword list reusing
  the existing `highlightScriptPyR`-style tokenizer and the autocomplete
  plumbing). Parity with python's richness is not required for the first cut.
- **No translator:** `statx → microdata` (a `statx2m` mirroring `py2m`/`r2m`) is
  a **separate future effort**, explicitly not in this spec. The Translate
  button is simply unavailable in statx mode (same way it is handled for any
  mode lacking `translateToMicrodata`).

### Runtime: pdexplorer in Pyodide — the real risk to verify first

The registry wiring is low-risk; the **open risk is whether pdexplorer loads and
runs under Pyodide**. This MUST be verified at the start of Stage 2
implementation, before building UI:

1. **Install:** confirm `micropip.install("pdexplorer")` succeeds in Pyodide —
   i.e. pdexplorer (and its transitive deps) are pure-Python wheels with no
   unsupported native extensions. If a dep fails, identify whether it is already
   provided by Pyodide or has a pure-Python fallback.
2. **API:** confirm how a user-authored Stata-style script is executed —
   pdexplorer's command/`run` interface, how a dataset is loaded into it from
   the app's existing data source, and how its output (tables, regression
   results) is captured as text for the existing output renderer.
3. **Lazy load:** load pdexplorer lazily on first entry into statx mode (mirror
   `loadPy2m` / `schedulePrefetchLazyPackages`), not on page load.

If step 1 or 2 fails, Stage 2 stops and is reconsidered (e.g. vendored subset,
or deferred) — Stage 0 and Stage 1 stand on their own and are unaffected.

### Service worker / data

- If pdexplorer is fetched from PyPI at runtime via micropip, it is **not**
  precached by `sw.js` (consistent with how other lazy Pyodide packages are
  handled); document this so offline behavior is understood.
- statx reads the same in-browser dataset the python/microdata modes use; no new
  data source.

### Verification (Stage 2)

- Switching to `statx` mode loads pdexplorer (once), with a visible loading
  state, no console errors.
- A small Stata-style script (e.g. summarize + a regression) runs and renders
  output through the existing renderer.
- Switching away and back does not reload pdexplorer.
- The other three modes are unaffected (registry regression).

## Out of scope (explicit)

- jamovi / point-and-click ribbon — separate spec; authoring shell emitting R.
- `statx → microdata` translator (`statx2m`) — separate future effort.
- ESM / Vite / any build step.
- `window.M2PY` namespace consolidation.
- Physical extraction of the editor/mode/run/output core into `js/` files
  (Stage 1 makes it a registry; physical extraction can follow later).

## Sequencing

Stage 0 first (safe, makes the file workable), then Stage 1 (the architectural
keystone), then Stage 2 (`statx`, gated on the pdexplorer-in-Pyodide
verification). If Stage 2's runtime check fails, Stages 0–1 still ship. The
jamovi spec comes later, building on the registry and the reserved
authoring-shell seam.
