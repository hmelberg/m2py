# DuckDB mode — design

**Date:** 2026-06-28
**Status:** Approved design, pending implementation plan
**Scope:** v1 — a SQL execution mode. Translation (microdata↔SQL) and native-SQL privacy are explicitly deferred to later specs.

## Summary

Add a new editor mode, `duckdb`, in which the input layer is SQL text. On Run, the
SQL executes against the app's existing in-memory datasets via the **DuckDB-WASM
worker that the app already loads**, results render in the output area, and
`CREATE TABLE` statements persist their result back into the dataset store so the
new table appears in the dataset picker and is usable from the other modes
(microdata, Python, R, jamovi). The mode ships with a set of 6–9 SQL example
scripts in the Examples menu, mirroring how the R/Python/Statx modes ship examples.

The guiding principle: **pandas stays the source of truth.** DuckDB is an execution
engine that datasets are handed to and results come back from. No rewrite of the
existing pandas-based engine (`StatsEngine`, `MicroInterpreter`, `protect.py`).

## Context / what already exists (verified)

These findings make this a small, incremental feature rather than greenfield work:

- **DuckDB-WASM is already running.** `index.html:2806-2855` loads
  `@duckdb/duckdb-wasm@1.29.0` (jsDelivr ESM) into a Web Worker, memoized via
  `__duckdbPromise` / `__ensureDuckDB()`, with `__arrowToColumns(table)` to turn
  an Arrow result into a plain `{col: [values]}` object, and `window.runStaticQuery(sql)`
  which Pyodide already `await`s during a run (`index.html:7343`). Today it only
  reads hosted Parquet for static-data mode.
- **Modes that are text-only are registered inline** in `modeRegistry`
  (`index.html:3138-3185`): `microdata`, `python`, `r`, `statx`. Each is an object
  with `id`, `label`, optional `hlConfig`, `handleTab`, and `runSelf`/`runDefault`.
  The R and Statx modes use `runSelf: async (script, ctx) => …`. jamovi is the only
  *externalized* module (`js/modes/jamovi.js`) because of its ribbon UI.
- **`runSelf` returns early** at `index.html:7317`, *before* the shared
  `renderOutput` (`index.html:5251`) and `refreshDatasetSidebarFromPy(py)`
  (`index.html:6294`, line 7382) at the bottom of the run path. A `runSelf` mode
  must therefore call rendering and the sidebar refresh itself (as R/Statx do).
- **Data is a dict of named pandas DataFrames** reachable in Pyodide as
  `micro_interpreter.datasets` (alias of `e`; see `_g` at `index.html:6218` and
  `__main__.micro_interpreter` at `index.html:6120`). `micro_interpreter.datasets`
  is `{name: DataFrame}`.
- **pyarrow is available on-demand** in Pyodide (micropip, `index.html:3074-3078`),
  and `mockdata_export.py` already has a `df_to_parquet_bytes(df)` helper to reuse.
- **Two output surfaces already exist**, matching the tables-vs-datafiles split:
  text/table output via `renderOutput` with a global 30000-char truncation backstop
  (`index.html:2394`); and a Tabulator data viewer for browsing a whole dataset
  (`index.html:4114-4140`, capped at 5000 rows), reached from the dataset overview.
- **Examples are per-mode** (`index.html:29-62`): `.txt` files in `examples/`, listed
  in `#examplesDropdown` as `<div class="examples-section" data-section-mode="MODE">`
  with `<button data-example="file.txt" data-mode="MODE">`. `updateExamplesVisibility()`
  (`index.html:1876`) shows the section matching the active mode. The click handler
  (`index.html:1893-1927`) fetches the file, sets the editor, and calls
  `switchEditorMode(mode)` — but its mode whitelist (`index.html:1903`) currently
  lists only `microdata|python|r|statx` and must be extended to include `duckdb`.
- **The mode dropdown** menu lives at `index.html:377-383` (`#editorModeMenu`).
- **Syntax highlighting** is config-driven (`index.html:2653-2657`): e.g.
  `STATA_HL_CFG = { commentChar, triple, identStart, identPart, kw, fn }`. The
  highlighter (`index.html:2687`) compares a single `commentChar`; SQL line comments
  are `--` (two chars), so the highlighter needs a small `commentPrefix` extension.

## Decisions (locked)

1. **Engine: reuse the existing DuckDB-WASM worker** (not the Python `duckdb`
   package inside Pyodide). Off-main-thread, scales to large data + Parquet,
   reuses existing plumbing.
2. **Result model: explicit persist.** Datasets are registered as DuckDB views
   before a run. A bare `SELECT` previews its result (read-only); `CREATE TABLE
   name AS SELECT …` materializes `name` back into `micro_interpreter.datasets`.
