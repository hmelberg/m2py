# Phases 4–5 of the DuckDB-data-layer direction — completion notes (2026-07-11)

Context: phases 0–3 landed the same day (see 2026-07-11-phase0-jamovilight-microdata-gating.md and 2026-07-11-phase1-duckdb-native.md). Phases 4 and 5 turned out to be mostly **absorbed by earlier phases**; this note records what was verified, what was decided, and what was deliberately deferred.

## Phase 4 — python mode's data layer via DuckDB

**Already true after phase 2/3:**
- Microdata-style imports in python-family modes flow through DuckDB-WASM + `static_data/*.parquet` by default (phase 2 flipped the default; the per-variable fallback to generation and the `// m2py: data-source=dynamic` opt-out both verified working headless).
- Plain `load <url> as df` directives fetch bytes JS-side and bind directly into pandas (`pd.read_parquet`/`read_csv` from FS bytes) — routing these through DuckDB would add a serialization hop with no benefit at typical sizes.
- `.duckdb`/`.sqlite` file loads already extract via DuckDB-WASM (`__extractDuckdbTable`) before pandas sees them.
- Assemblies with public columnar sources compile to DuckDB SQL (pushdown) and return parquet bytes — no pandas in the pipeline until the mode binds the result.

**Golden comparison (structural):** `create-dataset + import BOSATT_KOMMUNE/KJONN + tabulate kjonn` run under static (default) and dynamic (directive opt-out) in one session: both clean, identical table structure (categories + Total). Values differ by design — static is one fixed draw, dynamic regenerates (6 000 living units at the date vs 10 000 default universe).

**Decided/deferred:**
- The static-cache transfer bridge stays **JS column objects → `to_py()` → DataFrame**. Arrow IPC + pyarrow would be cleaner/faster for large imports but is not a bottleneck at the default import limit; upgrade candidate if import limits grow. (CSV was never the bridge — see the 2026-07-11 conversation.)
- **No static data regeneration** was done: rebuilding `static_data/` changes every example's numbers and is Hans's call (`build_static_data.py`, remember to bump `M2PY_VERSION` when data files change — the ?v= cache-bust keys on it).

## Phase 5 — Pyodide as lazy execution engine

**Already true after phase 1:** the boot dispatch and mode-switch warm-load are runtime-driven (`RUNTIME_FOR_MODE`): duckdb boots duckdb-wasm, r boots webR, brython boots Brython, and only python-family modes (python, microdata, statx, jamovi, safestat) warm-boot Pyodide — which is desirable for them, since the startup example auto-runs.

**Verified headless (fresh sessions, zero pyodide.asm/wheels/stdlib fetched):**
- duckdb mode: `SELECT`/`CREATE TABLE` runs natively in ~250 ms, sidebar reads the wasm catalog.
- r mode: startup example runs via webR only.
- brython mode: startup example runs via Brython only.
- Hybrid `#py → #duckdb` scripts late-boot Pyodide and run unchanged.

**Remaining (not this phase):** m2py/mockdata stay in safestat (microdata mode lives here for protected-data users) and gated-off-but-synced in openstat; hard removal is a later, evidence-based cleanup. The `<link rel="preload">` for `pyodide.js` (~small loader stub) still fetches on every page — harmless, but could be made conditional on the persisted mode if we want the last few KB.
