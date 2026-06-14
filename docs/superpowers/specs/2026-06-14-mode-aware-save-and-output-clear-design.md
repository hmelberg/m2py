# Design: Mode-aware GitHub save guard + output clearing

Date: 2026-06-14
Status: Approved (pending written-spec review)
Branch: dev

## Goal

Two small, independent safety/UX fixes in `index.html`:

1. **B — prevent cross-mode overwrite.** The editor has three independent
   per-mode content buffers (`editorContent.microdata/.python/.r`), but the
   filename (`scriptName`) and GitHub binding (`cur = {repo, branch, path}`) are
   global. Quick-save (`doSave`) writes the *active mode's* buffer to `cur.path`,
   guarding only repo/branch — not mode/extension. So switching to Python while
   bound to a microdata `.txt` and quick-saving silently overwrites the `.txt`
   with Python. Make save and the save indicator mode-aware so this can't happen.
2. **Output clearing.** Loading/selecting a new script does not clear the output
   container, leaving stale output from the previous script. Clear it on load.

## Non-goals

- No per-mode filename/binding restructuring (Alternative A) — `cur` and
  `scriptName` stay global. Possible later follow-up.
- No output clearing on mode switch (a mode switch is not a new script).
- No edge-function changes.

## Current behavior (verified)

- `switchEditorMode` (index.html:4103) swaps `editorContent[mode]` into the
  textarea; does not touch `cur`/`scriptName`/the indicator.
- `cur` is a single localStorage object via `getCurrent`/`setCurrent` (10611).
- `doSave` (10961) writes `si.value` (active buffer) to `cur.path`; only guards
  `cur.repo === s.repo && cur.branch === s.branch` (10969).
- `updateCurrentIndicator` (10749) shows the floppy `ghSaveIcon` whenever
  `cur.path` is set, with `ghIsDirty()` state — no mode check. After a mode
  switch, `ghIsDirty()` is true (new buffer ≠ saved snapshot), so the icon shows
  "dirty" and invites the overwrite.
- `langFromPath(p)` (10386): `.py`→python, `.r`→r, else→microdata.
- `setEditor` (10375) is called only by load paths (URL/GitHub/recent/shared);
  it does NOT clear output. The "Oversett" flow does not use `setEditor`.
- Example loaders set `scriptInput` directly (microdata examples ~2871,
  web_examples ~2967) and do not clear output.
- `clearOutput()` (3291) already exists and is idempotent.

## Design

### B — mode-aware save

A single predicate gates save + indicator on extension matching the mode:

- **New helper** `curMatchesMode()`:
  `const c = getCurrent(); return !!(c && c.path && langFromPath(c.path) === activeEditorMode);`
- **`doSave`:** before the existing repo/branch guard's `putFile`, add: if a
  `cur` exists but `langFromPath(cur.path) !== activeEditorMode`, call
  `openSaveAs()` and return (never overwrite a mismatched-extension file).
- **`updateCurrentIndicator`:** show `ghSaveIcon` only when `curMatchesMode()`
  (else hide it, exactly as when nothing is bound). This removes the misleading
  "dirty" state and the overwrite invitation while in a non-matching mode.
- **`switchEditorMode`:** call `updateCurrentIndicator()` at the end so the icon
  hides/shows correctly on every mode switch.
- **`openSaveAs` on mismatch:** pre-fill a mode-appropriate filename
  (`scriptName` value + extension by mode: microdata→`.txt`, python→`.py`,
  r→`.r`) instead of the mismatched `cur.path`, so the dialog does not re-suggest
  the overwrite. When the mode matches `cur.path` (normal case), keep the
  existing pre-fill behavior.

`cur` is never cleared on mode switch — switching back to the matching mode
restores the binding and normal quick-save automatically.

### Output clearing

Call `clearOutput()` at the genuine "load a new script" entry points:
- inside `setEditor` (covers URL/GitHub/recent/shared loads),
- in the microdata example loader (~2871) and the web_examples loader (~2967),
  which set `scriptInput` directly without `setEditor`.

Not in `switchEditorMode`.

## Error handling / edge cases

- No GitHub connection: `doSave` already routes to settings/Save-As — unchanged.
- Extensionless file → `langFromPath` returns `microdata`; matches microdata
  mode. Fine.
- `clearOutput()` is idempotent — safe to call when output is already empty.
- Save-As pre-fill: if `scriptName` is empty, fall back to `script` + extension.

## Testing

No JS test harness in the project → manual verification:
1. Open a microdata `.txt` from GitHub → floppy visible, quick-save works.
   Switch to Python → floppy hidden; menu "Lagre" routes to Save-As (no
   overwrite), pre-filled with a `.py` name. Switch back to microdata → floppy
   and normal quick-save restored.
2. Load an example and a GitHub file → output container is empty afterwards.
3. Microdata quick-save unchanged when the mode matches the bound file.

## Rollout / rollback

- Additive guards + clear calls in `index.html`. Rollback = revert the diff.
