# Design: Stage 1.x — remove the dead `btnTranslate` cluster (keep Oversett)

Status: **design** (corrected). Follow-up to Stage 1. An earlier draft of this
spec had the direction BACKWARDS — it would have removed the live **Oversett**
button and kept the hidden `btnTranslate`. Corrected after discovering the real
layout.

## The real situation (verified in-browser + CSS)

- The `<div class="toolbar">` holding `btnTranslate` is **permanently hidden** in
  this layout: `app.css` has `.panel-left .toolbar { display: none }`, and the
  toolbar always sits in `.panel-left`. So `btnTranslate` ("Translate") is never
  visible/clickable.
- The **live** translate control is **`oversettBtn`** ("Oversett") in the
  bottombar. Stage 1 already registry-routed it via
  `currentMode().translate.toPython/toMicrodata` (in the `initOversettBtn`
  handler). This is the single source of truth for the reachable translate path.
- `btnTranslate`'s click handler (calls `doTranslate*` → `renderTranslationResult`)
  and `translateAndSwitchToMicrodata` are therefore **dead code** — the reviewer's
  "unrouted gap" is dead, not a real inconsistency.
- The same hidden toolbar also holds **`btnRun`** and **`btnForklar`**, which ARE
  live (proxied by visible footer buttons like `btnRunFooter`). These must NOT be
  touched — only `btnTranslate` is removed.

## Goal

Delete the dead `btnTranslate` cluster. Keep `oversettBtn` and its registry
routing exactly as-is. Zero change to reachable behavior.

## Deletions (all verified dead)

Reference counts were traced; every one of these traces only to the hidden
`btnTranslate`:

1. The `btnTranslate` `<button>` element (in the hidden toolbar). **Leave
   `btnRun` and `btnForklar` and `leftStatus` in that toolbar untouched.**
2. The `btnTranslate.addEventListener('click', …)` handler.
3. `const btnTranslate = document.getElementById('btnTranslate');` (only used by
   that handler).
4. `updateTranslateBtnLabel()` function **and** its single call in
   `switchEditorMode` (it only set `btnTranslate`'s text).
5. The `tBtn` (`btnTranslate`) visibility lines in `updateModeButtonsUi`. **Keep
   the `oBtn`/`oversettBtn` visibility lines and the `_shows` line** — those drive
   the live Oversett button.
6. `doTranslateMicrodataToPython`, `doTranslatePythonToMicrodata`,
   `doTranslateRToMicrodata` (only called by the deleted handler).
7. `renderTranslationResult` (only called by those three). Its `lastOutput` /
   `lastOutputMode` writes are in a never-executed path; `lastOutputMode` is
   write-only anyway. No runtime impact.
8. `translateAndSwitchToMicrodata` (already callerless).
9. `btnLabel` field in the three `plugin.translate` descriptors becomes unused
   once `updateTranslateBtnLabel` is gone — drop it. **Keep `showsButton`,
   `toPython`, `toMicrodata`** (used by `updateModeButtonsUi` + `initOversettBtn`).

## Keep (live — do not touch)

`oversettBtn` + `initOversettBtn`; `plugin.translate.{ showsButton, toPython,
toMicrodata }`; `updateModeButtonsUi`'s `oBtn`/`_shows` lines; `btnRun`,
`btnForklar`, `btnRunFooter` and all run wiring.

## Out of scope

statx, jamovi, ES modules, any change to py2m/r2m output or the Oversett
rendering.

## Verification

Dead-code removal — reachable behavior unchanged.
- Oversett button still visible in Python/R, translates as before; hidden in
  microdata.
- Run / step-wise-run (forklar) still work (their hidden toolbar buttons + footer
  proxies untouched).
- No `btnTranslate` / `doTranslate*` / `translateAndSwitchToMicrodata` /
  `renderTranslationResult` / `updateTranslateBtnLabel` references remain.
- No console errors on load; `pytest` unaffected.
