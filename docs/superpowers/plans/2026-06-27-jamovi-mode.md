# jamovi mode Implementation Plan

> Autonomous build (user away). Controller tests each piece in-browser via the Chrome devtools + webR session. Commit per task on branch `jamovi`; do NOT merge/push — leave for user review.

**Goal:** A jamovi-styled point-and-click analysis GUI: a ribbon (in jamovi mode) whose analyses open dialogs that emit standard R, run via webR on the engine's active dataset, and render jamovi-style HTML tables.

**Architecture:** `jamovi` mode in `modeRegistry`; a `#jamoviRibbon` shown only in that mode; a generic data-driven dialog renderer fed by per-analysis spec objects (`{roles, options, buildR}`); the active dataset transferred to webR via the existing `runHybridR` base64-CSV bridge; results via `webR.evalR(...).toJs()` → `renderJamoviResult` HTML tables.

**Tech Stack:** webR (R), the Stage-1 mode registry, existing engine→webR transfer; static no-build JS/CSS.

## Global Constraints
- Emit **standard base/stats R** (NOT `jmv`). Run on the existing webR runtime + `webRShelter`.
- Data + variables come from the **engine's active dataset** (`window.lastDatasetInfo` / `e.datasets`); no spreadsheet, no CSV upload in v1.
- jamovi UI shows **only** when `activeEditorMode === 'jamovi'`; other modes untouched.
- Results = jamovi-style HTML tables (title, bold header, right-aligned formatted numbers, thin borders, note line); plain-text fallback.
- Inline JS/CSS in index.html (+ app.css). No build, no `type=module`.
- Each analysis run also appends its generated R into the editor (visible syntax; reuses R runtime).
- Verification: in-browser (controller drives webR) + pytest unaffected.

---

### Task 1: jamovi mode + ribbon shell (no analyses yet)
- Register `modeRegistry.jamovi = { id:'jamovi', label:'jamovi', hlConfig:R_HL_CFG, handleTab:handleRTab, onActivate: load webR + show ribbon + refresh variable list, translate:{showsButton:false}, runSelf: runHybridR(editorR) }`. Add a `data-mode="jamovi"` dropdown button + `editorModeBtn` title.
- Add `#jamoviRibbon` markup (hidden by default; CSS shows it only in jamovi mode): 5 category buttons (Exploration, T-Tests, ANOVA, Regression, Frequencies), each opening a dropdown listing its analyses (wired to `openJamoviAnalysis(id)`).
- jamovi-style CSS (light bar, grouped buttons, dropdowns).
- `updateModeButtonsUi` / `switchEditorMode`: toggle `#jamoviRibbon` visibility by mode; add `statx`-style editorContent/editorBP key `jamovi`.
- Empty-state: if no active dataset, ribbon analyses are disabled + tooltip "Lag/­importer data først".
- **Test:** switch to jamovi → ribbon appears (jamovi-styled), categories open dropdowns; other modes hide it; webR starts loading. Commit.

### Task 2: dialog framework + data→webR bridge + renderJamoviResult + Descriptives (vertical slice)
- `jamoviVariables()` → returns the active dataset's columns+types from `window.lastDatasetInfo[window.activeDatasetName]` (fallback: sidebar info). Used to populate dialogs.
- `transferActiveDatasetToWebR()` → reuse the `runHybridR` Phase-1 mechanism: get `e.datasets[active]` as base64-CSV from Pyodide, `read.csv(textConnection(base64enc::base64decode(...)))` into webR as `data` (apply catalog factors). Idempotent per run. (Trace the exact code at index.html ~6623–6681 and factor it into a reusable helper used by both runHybridR and jamovi.)
- Generic dialog (`openJamoviAnalysis(specId)`): modal with left variable list (type icons), role boxes (per spec.roles, type-filtered, assign/remove arrows), option controls (per spec.options), Run/Close. On Run: `spec.buildR(assignments, opts)` → R string; `await transferActiveDatasetToWebR()`; `res = (await webRShelter.captureR('{ result-building R }')...)` OR `(await webR.evalR(rCode)).toJs()`; `renderJamoviResult(spec.title, res)`; append the R to the editor.
- `renderJamoviResult(title, structure)` → jamovi-style HTML table(s) into the output panel; numeric formatting; plain-text fallback.
- **Descriptives** spec: roles `[{key:'vars', label:'Variables', types:['numeric'], multiple:true}]`; `buildR` → R that computes a data.frame of N/Missing/Mean/Median/SD/Min/Max per var and returns it. 
- **Test in browser:** make an active dataset (run a `#micro` block), switch to jamovi, Descriptives → assign vars → Run → correct jamovi table. Iterate until numbers are right. Commit.

