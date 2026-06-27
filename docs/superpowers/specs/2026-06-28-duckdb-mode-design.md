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
(microdata, Python, R, jamovi).

The guiding principle: **pandas stays the source of truth.** DuckDB is an execution
engine that datasets are handed to and results come back from. No rewrite of the
existing pandas-based engine (`StatsEngine`, `MicroInterpreter`, `protect.py`).

## Context / what already exists

These findings (verified in the codebase) make this a small, incremental feature
rather than greenfield work:

- **DuckDB-WASM is already running.** `index.html:2806-2855` loads
  `@duckdb/duckdb-wasm@1.29.0` (jsDelivr ESM) into a Web Worker, memoized via
  `__duckdbPromise` / `__ensureDuckDB()`, and exposes `window.runStaticQuery(sql)`
  which Pyodide already `await`s during a run. Today it only reads hosted Parquet
  for static-data mode. The engine, worker, Arrow→columns bridge, and the
  Pyodide↔JS call path are all in place.
- **Modes are a clean registry.** `modeRegistry` + `M.registerMode()` in
  `index.html` (~3138–3310), lazy-loaded modules (`MODE_MODULES`), with a single
  execution dispatch point at `currentMode().runSelf()` (~`index.html:7317`).
  jamovi (`js/modes/jamovi.js`) is the reference for a lazy-loaded mode with its
  own JS+CSS.
- **Data is already a dict of named pandas DataFrames.** `self.datasets = {}`,
  `self.active_name`, with `use` / `create-dataset` / multi-dataset support and an
  active-dataset picker. This maps 1:1 onto DuckDB named tables.
- **pyarrow is available on-demand** in Pyodide (installed via micropip when
  Parquet is used: `index.html:3074-3078`), so Arrow IPC round-trips are feasible.
- **Two output surfaces already exist**, matching the tables-vs-datafiles split:
  text output via `renderOutput` with a global 30000-char truncation backstop
  (`index.html:2394`); and a Tabulator-based data viewer for browsing a whole
  dataset (`index.html:4114-4140`, capped at 5000 rows, "Viser X av Y rader"),
  reached from the dataset overview / picker.

## Decisions (locked)

1. **Engine: reuse the existing DuckDB-WASM worker** (not the Python `duckdb`
   package inside Pyodide). Off-main-thread, scales to large data + Parquet,
   reuses existing plumbing. The cost is an Arrow-IPC copy across the
   Pyodide↔worker boundary — the same cost `runStaticQuery` already pays.
2. **Result model: explicit persist.** Datasets are auto-registered as DuckDB
   tables before a run. A bare `SELECT` previews its result in the output area
   (read-only). `CREATE TABLE name AS SELECT ...` materializes `name` back into
   `self.datasets`.
3. **Input layer: text-only SQL** with SQL syntax highlighting. No ribbon in v1.

## Architecture

### Components

| Component | Location (new/changed) | Responsibility |
|---|---|---|
| Mode spec | `js/modes/duckdb.js` (new) | Registers the `duckdb` mode: label, SQL highlighting config, `handleTab`, `runSelf`. |
| Mode styles | `css/modes/duckdb.css` (new) | Minimal styling for SQL highlighting / result tables, consistent with existing modes. |
| Module registration | `index.html` `MODE_MODULES` + mode dropdown | Register the lazy-loaded module and add a `data-mode="duckdb"` menu entry. |
| JS bridge | `index.html` (generalize `runStaticQuery`) | New `window.runDuckSql({ sql, inputs })` that registers Arrow inputs, runs SQL, returns Arrow results + created table names. |
| Python glue | `m2py.py` (or a small new module) | Table-name parsing, dataset→Arrow IPC serialization, results Arrow→DataFrame, materialize-back into `self.datasets`. |

### Data flow (per Run)

A fresh DuckDB connection is used per run so DuckDB never becomes a second source
of truth — pandas datasets are re-registered each run and there is no cross-run
drift.

1. **Parse** the SQL to extract referenced table names (identifiers that match
   existing dataset names).
