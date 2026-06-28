# DuckDB hybrid segments — design

**Date:** 2026-06-28
**Status:** Approved design, pending implementation plan
**Builds on:** `2026-06-28-duckdb-mode-design.md` (the v1 DuckDB mode)

## Summary

Make DuckDB a **first-class hybrid segment kind** so SQL can be mixed with other
languages in one script, in both directions:

- **In DuckDB mode:** a leading `#micro` and/or `#py` block runs first (in the
  normal engine) to build datasets, then the SQL runs against them — so an
  example can be self-contained: build a dataframe, then use DuckDB to derive a
  smaller one from it.
- **In microdata / Python / R modes:** a `#duckdb` block runs SQL against the
  datasets those scripts built.

This replaces the v1 bespoke `runDuckdbScript` (`runSelf`) execution path with a
**single shared DuckDB executor** used by the normal hybrid dispatcher, so there
is exactly one DuckDB execution path regardless of host mode.

## Context / what exists (verified)

- **Hybrid parsing already exists.** `matchHybridMarker(trimmed)` (`index.html:5596`)
  recognizes `#micro`/`#py`/`#r`/`#stata` (also `//`/`##` spellings);
  `parseHybridScript(text, defaultMode)` (`index.html:5605`) splits a script into
  ordered `{kind, text}` segments.
- **The shared Pyodide segment loop** (`index.html:7600-7625`, built inside
  `getInterpreterCorePython`) dispatches `microdata` (`e.run_script[_async]`) and
  `pyodide` (`_exec_pyodide_block`) segments, calling `e.sync_datasets_to_globals(_g)`
  after each so later segments see new datasets. Output is `print`ed to stdout,
  captured, and rendered once via `renderOutput` (`index.html:7627-7635`).
- **R has its own hybrid path**, `runHybridR(src, py, runOpts)` (`index.html:6776`),
  which runs `#micro` segments first (Pyodide) then R (webR).
- **DuckDB v1 currently bypasses all of this**: `modeRegistry.duckdb` uses
  `runSelf: runDuckdbScript`, which runs the whole editor as one SQL program via
  `__DUCK_RUN_PY` and the `window.__duck` bridge, rendering directly with
  `renderOutput`. The bridge helpers — `window.__duck`, `__ensureDuckDB`,
  `__arrowToColumns`, `__decimalToNumber`, `__ensureDuckBridge` (lazy-loads
  `duckdb_bridge.py` into Pyodide) — stay; only the orchestration moves.
- **`duckdb_bridge.py`** (pure, pytest-tested) provides `split_sql_statements`,
  `extract_referenced_tables`, `extract_created_tables`, `build_preview_select`,
  `df_to_parquet_bytes` — unchanged by this work.
- **The v1 runtime correctness fixes must be preserved** in the moved executor:
  the pyarrow `patch_pyarrow` shim, per-run catalog clean, created-name exclusion
  from view registration, Decimal/HUGEINT handling, and the 400-row preview.

## Decisions (locked)

1. **Unified approach:** DuckDB is a hybrid segment kind, not a bespoke runner.
2. **Markers:** `#duckdb`, with aliases `#duck` and `#sql` (and `//`/`##` spellings,
   consistent with the other markers).
3. **DuckDB mode** becomes `runDefault: 'duckdb'` (no `runSelf`); unmarked text is
   SQL. `#micro`/`#py` preambles run first because segments execute in order.
4. **One shared executor** `_run_duck_sql(sql)` (Python, defined in the interpreter
   core) holds all DuckDB orchestration; the segment loop and `runHybridR` both
   call it. Output flows through stdout → the normal renderer.
5. **Scope of hosts:** `#duckdb` works in microdata, Python, **and R** modes;
   DuckDB mode accepts `#micro` and `#py` preambles. `#r`/`#stata` preambles
   inside DuckDB mode are out of scope (see below).

## Architecture

### Components / changes