### Task 3: Linear Regression (complex two-table result)
- Spec: roles Dependent (1 numeric), Covariates (≥1 numeric); `buildR` → `lm(dv ~ ivs, data=data)`; return list of two data.frames: Model Fit (R², adj R², F, df1, df2, p) and Coefficients (term, Estimate, SE, t, p). `renderJamoviResult` renders both tables under the title.
- **Test:** Run; cross-check against `summary(lm(...))`. Commit.

### Task 4: T-Tests (Independent + Paired)
- Independent: roles Dependent (numeric), Grouping (factor, 2 levels); options Student/Welch, Cohen's d. `t.test(dv ~ grp, var.equal=?)`. Paired: two numeric vars; `t.test(x,y,paired=TRUE)`. Result table: statistic, df, p (+ d). Test + commit.

### Task 5: Correlation Matrix
- Roles Variables (≥2 numeric); option Pearson/Spearman. `cor()` + `cor.test()` p per pair → matrix table (r above, p below or asterisks). Test + commit.

### Task 6: One-Way ANOVA + Contingency Tables (χ²)
- ANOVA: Dependent (numeric), Factor (factor); `aov(dv~factor)` → SS/df/MS/F/p table. Contingency: Rows, Cols (factors); `chisq.test(table(...))` → counts table + χ²/df/p. Test + commit.

### Task 7: Logistic Regression + Frequencies
- Logistic: Dependent (binary factor), Covariates; `glm(...,family=binomial)` → coefficients (Estimate/SE/z/p) + fit (deviance, AIC). Frequencies: nominal var(s) → `table()` → Levels/Counts/%/Cumulative. Test + commit.

### Task 8: Polish
- jamovi styling pass (ribbon icons, dialog two-column look, result-table fidelity); empty-state; help text; an `examples/`/help note. Test + commit.

## De-risking spikes (DONE — verified in-browser, use these)
- **webR structured results CONFIRMED.** `(await webRShelter.evalR(rCode)).toJs()` on an R `data.frame` returns:
  `{ type:'list', names:[<colnames>], values:[ {type:'character'|'integer'|'double', values:[...]}, ... ] }`
  (column-oriented). `renderJamoviResult` builds a table by transposing: row r = `values[c].values[r]` across columns `names`. For a multi-table result, return a NAMED `list(fit=df1, coef=df2)` in R → toJs gives `{type:'list', names:['fit','coef'], values:[<df1-list>, <df2-list>]}`; detect "value is itself a list-of-vectors" → render each as a table under its name.
- **Data→webR bridge CONFIRMED** at `index.html` ~6623–6681 (runHybridR Phase 1): Python `e.datasets` → base64-CSV (`to_csv` + b64) → webR `read.csv(textConnection(rawToChar(base64enc::base64decode(<b64>))))`, catalog labels applied as `factor()`. Factor this into a reusable `ensureDatasetInWebR(name)` for jamovi (transfer the active dataset as R `data`), shared with runHybridR.
- T1 (ribbon) DONE + visually verified (ribbon shows in jamovi mode, categories+dropdowns work).

## Self-Review
Covers spec's confirmed decisions: ribbon+dialogs only (T1), broad analyses (T2–T7), active-dataset data source + webR bridge (T2), jamovi tables (T2 `renderJamoviResult`). Risk/uncertainty flagged for execution: (a) exact `lastDatasetInfo` shape for the variable list; (b) webR `toJs()` structure for data.frames (handle in `renderJamoviResult`); (c) factoring the runHybridR transfer into a reusable helper without breaking R mode. These are traced/verified in-browser during T2 (the vertical slice) before adding analyses.

## Delivery note (autonomous)
Build T1→T2 first (framework proven end-to-end). Each later analysis is independent; partial completion (framework + a subset) is a coherent deliverable. Leave on branch `jamovi`, unmerged, with a status summary for the user.
