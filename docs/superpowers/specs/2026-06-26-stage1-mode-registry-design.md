# Design: Stage 1 — mode registry

Status: **design**. Detailed design for Stage 1 of the split/registry arc,
refining the high-level Stage 1 section of
`2026-06-26-split-and-mode-registry-design.md` against the **post-Stage-0**
`index.html`. Stage 0 (physical split) is merged. `statx` (Stage 2) and jamovi
remain out of scope here; this spec only restructures the existing
microdata/python/r dispatch.

## Goal

Replace the ~dozen scattered `activeEditorMode === '…'` editor-level dispatch
sites with one **mode registry**, so adding a language mode becomes a
registration rather than editing many call-sites — with **zero behavior
change** for the three existing modes.

## Context: what's in the current code

`index.html` (post-split, ~8,180 lines) has ~80 mode references. They split into
two categories:

1. **Editor-level dispatch on the `activeEditorMode` global** — `switchEditorMode`,
   highlight config selection (`R_HL_CFG` / `PY_HL_CFG`), the Tab/autocomplete
   handler, the run *entry*, the translate-button wiring, and lazy-load-on-switch
   (`loadWebR`). **This is the registry's target.**
2. **Per-segment `seg.kind` / `mode` parameters** in the hybrid-script and forklar
   parsing (a single script may mix microdata + python/r blocks). This is a
   *different axis* (intra-script language, not editor mode) and is **out of
   scope** — left exactly as-is.

The run pipeline is a **shared scaffold with small mode-specific preludes**, not
cleanly per-mode (verified in `index.html`):
- R mode short-circuits early: `if (activeEditorMode === 'r') { await runHybridR(…); return; }`
- Python mode runs a pip-install prelude (`loadPackagesFromImports` + micropip loop).
- microdata + Python then share one segment-execution path that builds the
  interpreter-core Python (`getInterpreterCorePython`) and runs segments.

## Approach: registry + run-hook (chosen)