| Component | Location | Change |
|---|---|---|
| Marker recognition | `index.html:5596` `matchHybridMarker` | Add `if (/^(\/\/|##?)\s*(duckdb|duck|sql)\s*$/i.test(trimmed)) return 'duckdb';` |
| Shared executor | `getInterpreterCorePython` (near `show`/`to_microdata` defs) | Define `async def _run_duck_sql(sql)` — the v1 `__DUCK_RUN_PY` logic as a function returning the text to print (preview table or "Opprettet datasett …"), reading/writing `e.datasets`. |
| Segment loop | `index.html:7600-7625` | Add `elif _k == "duckdb": print(await _run_duck_sql(_st)); e.sync_datasets_to_globals(_g); _apply_labels_to_globals(_g, catalog); _g["show"]=show; _g["to_microdata"]=to_microdata` |
| Run setup | main run fn, before `py.runPythonAsync(runCode)` (~`index.html:7627`) | If any segment is `duckdb`: `await __ensureDuckBridge(py)` and ensure pyarrow (the ensure logic moved out of `runDuckdbScript`). |
| Mode spec | `modeRegistry.duckdb` (~`index.html:3230`) | Remove `runSelf`; add `runDefault: 'duckdb'`. Keep `hlConfig: SQL_HL_CFG`, `handleTab`. |
| R host | `runHybridR` (`index.html:6776`) | Add handling so `duckdb` segments call `_run_duck_sql` via Pyodide (alongside the existing micro-then-R flow). |
| Remove | `runDuckdbScript` + `__DUCK_RUN_PY` | Folded into `_run_duck_sql`; delete the bespoke path. |
| Examples | `examples/` + dropdown | Add hybrid examples (see below). |

### Data flow (any host mode)

1. `parseHybridScript(script, runDefault)` → ordered segments. In DuckDB mode the
   default kind is `duckdb`; in Python mode `pyodide`; etc.
2. If any segment is `duckdb`, ensure the bridge module + pyarrow once (JS).
3. The shared Pyodide loop runs segments **in order**: `microdata`/`pyodide`
   segments build/modify `e.datasets`; each `duckdb` segment calls
   `_run_duck_sql`, which sees the datasets built by earlier segments.
4. `_run_duck_sql(sql)` (per call): clean the DuckDB catalog; register only the
   referenced datasets (minus any the SQL creates) as views from Parquet;
   `exec` the SQL; build a ≤400-row preview of the trailing SELECT; materialize
   each `CREATE TABLE` back into `e.datasets`; return the text to print
   (preview, or "Opprettet datasett …" when there is no trailing SELECT).
5. The loop `print`s that text and re-syncs datasets to globals so later `#py`
   segments see new tables. The run path renders stdout once and calls
   `refreshDatasetSidebarFromPy`.

### Behavior preservation

A DuckDB-only script (no markers) parses to a single `duckdb` segment → one
`_run_duck_sql` call → identical behavior to v1 (same preview, same persistence,
same fixes). The v1 in-browser scenarios remain valid regression checks.

## Error handling

`_run_duck_sql` formats DuckDB/SQL errors concisely (the existing "pick the line
containing `Error:`" logic) and raises a clean exception. A failing segment
aborts the run and is rendered by the normal run-path catch — consistent with how
a failing `#micro` segment aborts today. The catalog connection is always closed
in a `finally` inside `_run_duck_sql`.

## Testing

- **pytest:** `duckdb_bridge.py` is unchanged; its 18 tests still pass. No new
  pure-Python logic.
- **Manual in-browser** (the matrix that matters here):
  1. DuckDB-only script (regression) — preview + CREATE TABLE persist, unchanged.
  2. DuckDB mode with a `#micro` preamble that builds a dataset, then SQL derives
     a smaller one from it.
  3. DuckDB mode with a `#py` preamble (build a DataFrame in pandas) then SQL.
  4. Python mode with a `#duckdb` block over a DataFrame built in `#py`/`#micro`.
  5. R mode with a `#duckdb` block over a `#micro`-built dataset.
  6. Error in a `#duckdb` segment renders concisely and aborts the run.
  7. New tables from a `#duckdb` segment are visible to a following `#py` segment
     and in the dataset sidebar.

## Examples (added to the menu)

Self-contained hybrid scripts (Norwegian labels, consistent with the menu):
- `sql09_micro_then_sql` — `#micro` builds a dataset via import/generate, then a
  `#duckdb` block builds a smaller extract from it.
- `sql10_py_then_sql` — `#py` builds a pandas DataFrame, then `#duckdb` derives a
  summary table from it.
- `pyNN_sql_block` (Python-mode example) — a Python script with a `#duckdb` block,
  listed under the Python examples, demonstrating the reverse direction.

(Comment symbol reminder for authors: DuckDB/SQL uses `--` and `/* … */`, not `#`.)

## Out of scope

- **`#r`/`#stata` preambles inside DuckDB mode.** A `#duckdb` block inside R mode
  is in scope (R host), but running webR/Stata *as a preamble to* DuckDB mode is
  deferred (heavier runtimes; little demand).
- **Sharing temporary tables across separate `#duckdb` segments.** Each segment
  cleans the catalog and runs independently; a temp table made in one `#duckdb`
  block is not visible to a later `#duckdb` block unless persisted via
  `CREATE TABLE` (which lands in `e.datasets` and is re-registered).
- **The large-data v2 work** (file-output sink, external-source catalog,
  microdata→SQL translation) — tracked separately; see [[duckdb-large-data-aim]].