3. **Input layer: text-only SQL** with SQL syntax highlighting. No ribbon in v1.
4. **Registered inline** in `modeRegistry` (like R/Statx), not as an external
   `js/modes/duckdb.js` module. The testable Python logic lives in a new
   `duckdb_bridge.py`; the browser glue (`window.__duck`) lives next to
   `runStaticQuery` in `index.html`.
5. **Ship 6–9 SQL examples** in the Examples menu, mirroring other modes.

## Architecture

### Components

| Component | Location (new/changed) | Responsibility |
|---|---|---|
| Pure SQL-parsing + parquet helpers | `duckdb_bridge.py` (new) | `split_sql_statements`, `extract_referenced_tables`, `extract_created_tables`, `build_preview_select`, `df_to_parquet_bytes` (reuse). Unit-tested with pytest. |
| Mode registration | `index.html` `modeRegistry` (inline, ~3185) | `{ id:'duckdb', label:'DuckDB', hlConfig: SQL_HL_CFG, handleTab: microdataHandleTab, runSelf }`. |
| Run orchestration | `index.html` (new `runDuckdbScript(script, ctx)`) | Loads Pyodide + pyarrow, drives the per-run flow, renders output, refreshes the dataset sidebar. |
| JS DuckDB bridge | `index.html` (near `runStaticQuery`, ~2840) | `window.__duck`: `begin/registerTable/exec/query/end` over a per-run connection. |
| SQL highlight config | `index.html` (~2657) | `SQL_HL_CFG` + a `commentPrefix` (`--`) extension to the highlighter at line 2687. |
| Mode dropdown entry | `index.html:377-383` | `<button data-mode="duckdb">DuckDB</button>`. |
| Examples whitelist | `index.html:1903` | add `mode === 'duckdb'` so example clicks switch into the mode. |
| Example files | `examples/sql01..sql0N.txt` (new) + `#examplesDropdown` section | 6–9 SQL example scripts + a `data-section-mode="duckdb"` section. |

### Data flow (per Run)

A fresh DuckDB connection per run keeps pandas the single source of truth; datasets
are re-registered each run, so there is no cross-run drift.

1. **Parse** (Python, `duckdb_bridge.py`): split the SQL into statements; compute
   `referenced` = known dataset names appearing as identifier tokens in the SQL;
   `created` = targets of `CREATE [OR REPLACE] [TEMP] TABLE name`; `preview_select`
   = the last statement if it is a `SELECT`/`WITH … SELECT`, else `None`.
2. **Register** (orchestration): `await js.__duck.begin()`, then for each
   `referenced` name, serialize its DataFrame with `df_to_parquet_bytes` and
   `await js.__duck.registerTable(name, parquetBytes)` (registers a buffer + a view
   named exactly `name`). Registering only referenced datasets avoids copying every
   dataset each run.
3. **Execute** the full SQL script for side effects: `await js.__duck.exec(sql)`
   (runs all statements in order, including `CREATE TABLE`).
4. **Preview** (a *table*): if `preview_select` is not `None`, run a capped query
   `SELECT * FROM (<preview_select>) _q LIMIT 401` via `js.__duck.query`, plus
   `SELECT count(*) … ` for the true row count. Render the first **400 rows** via
   `renderOutput`; if the count exceeds 400, append the note `"N rows — showing
   first 400. Use CREATE TABLE name AS … to save as a dataset."`. The 30000-char
   truncation (`index.html:2394`) is the backstop.
5. **Persist** (a *datafile*): for each `created` name, `SELECT * FROM "name"` via
   `js.__duck.query`, build `pd.DataFrame(cols)`, assign to
   `micro_interpreter.datasets[name]`. Datafiles are **not printed**; they surface
   in the data overview / picker (browsable via the 5000-row Tabulator viewer). If
   there is no `preview_select`, print a short confirmation per created table:
   `"Created dataset <name> (<rows> rows × <cols> cols)"`.
6. **Finish**: `await js.__duck.end()`; call `refreshDatasetSidebarFromPy(py)` so
   new datafiles appear in the overview/picker.

### The JS bridge (`window.__duck`)

A small stateful helper next to `runStaticQuery`, reusing `__ensureDuckDB()` and
`__arrowToColumns`:

```
window.__duck = {
  conn: null,
  async begin()  { const db = await __ensureDuckDB(); this.conn = await db.connect(); },
  async registerTable(name, parquetBytes) {
    const db = await __ensureDuckDB();
    await db.registerFileBuffer(name + '.parquet', new Uint8Array(parquetBytes));
    await this.conn.query('CREATE OR REPLACE VIEW "' + name +
      '" AS SELECT * FROM read_parquet(\'' + name + '.parquet\')');
  },
  async exec(sql)   { await this.conn.query(sql); },               // DDL / side effects
  async query(sql)  { return __arrowToColumns(await this.conn.query(sql)); }, // {col:[...]}
  async end()       { try { await this.conn.close(); } finally { this.conn = null; } }
};
```

