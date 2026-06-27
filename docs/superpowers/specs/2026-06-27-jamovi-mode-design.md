# Design: jamovi mode (GUI analyses → R → webR → jamovi-style tables)

Status: **design**. A point-and-click, jamovi-styled analysis GUI. Built on the
Stage 1 mode registry and the existing webR runtime. The user delegated
autonomous build + test based on best recommendations; these 4 decisions were
confirmed with them:
- **Layout:** keep the app's current layout; add a jamovi-style **ribbon** on
  top (in jamovi mode) whose buttons open **analysis dialogs**; results render in
  the existing output panel ("ribbon + dialogs only").
- **Analyses (broad set):** Descriptives, Frequencies, Independent + Paired
  T-Test, Correlation Matrix, Linear Regression, One-Way ANOVA, Contingency
  Tables (χ²), Logistic Regression.
- **Data:** the engine's **active dataset** supplies the variables.
- **Results:** **jamovi-style HTML tables** (parse structured R results), degrade
  to plain text for anything unexpected.

## Core model

jamovi is an **authoring shell**, not a new language. It generates **standard R**
(base/stats — NOT the `jmv` package, which won't load in webR) and runs it on the
**existing webR runtime**. It is registered as a mode `jamovi` in `modeRegistry`.

Pipeline per analysis:
1. User picks an analysis from the ribbon → a **dialog** opens with a variable
   picker (the active dataset's columns) + role boxes + key options.
2. On Run, the dialog builds an **R command** from the role assignments.
3. The active dataset is ensured present in webR as an R data.frame `data`
   (reusing the existing engine→webR transfer used by `#r`); the R runs via webR
   (`webR.evalR(...).toJs()` for structured results).
4. The structured result is rendered as **jamovi-style HTML table(s)** in the
   output panel; the generated R is also written into the editor as visible
   "syntax" (transparency + reuse of the R runtime).

## Architecture / components

### Registry plugin `jamovi`
`modeRegistry.jamovi = { id:'jamovi', label:'jamovi', hlConfig: R_HL_CFG (the
editor shows generated R), handleTab: handleRTab, onActivate: load webR + reveal
the ribbon, translate:{showsButton:false}, runSelf: run the editor's R via the
existing R path }`. The ribbon is shown only when `activeEditorMode === 'jamovi'`.

### The ribbon (`#jamoviRibbon`, new)
A horizontal bar shown above the editor in jamovi mode, styled like jamovi:
light background, category groups each a button that opens a dropdown of
analyses. Categories → analyses:
- **Exploration**: Descriptives, Frequencies
- **T-Tests**: Independent Samples T-Test, Paired Samples T-Test
- **ANOVA**: One-Way ANOVA
- **Regression**: Correlation Matrix, Linear Regression, Logistic Regression
- **Frequencies**: Contingency Tables (χ²)

### Analysis dialogs (data-driven)
Each analysis is described by a small **spec object** `{ id, title, category,
roles:[{key,label,types,multiple}], options:[...], buildR(assign, opts) }`. One
generic dialog renderer builds the UI from the spec: a left list of the active
dataset's variables (with type icons), role boxes on the right, assign/remove
arrows, and option controls. `buildR` returns the R string. This keeps adding
analyses cheap (data, not bespoke UI per analysis).

### Variable source
The active dataset's columns + types come from the engine
(`e.datasets[active]` / the sidebar dataset info the app already computes —
`window.lastDatasetInfo` / `updateSidebarDatasets`). The dialog's variable list
and role-box type filtering use these. If there is no active dataset, the ribbon
analyses are disabled with a hint to create/import data first (e.g. run a
`#micro` block).

### Data → webR bridge
Reuse the existing engine→webR dataset transfer (the mechanism `#r` blocks use to
expose `folk` etc. as R data.frames — `sync_datasets_to_globals` + the R transfer
in `runHybridR`). The active dataset is exposed in webR under a stable name
`data` (and/or its own name) before each analysis runs. The plan must trace the
exact existing transfer and reuse it (do NOT reinvent).

### R execution + structured results
Each `buildR` produces R that computes the result and returns a structure webR
can convert: prefer building a `data.frame`/named `list` and returning it so
`webR.evalR(code).toJs()` yields JS we render. Wrap in `tryCatch` so R errors
become a readable message, not a crash. Reuse `webRShelter`.

### jamovi-style table rendering (`renderJamoviResult`, new)
Convert the toJs() structure into HTML tables matching jamovi's look: an analysis
**title**, one or more tables with a bold header row, right-aligned numerics
(formatted to sensible decimals), thin borders, subtle zebra/section lines, and a
small note line (e.g. test type, N). Rendered into the existing output panel
(reuse `renderOutput`/the output container). Plain-text fallback if the structure
is unexpected.

### v1 analyses → R (each emits base R; `data` is the active dataset)
- **Descriptives**: per selected var → N, Missing, Mean, Median, SD, Min, Max
  (`mean/median/sd/min/max`, `sum(is.na())`). Table: vars as columns or rows like
  jamovi.
- **Frequencies**: `table()` per selected (nominal) var → Levels/Counts/%/Cumulative.
- **Independent T-Test**: `t.test(dv ~ group)` (Welch default; Student via
  `var.equal=TRUE` option); report t, df, p; option Cohen's d.
- **Paired T-Test**: `t.test(x, y, paired=TRUE)`.
- **Correlation Matrix**: pairwise `cor()` + `cor.test()` p-values → matrix table
  (Pearson default; Spearman option).
- **Linear Regression**: `lm(dv ~ iv1 + iv2 + ...)` → Model Fit (R², adj R², F,
  df, p) + Coefficients (Estimate, SE, t, p).
- **Logistic Regression**: `glm(dv ~ ivs, family=binomial)` → coefficients
  (Estimate, SE, z, p) + model fit (deviance, AIC).
- **One-Way ANOVA**: `aov(dv ~ factor)` → ANOVA table (SS, df, MS, F, p); option
  Welch's via `oneway.test`.
- **Contingency Tables (χ²)**: `chisq.test(table(rows, cols))` → counts table + χ²
  test (value, df, p).

### Editor / syntax
Each run appends the generated R to the editor (visible "syntax", like jamovi's
syntax mode). The editor remains an R buffer; the existing R run still works, so
the user can tweak/re-run the R by hand. (This reuses the R `runSelf`.)

## Visual style (jamovi look)
Light, clean: ribbon with grouped category buttons and small analysis icons;
dialogs with the two-column variable-assignment layout (variable list ⇄ role
boxes) and a header; results as bordered tables with bold headers, right-aligned
numbers, an analysis title, and a muted note line. Honor the app's existing
theme variables where possible but lean to jamovi's light, table-centric look.
Reference: jamovi's Analyses ribbon + options-panel + results-panel.

## Error handling
- No active dataset → ribbon analyses disabled with a clear hint.
- webR not loaded → load on jamovi activation; show loading state.
- R error in an analysis → `tryCatch` returns a message rendered in the results
  area; other analyses keep working.
- Wrong variable type assigned to a role → dialog filters role boxes by type and
  validates before Run.

## Out of scope (v1)
- The `jmv` R package; a Data spreadsheet/editor tab; live-update-as-you-type
  (run on explicit Run/OK); plots (tables only); save/restore of analyses;
  CSV upload as the jamovi dataset (data comes from the engine's active dataset);
  Factor analysis / repeated-measures / mixed models.

## Verification
No front-end unit harness; verification is in-browser via the Chrome devtools
session + webR, plus pytest unaffected (no engine change). For EACH analysis:
build a hybrid setup (a `#micro` block → active dataset), open the dialog, assign
roles, Run, and confirm a correct jamovi-style table renders (cross-check numbers
against the equivalent R). Confirm: ribbon shows only in jamovi mode; no active
dataset → disabled with hint; microdata/python/r/statx modes unchanged.

## Build sequencing (for the plan)
1. Register `jamovi` mode + the ribbon shell (categories/dropdowns visible, webR
   lazy-load on activate, variable source wired) — no analyses yet.
2. The generic dialog renderer + analysis-spec object + the data→webR bridge +
   `renderJamoviResult`, proven end-to-end with **Descriptives** (the vertical
   slice).
3. Add the remaining analyses one per task (each = a spec object + its `buildR` +
   a result shape), tested in-browser.
4. Polish jamovi styling + empty-state + syntax-into-editor + help.
