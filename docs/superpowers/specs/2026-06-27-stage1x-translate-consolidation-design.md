# Design: Stage 1.x — consolidate translate to one registry-routed path

Status: **design**. Follow-up to Stage 1 (mode registry, merged). Closes the
translate consistency gap the Stage 1 whole-branch review flagged, and removes
the dead/duplicate translate code uncovered while investigating it.

## Context (what's actually there)

`index.html` has **two** translate buttons, plus dead code:

- **`btnTranslate`** ("Translate" / "→ Microdata", main toolbar) — the LIVE
  button. Its click handler dispatches `if activeEditorMode === 'microdata' →
  doTranslateMicrodataToPython() else if 'python' → doTranslatePythonToMicrodata()
  else → doTranslateRToMicrodata()`. The `doTranslate*` functions render via the
  shared `renderTranslationResult` and set `lastOutput`/`lastOutputMode`. This
  handler was NOT registry-routed in Stage 1.
- **`oversettBtn`** ("Oversett", `display:none` by default) — a near-duplicate.
  Its handler (`initOversettBtn`) was routed in Stage 1 through
  `plugin.translate.toPython/toMicrodata`, with its own inline-HTML render.
- **`translateAndSwitchToMicrodata`** (defined ~line 3203) — **dead**: defined,
  never called. Stage 1 routed it pointlessly.

Both buttons are **hidden in microdata mode** and shown only in Python/R
(`updateModeButtonsUi` toggles both). Therefore the microdata→Python paths
(`doTranslateMicrodataToPython` and `oversettBtn`'s `toPython`) are **unreachable**
today. The only reachable translate is Python/R → microdata, served redundantly
by two buttons via two render paths.

## Goal

One translate button, one path, registry-routed. Remove the dead and duplicate
code. Behavior for the reachable paths is preserved (Python/R → microdata via the
surviving Translate button, rendered exactly as `btnTranslate` does today).

## Design

### Consolidated `plugin.translate`

Replace Stage 1's `{ showsButton, btnLabel, toPython, toMicrodata }` descriptors
with:

```js
translate: { showsButton, btnLabel, run? }
```
- `microdata` → `{ showsButton: false, btnLabel: 'Translate' }` (no `run`; button
  hidden, exactly as today).
- `python` → `{ showsButton: true, btnLabel: '→ Microdata', run: doTranslatePythonToMicrodata }`.
- `r` → `{ showsButton: true, btnLabel: '→ Microdata', run: doTranslateRToMicrodata }`.

### Call-site changes

- **`btnTranslate` click handler** — replace the `if/else if` chain with:
  ```js
  const t = currentMode().translate;
  if (!t || !t.run) return;
  // keep existing: disabled guard, try { await t.run(); } catch {…} finally { btnTranslate.disabled = false; }
  ```
  Preserve the handler's existing disabled-guard, try/catch error rendering, and
  finally-re-enable exactly.
- **`updateModeButtonsUi`** — remove the `oversettBtn` (`oBtn`) visibility lines;
  toggle only `btnTranslate` via `currentMode().translate.showsButton` (unchanged
  logic, minus the second button).
- **`updateTranslateBtnLabel`** — unchanged (already reads
  `currentMode().translate.btnLabel`).

### Deletions (all dead or redundant)

- `translateAndSwitchToMicrodata` function (dead — no callers).
- `doTranslateMicrodataToPython` function (unreachable — microdata button hidden).
- `initOversettBtn` IIFE (the `oversettBtn` handler).
- the `oversettBtn` `<button>` element in the HTML.
- Stage 1's `toPython` / `toMicrodata` fields on the plugins (only consumed by the
  two things being deleted).

### Update

- The variable-detail help text (~line 2416) currently says *"**Oversett**-knappen
  konverterer Python/R til microdata-syntaks."* — change to reference the
  **Translate** button (the surviving control). Keep meaning, update the name.

### Keep

`doTranslatePythonToMicrodata`, `doTranslateRToMicrodata`, `renderTranslationResult`.

## Behavior outcome (preservation statement)

- Python/R → microdata translation works via the **Translate** button, rendered
  via `renderTranslationResult` exactly as `btnTranslate` does today.
- Microdata mode still shows **no** translate button.
- The duplicate **Oversett** button is gone (intended).
- No reachable behavior is removed: the only deletions are dead functions and an
  unreachable button path.

## Out of scope

- Any change to what `doTranslatePythonToMicrodata` / `doTranslateRToMicrodata`
  actually produce (py2m/r2m output unchanged).
- statx, jamovi, ES modules, the wider roadmap.

## Verification

Behavior-preserving for reachable paths; no front-end unit harness (greps +
manual browser; `pytest` unaffected).
- Python mode: Translate button visible, labelled "→ Microdata", click →
  microdata rendered in output via `renderTranslationResult`, as before.
- R mode: same via r2m; "WebR ikke klar" guard preserved.
- Microdata mode: no translate button (Translate hidden, Oversett gone).
- No `oversettBtn` / `initOversettBtn` / `translateAndSwitchToMicrodata` /
  `doTranslateMicrodataToPython` references remain.
- `btnTranslate` handler has no `activeEditorMode === '…'` branches.
- No console errors on load; help text reads "Translate".