The registry owns the clean axes; the shared run pipeline stays intact and only
its mode-specific preludes are lifted out behind per-mode hooks. (Rejected: full
per-mode `run()` — rewrites the most fragile code, high risk, YAGNI. Rejected:
thin dispatch only — leaves run-entry branches hardcoded, so a 4th mode's run
wouldn't slot in.)

### The `ModePlugin` interface

```js
{
  id,                       // 'microdata' | 'python' | 'r'
  label,                    // dropdown label: 'Microdata' | 'Python' | 'R'
  hlConfig,                 // highlight config object (PY_HL_CFG / R_HL_CFG), or null for microdata
  handleTab(e),             // autocomplete on Tab; returns true if handled
  translate,                // optional; the mode's translate wiring (action + button
                            //   visibility/label) reproduced verbatim from today — see note
  onActivate,               // optional; runs when switching INTO this mode (R ⇒ loadWebR)
  // run modelling:
  runSelf,                  // optional async (script, ctx); if present, fully owns run and short-circuits (R ⇒ runHybridR)
  preRun,                   // optional async (script, ctx); prelude before the shared pipeline (Python ⇒ pip-install)
  runDefault,               // optional string; segment default for parseHybridScript ('pyodide' for Python)
}
```

`modeRegistry` maps `id → plugin`. `activeEditorMode` stays as the current-mode
string. A helper `currentMode()` returns `modeRegistry.get(activeEditorMode)`.

### Call-sites routed through the registry

(Names/areas in the post-split file; the plan re-anchors exact lines.)

- `switchEditorMode(newMode)` — central switch; calls `currentMode().onActivate?.()`
  instead of `if (newMode === 'r' && …) loadWebR()`.
- `updateModeButtonsUi` — label from `plugin.label`; Translate/Oversett button
  visibility reproduced from `plugin.translate` (exact current rule per the
  translate note below).
- `updateTranslateBtnLabel` — label driven by the active `plugin.translate`
  wiring, reproducing today's per-mode label.
- Highlight: the `mode === 'r' ? R_HL_CFG : PY_HL_CFG` selection reads
  `plugin.hlConfig`.
- Tab dispatch (`if (activeEditorMode === 'python') handlePythonTab… else if 'r' handleRTab…`)
  becomes `currentMode().handleTab(e)`.
- Translate (`translateAndSwitchToMicrodata`, the Oversett button handler) calls
  `plugin.translate`.
- **Run entry** (the de-branching):
  ```js
  const m = currentMode();
  if (m.runSelf) { await m.runSelf(effectiveScript, ctx); return; }   // R
  if (m.preRun)  await m.preRun(effectiveScript, ctx);                // Python pip
  const runDefault = m.runDefault ?? getRunnerDefaultMode();
  // … existing shared segment / interpreter-core pipeline, unchanged …
  ```
  `ctx` carries the locals those preludes need (`py`, `rightStatus`,
  `_showCmds`, etc.) — the plan pins the exact shape.

### Registering the three modes

Pure extraction of today's logic into three plugin objects:
- **microdata** — `hlConfig: null`, `handleTab` ⇒ `microdataSlashSuggest` path,
  `translate` ⇒ whatever microdata mode does today, no `runSelf`/`preRun`,
  default runner.
- **python** — `hlConfig: PY_HL_CFG`, `handleTab` ⇒ `handlePythonTab`,
  `translate` ⇒ `translatePythonThroughPy2m` path, `preRun` ⇒ the pip-install
  prelude, `runDefault: 'pyodide'`.
- **r** — `hlConfig: R_HL_CFG`, `handleTab` ⇒ `handleRTab`, `translate` ⇒
  `translateRThroughR2m` path, `onActivate` ⇒ `loadWebR`, `runSelf` ⇒
  `runHybridR`.

**Note on translate (do not assume — read the code):** the per-mode translate
direction and Translate/Oversett button visibility are NOT uniform across modes
today (e.g. microdata's translate action differs in direction from python/r's).
This design does **not** prescribe a single `translateToMicrodata` semantic. The
`translate` field is a placeholder for "this mode's current translate wiring,
including button visibility and label." The implementation plan MUST read the
current `updateModeButtonsUi`, `updateTranslateBtnLabel`, the Oversett-button
handler, and `doTranslate*` functions and reproduce each mode's behavior
**verbatim** — the registry only changes *where the dispatch lives*, never *what
it does*.

### File placement: inline

The registry and the three plugin objects live **inline in `index.html`**, in a
focused block next to `switchEditorMode` — NOT a new `js/modes.js`. The plugin
methods call inline functions (`highlightScriptPyR`, `runHybridR`,
`handlePythonTab`, `translatePythonThroughPy2m`, …); extracting to a separate
classic-script file would spread the implicit-global coupling across files for
zero legibility gain. Physical extraction belongs with a future ESM migration,
not Stage 1. No build step; no `window.*` surface change.

### Reserve the authoring-shell seam (do not build)

Leave a clean seam for a future jamovi ribbon without implementing one: ensure a
stable programmatic path to "load a script into a mode and run it" exists —
`switchEditorMode(id)` + the existing `setEditor(text, lang)` (in
`js/github-storage.js`) + a run function callable programmatically (not only
from the button handler). No ribbon, no statx, no jamovi.

## Out of scope

- `statx` mode (Stage 2) and jamovi (later).
- The per-segment `seg.kind` hybrid/forklar plumbing (category 2).
- Refactoring the shared segment/interpreter-core run pipeline beyond lifting the
  R/Python preludes out.
- Extracting modes to a `js/` file; ESM/Vite; `window.M2PY` consolidation.

## Verification

Behavior-preserving; the three existing modes are the test oracle. No front-end
unit harness (same as Stage 0): structural greps + manual browser checks;
`pytest` unaffected (no engine change).

- microdata / python / r each **highlight, autocomplete (Tab), run, and
  translate** identically to before.
- Mode dropdown switches correctly; switching to R still lazy-loads webR;
  Translate button shows/labels per mode as before.
- A hybrid script (mixed microdata + python segments) still runs identically
  (confirms the run-hook change didn't disturb the shared pipeline).
- No `activeEditorMode === '(microdata|python|r)'` branch remains in the routed
  call-sites (they go through `currentMode()` / `modeRegistry`). Category-2
  `seg.kind` sites intentionally remain.

## Sequencing

Stage 1 next. Then Stage 2 (`statx`) registers a 4th plugin (pyodide runtime
with its own `preRun`/`runDefault`), gated on the pdexplorer-in-Pyodide spike.
jamovi (authoring shell emitting R) comes after, using the reserved seam.