`runStaticQuery` is unchanged (static-data mode keeps using it).

## Error handling

- DuckDB SQL errors are caught in `runDuckdbScript` and rendered in the output
  area as an error `<pre>` (same channel/markup as the main run path's catch at
  `index.html:7389-7398`), with the DuckDB message passed through. `js.__duck.end()`
  runs in a `finally` so the connection never leaks on error.
- A `CREATE TABLE` whose name collides with an existing dataset overwrites that
  dataset (consistent with explicit-persist intent); `CREATE OR REPLACE` is the
  recommended form and is highlighted in an example.
- Worker/instantiation failure surfaces via the existing `__duckdbPromise`
  reset-and-rethrow, rendered as a mode error.

## Testing

- **pytest (headless), TDD:** the pure functions in `duckdb_bridge.py` —
  `split_sql_statements` (quotes, `--` and `/* */` comments, trailing `;`),
  `extract_referenced_tables` (token match vs known names, case-insensitive),
  `extract_created_tables` (`CREATE`, `CREATE OR REPLACE`, `TEMP`, quoted names),
  `build_preview_select` (SELECT vs WITH…SELECT vs DDL-last → None), and the
  `df_to_parquet_bytes`→`pd.read_parquet` round-trip (dtype/null fidelity).
- **Manual in-browser** (browser-only WASM path, consistent with how Pyodide/webR/
  static-DuckDB paths are validated): bare SELECT preview + 400-row cap + note;
  `CREATE TABLE` persists, appears in the picker, usable from another mode, not
  printed; `CREATE OR REPLACE` overwrite; multi-statement script; SQL-error
  rendering; missing-dataset reference; each shipped example runs clean; the
  Examples menu shows the DuckDB section only in DuckDB mode and loads into it.

## Examples (shipped in the Examples menu)

6–9 `.txt` scripts in `examples/` (`sql01_…` … `sql0N_…`), each runnable against
the mock datasets (e.g. `person`, `person_year`, `jobb`). Planned set:

1. `sql01_select_basics` — `SELECT … FROM person WHERE … ORDER BY … LIMIT`.
2. `sql02_aggregate_groupby` — `GROUP BY` with `count`, `avg`, `sum`, `HAVING`.
3. `sql03_join` — join `person` and `jobb` (or `person_year`) on the key.
4. `sql04_create_table` — `CREATE OR REPLACE TABLE … AS SELECT …` (build a datafile).
5. `sql05_cte_window` — a `WITH` CTE + a window function (`row_number()`/`avg() OVER`).
6. `sql06_case_recode` — `CASE WHEN …` recoding into buckets.
7. `sql07_multi_statement` — create an intermediate table, then build a summary table.
8. `sql08_describe_summary` — `SUMMARIZE`/quantiles for quick profiling.

(Final count 6–9; labels in Norwegian to match the existing menu style.)

## Known limitations (v1)

- **Table names are assumed bare/unqualified.** `extract_created_tables` captures
  the first identifier after `TABLE`, so a schema-qualified `CREATE TABLE
  main.foo …` would be read as `main`. v1 has no schema/ATTACH concept (the
  catalog is cleaned to `main` each run), so this does not arise in practice;
  qualified names are unsupported.
- **The trailing `SELECT` runs up to three times per run** (once in the full
  script exec, once for the `count(*)`, once for the capped preview). Harmless
  for ordinary queries; a non-deterministic trailing `SELECT` (e.g. `random()`)
  could show a count and preview that disagree. A future optimization can fetch
  `LIMIT 401` once and derive the "more than 400" flag from the row count.
- **Preview is rendered as `to_string()` text**, not the app's HTML output-table
  styling (see data-flow step 4).
- **Browser-environment shim:** pandas' `to_parquet` triggers `patch_pyarrow()`
  which raises `ArrowKeyError` in the Pyodide pyarrow build; the run wrapper makes
  `unregister_extension_type` lenient and pre-imports the module. (Verified
  necessary via in-browser testing.)

## Out of scope (future specs)

- **microdata ↔ SQL translation.** Feasible later — the microdata DSL already maps
  to SQL (`collapse`→GROUP BY, `merge`→JOIN, `keep/drop if`→WHERE, `generate`→
  computed column) and translators already exist (`toPython`, `toMicrodata`,
  r2m/py2m). microdata→SQL is the clean direction; SQL→microdata only round-trips
  for the DSL subset.
- **Native-SQL privacy/SDC.** Not needed for v1: `CREATE TABLE` results materialize
  as pandas DataFrames, so existing `protect.py` verbs already apply to DuckDB
  output. Pushing SDC into DuckDB is a large-data optimization for later.
- **DuckDB as the general/default store.** Rejected for now: would require
  rewriting/wrapping the entire pandas-native analysis stack.
