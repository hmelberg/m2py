# Phase 1: DuckDB mode without Pyodide — Implementation Plan

> Part of the DuckDB-data-layer direction (see 2026-07-11-phase0-jamovilight-microdata-gating.md for phase 0). Executed inline same-session by the plan author.

**Goal:** A pure-SQL duckdb-mode run never boots Pyodide. Hybrid scripts, assemblies, remote sources, `# use`, and exotic load formats fall back to the existing Pyodide path unchanged (with a late Pyodide boot).

**Why it's safe (SDC):** protection is source-based; strict/protected sources are already rejected in duckdb mode ("strict-kilder støttes foreløpig i python/r — ikke duckdb-modus"), and SQL previews already bypass the DSL protection today (`_run_duck_sql` returns raw `to_string`). The native path only ever sees public/mock data.

## Design

- `RUNTIME_FOR_MODE.duckdb: 'pyodide'` → `'duckdb'`. Mode switch then stops warm-loading Pyodide (the `runtimeForMode(newMode) === 'pyodide'` guard in `switchEditorMode`); instead the duckdb registry entry gets `onActivate: __ensureDuckDB()` to warm the SQL engine.
- New pure module `js/duckdb-native.js` (UMD pattern like `js/data-loader.js`): 1:1 JS port of `duckdb_bridge.py`'s `_scrub`, `split_sql_statements`, `extract_created_tables`, `build_preview_select` (NOT `extract_referenced_tables`/`df_to_parquet_bytes` — no pandas datasets exist in the native path), plus `formatColumnsText(cols, limit)` to replace `DataFrame.to_string(index=False)`. Tests ported from `tests/test_duckdb_bridge.py` to `tests/js/duckdb-native.test.js`.
- In the run function, right before the `activeEditorMode === 'python' || 'duckdb'` loads block:

```js
if (activeEditorMode === 'duckdb' && !py && !dashboardPendingParsed) {
  if (await maybeRunDuckNative(effectiveScript, _ctx)) return;
  py = await loadPyodideAndM2py();   // fallback: late boot, old path unchanged
  _ctx.py = py;
  _wirePyIO(py);
}
```

`_wirePyIO(p)` = the existing setStdout/setStderr wiring extracted into a closure-local helper so both the normal boot and the late boot use it.

- `maybeRunDuckNative` returns false (→ fallback) when: any hybrid segment (`parseHybridScript` kind !== 'duckdb'); any `# use` directive; assembly spec present; any remote/registered source; any load format outside parquet/csv/duckdb/sqlite; duckdb/sqlite load without a `table`. It throws the existing html-load error directly (same UX as today).
- Native execution mirrors `_run_duck_sql` exactly: strip directive lines → scrub-empty check → `__duck.begin()` → register loads (parquet via `__duck.registerTable`, csv via new `__duck.registerCsv` using `read_csv_auto`, duckdb/sqlite via `__extractDuckdbTable` → parquet) → `__duck.exec(fullSql)` → preview = last SELECT/WITH statement: count + LIMIT 400 → text table; created tables reported from the catalog ("Opprettet datasett …") → `__duck.end()` in finally → `refreshDatasetSidebarFromDuck()` → `lastOutput` + `renderOutput(text, false, false)` (statx precedent). Sidebar levels via `window.__setDatasetLevel`/`SessionContext.noteFetchedLoad`, both feature-guarded with `if (window.X)` so the identical function body ports to openstat/microdata.

**Accepted behavior delta (documented):** a table CREATEd in a *native* SQL run is no longer auto-materialized into `e.datasets` (pandas), so a *later* python-mode run must fetch it with `# use <name> from duckdb` instead of referencing it bare. This only affects sessions that ran SQL before ever booting Python (if Pyodide is already up, `!py` routes to the old path and semantics are 100% unchanged). Cross-runtime transfer via `use` matches how r↔python already works, and the sidebar/`use from duckdb` read the catalog, which remains the duckdb-mode source of truth.

## Tasks

1. **safestat:** add `js/duckdb-native.js` + `tests/js/duckdb-native.test.js` (ported tests must pass), wire `index.html` (RUNTIME_FOR_MODE, onActivate warm-load, `_wirePyIO` extraction, `__duck.registerCsv`, `maybeRunDuckNative` + dispatch branch). Run `node --test tests/js/*.test.js`. Manual smoke: fresh tab → SQL mode → run `SELECT 1 AS x;` → network shows duckdb-wasm but NO pyodide download; hybrid example (sql10 py→duckdb) still runs via fallback (pyodide boots late).
2. **openstat:** copy `js/duckdb-native.js` + test file verbatim; apply the same `index.html` edits (structure identical; guards make SessionContext-less environment safe). Tests + commit.
3. **microdata:** same as openstat. Tests + commit.
4. Push all three repos.