2. **Register** only the referenced `self.datasets[...]`: serialize each to Arrow
   IPC bytes in Pyodide (pyarrow), pass to `window.runDuckSql` as
   `inputs = { tableName: arrowIpcBytes }`. Registering only referenced tables
   avoids copying every dataset on every run (important for large data).
3. **Execute** the SQL, supporting multiple `;`-separated statements run in order.
4. **Return** results as Arrow IPC back to Pyodide, plus the list of table names
   created via `CREATE TABLE`.
5. **Render** each/the final `SELECT` result as a short **table** preview in
   `#outputArea` via the existing `renderOutput`. The intent is that `SELECT`
   produces *short tables*; bulk data should be written to a datafile instead
   (step 6). Preview cap: **400 rows**. When the result exceeds the cap, show the
   first 400 rows plus a note: `"N rows — showing first 400. Use CREATE TABLE
   name AS … to save as a dataset."` The existing global 30000-char truncation
   (`index.html:2394`) remains the backstop.
6. **Persist** any `CREATE TABLE name AS ...` result back into `self.datasets[name]`
   (Arrow→pandas) as a **datafile**. Datafiles are *not printed* as output — they
   surface in the existing data overview / dataset picker and are browsable via
   the existing Tabulator data viewer (`index.html:4114-4140`, capped at 5000
   rows with a "Viser X av Y rader" note). Bare `SELECT` previews only — it does
   not mutate `self.datasets`.

### The JS bridge

Generalize the existing `window.runStaticQuery` into:

```
window.runDuckSql({ sql, inputs })
  // inputs: { [tableName]: ArrayBuffer(arrowIpc) }
  // returns: { results: [ArrayBuffer(arrowIpc), ...], created: [tableName, ...] }
```

It reuses `__ensureDuckDB()` (worker already memoized), registers each input via
`insertArrowFromIPCStream` on a fresh connection, runs the SQL, collects result
sets and created-table names, and closes the connection. `runStaticQuery` remains
for static-data mode (or becomes a thin wrapper).

## Error handling

- DuckDB SQL errors are surfaced in the output area in the same error channel
  the other modes use (red text), with the DuckDB message passed through.
- A referenced table that has no matching dataset produces a clear
  "no dataset named X" message that lists the available dataset names.
- Worker/instantiation failures fall back to the existing `__duckdbPromise`
  reset-and-rethrow behavior, surfaced as a mode error.

## Testing

- **pytest (headless):** the Python-side glue is unit-testable without a browser —
  table-name parsing, dataset→Arrow IPC→DataFrame round-trip fidelity (dtypes,
  nulls), and the materialize-back-into-`self.datasets` logic.
- **Manual in-browser:** the worker/WASM execution path is verified manually,
  consistent with how the app's other browser-only paths (Pyodide, webR,
  static-data DuckDB) are validated. Manual checks: bare SELECT preview;
  CREATE TABLE persists and appears in the picker; the created table is usable
  from another mode; SQL error rendering; missing-table error; multi-statement
  script; SELECT preview cap (400 rows) + nudge note; datafile (CREATE TABLE)
  appears in the data viewer and is NOT printed to the output area.

## Out of scope (future specs)

- **microdata ↔ SQL translation.** Very feasible later — the microdata DSL already
  maps to SQL (`collapse`→GROUP BY, `merge`→JOIN, `keep/drop if`→WHERE,
  `generate`→computed column) and translators already exist (`toPython`,
  `toMicrodata`, r2m/py2m). microdata→SQL is the clean direction; SQL→microdata
  only round-trips for the DSL subset.
- **Native-SQL privacy/SDC.** Not needed for v1: because `CREATE TABLE` results
  materialize as pandas DataFrames, the existing `protect.py` verbs already apply
  to DuckDB output. Pushing SDC (k-anonymity, suppression, binning,
  hash-pseudonymize — all SQL-expressible) into DuckDB is a large-data
  optimization for later.
- **DuckDB as the general/default store.** Rejected for now: would require
  rewriting/wrapping the entire pandas-native analysis stack. Possible long-term
  direction, not a starting point.
