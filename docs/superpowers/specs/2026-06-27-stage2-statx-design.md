# Design: Stage 2 — `statx` mode (Stata-like, via pdexplorer in Pyodide)

Status: **design**. Stage 2 of the split/registry arc. Adds a 4th editor mode,
`statx`, that runs Stata-style commands in the browser via **pdexplorer** on
Pyodide. Builds on the Stage 1 mode registry.

## Feasibility — settled by spike (do NOT re-litigate)

The original premise (`micropip.install('pdexplorer')`) FAILS: pdexplorer 0.0.40
pins `pandas==1.3.5`, `pyarrow==13.0.0`, `statsmodels==0.14.0` (no wasm wheels)
and drags in desktop-only `xlwings`/`pynput`. **But** a spike proved it works
with this recipe (verified live in the app's Pyodide, Python 3.13):

1. `micropip.install('pdexplorer', deps=False)` — installs the pure-Python wheel,
   skipping its pinned deps.
2. Use Pyodide's **bundled recent** wasm builds: pandas **2.3.3**, numpy 2.2.5,
   statsmodels **0.14.4**, scipy 1.14.1, matplotlib 3.8.4 (already present).
3. `micropip.install(['rich','click','requests'])` — pdexplorer's pure-Python
   import-time deps.
4. Inject `MagicMock` stubs for `pywintypes`, `xlwings`, and `pynput` into
   `sys.modules` BEFORE importing (pdexplorer imports xlwings/pynput at top level;
   xlwings pulls pywintypes; all desktop-only and unused here). NOTE: verified from
   a *clean* Pyodide — a recipe derived from a dirty session missed xlwings.
5. `import pdexplorer` → OK. Run scripts via **`pdexplorer.do(inline=<raw Stata>)`**,
   which executes multi-line Stata syntax and prints Stata-style output (verified:
   `summarize`, `generate`, `regress`, `tabulate` all ran on pandas 2.3.3 with
   zero errors and correct output, including command echo `. summarize x`).

pdexplorer exposes Stata commands as module functions (`summarize`, `regress`,
`tabulate`, `gen`/`generate`, `egen`, `collapse`, `drop`, `keep`, `describe`,
`browse`, `do`, …). The `do(filename=None, inline=None)` entry runs raw Stata —
`inline=` for a string (a bare-string arg is treated as a filename, so always use
`inline=`).

## Goal

`statx` mode: the user writes raw Stata syntax (optionally in a hybrid script with
a `#micro` data block), runs it via pdexplorer, and sees Stata-style output —
consistent with how python/r modes work today.

## Architecture

### Registry fit (Stage 1)

`statx` is a 4th `ModePlugin` registered in `modeRegistry`:
- `id: 'statx'`, `label: 'Statx'`.
- `hlConfig`: a minimal Stata-keyword highlight config (new; can start small).
- `handleTab`: minimal autocomplete (Stata keyword list; parity with python not
  required for v1).
- `runSelf(script, ctx)`: statx runs through pdexplorer, NOT the microdata segment
  pipeline — so it uses the `runSelf` short-circuit path (like R's `runHybridR`).
- `onActivate`: lazy-load pdexplorer on first switch into statx (mirror R's
  `loadWebR` / `loadPy2m`).
- No `translate` action in v1 (no `stata2m` translator) → the Oversett/translate
  button is **hidden** in statx mode (`translate: { showsButton: false }`), exactly
  like microdata.

### Loading (`loadPdexplorer`, new — mirrors `loadPy2m`/`loadWebR`)

A lazy loader, called on first statx activation/run, idempotent (cached promise):
runs the 5-step recipe above against the app's existing Pyodide (`loadPyodideAndM2py`).
Sets a `pdexplorerReady` flag. Shows status while loading.
- **Not service-worker precached** — pdexplorer + rich/click/requests are fetched
  from PyPI via micropip at runtime, so first statx use needs network. Document
  this (offline caveat); consistent with how other lazy Pyodide packages are
  handled.

### Hybrid data integration (`#micro` + `#stata`)

statx participates in the hybrid model like python/r: a `#micro` block creates
named datasets (via the engine), and a `#stata` block runs on them. A new segment
marker `#stata` (alias `#statx`) is recognized. In statx editor mode, unmarked
code defaults to stata (mirrors python mode, where unmarked code defaults to
pyodide).

The engine already exposes each `#micro`-created dataset (e.g. `folk`) as a pandas
DataFrame in the Pyodide environment — that is how `#python` accesses `folk`.
statx reuses this: it resolves a dataset name to that DataFrame and hands it to
pdexplorer.

> **Verify first (plan-time spike):** the EXACT mechanism by which a
> `#micro`-created dataset becomes a named pandas DataFrame is in
> `getInterpreterCorePython` / the hybrid run path and has NOT yet been traced.
> The plan's first step must read that code and confirm how to obtain `df_NAME`
> for `pdexplorer.use()` (e.g. is `folk` a global in the Pyodide namespace after
> the `#micro` segment runs? is there an engine accessor?). If the bridge is not
> as assumed, the `#micro`→statx data hand-off may need its own small mechanism —
> resolve this before building the `use NAME` runner.

### The `use NAME` model (current-dataset selection)

Stata has a single *current* dataset; commands operate on it implicitly; `use`
switches it. statx implements this:

- The statx block is **parsed by us** (not blind-passed to `do`): split at each
  `use NAME` line into chunks `(datasetName, commands)`.
- For each chunk, in order: resolve `NAME` → the engine's DataFrame, call
  `pdexplorer.use(df_NAME)` (pdexplorer's native `use`, given a df — we resolve
  the name because pdexplorer's `use` otherwise expects a file path), then
  `pdexplorer.do(inline=<that chunk's commands>)`, capturing stdout in order.
- **`use` is optional.** A statx block with no `use` runs against the **active
  dataset** (`activeDatasetName` / the last `#micro`-created dataset). `use NAME`
  is the way to switch among multiple datasets.
- `use NAME` is idiomatic Stata (bare name, like `use auto`); the app's named
  datasets are the "working directory" namespace. Chosen over `sysuse`/`webuse`
  (example/web connotations) and frames (advanced, unsupported).

### v1 dataset-state rules (locked)

- **Fresh reload on each `use`:** every `use NAME` loads the engine's DataFrame
  fresh. `generate`/`replace` persist within a chunk (one `do` call); switching
  away and back with `use` gives the original again. Caching modified datasets
  across switches is a v1.x add.
- **No write-back to the engine:** statx analyses/derives in place but does not
  push modified data back so a later `#python` block sees it. Analysis-mostly for
  v1; bidirectional sync is separate.

### Output rendering

Capture pdexplorer's stdout from each `do(inline=…)` chunk and render through the
existing output path (`renderOutput`). pdexplorer uses `rich`, which emits plain
text when not attached to a TTY (verified). If any ANSI escapes appear, strip
them. Concatenate chunk outputs in order. Plots (seaborn/matplotlib) are secondary
— out of scope for v1 (text output only).

## Error handling

- Loader failure (network / PyPI down): statx run shows a clear "kunne ikke laste
  statx-motoren (pdexplorer)" error; other modes unaffected.
- `use NAME` where NAME is not a known dataset: clear error naming the missing
  dataset and the available ones.
- A pdexplorer command error inside a chunk surfaces the Stata/pdexplorer error
  text in the output (do not abort the whole UI).

## Out of scope (v1)

- `stata2m` (statx → microdata translation) and any translate button in statx.
- Plots/graph commands (text output only).
- Write-back of statx-modified data to the engine; cross-`use` modification
  caching; true simultaneous in-memory frames.
- Rich autocomplete / full Stata syntax highlighting (minimal is fine).
- Service-worker precaching of pdexplorer.

## Verification

No front-end unit harness (greps + manual browser; engine `pytest` unaffected).
Plus a small set of in-browser smoke checks:
- Switching to statx lazily loads pdexplorer once (status shown), no console
  errors; switching away/back does not reload.
- A hybrid script — `#micro` creating `folk`, then `#stata` with `summarize`,
  `generate`, `regress`, `tabulate` — runs and renders Stata-style output.
- Multiple datasets: `#micro` creates `folk` and `hus`; a `#stata` block with
  `use folk` … `use hus` … runs each chunk against the right dataset.
- A statx block with no `use` runs against the active dataset.
- `use NOTADATASET` shows a helpful error.
- microdata/python/r modes unchanged (registry regression).

## Sequencing (suggested for the plan)

1. `loadPdexplorer` loader + a thin "run a stata string on a df" Python helper
   (the spike recipe, hardened) — testable in isolation first.
2. Register the `statx` plugin (label, hlConfig, handleTab, onActivate, runSelf
   with no-`use` default = active dataset).
3. `#stata` segment marker + the `use NAME` parser/splitter + name→DataFrame
   resolution + multi-chunk run.
4. Output capture/rendering + error handling.
5. Minimal Stata highlight + dropdown entry + docs/help.
