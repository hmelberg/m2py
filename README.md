# m2py — microdata.no emulator

A browser app that emulates [microdata.no](https://microdata.no): it translates
microdata scripts to Python and runs them in the browser via Pyodide, generates
synthetic register data from metadata, and adds tools around it — Python/R
runners, Python/R → microdata translators, an editor that mimics microdata.no,
a step-by-step tutorial mode, and AI features (code generation, a
data-minimization/privacy review, and result interpretation).

## Layout

| Path | What |
|------|------|
| `index.html` | The front-end app shell (editor, runners, mode system, settings) + remaining inline modules. |
| `app.css`, `js/` | Extracted front-end: `app.css` (styles); `js/login.js`, `js/ai-chat.js`, `js/github-storage.js` (classic `<script src>` modules loaded after the inline block, sharing the `window.*` surface). |
| `m2py.py` | The interpreter: `MicroParser` + `MicroInterpreter` (engine, mock-data, stats, disclosure control). **Source of truth** — the `microdata-api` copy is generated. |
| `functions.py` | microdata functions used in generate/replace/if expressions. |
| `protect.py` | `scrub-*` data-protection verbs (noise, swap, k-anon, risk, …). |
| `mockdata_export.py`, `static_source.py`, `build_static_data.py` | Static synthetic-data build (Parquet/DuckDB) + the static data source. |
| `py2m/`, `r2m/` | Python→microdata and R→microdata translators (each with its own runner + tests). |
| `netlify/edge-functions/` | The AI endpoints (`dm-vurder`, `kode-svar`, `tolk-resultat`) + shared `_lib/`. |
| `manual_scripts/` | End-to-end example scripts run as a smoke suite. |
| `tests/` | pytest suite (engine, regressions, equivalence, mock-data, performance). |

A companion repo, `microdata-api` (Anvil), hosts the auth/AI backend and a
**generated** copy of the engine — see *Syncing the engine* below.

## Common commands

```bash
# Python tests (engine, regressions, equivalence, mock-data)
.venv/bin/python -m pytest tests/

# End-to-end smoke suite (exits non-zero on any CRASH/PARTIAL)
.venv/bin/python manual_scripts/run_manual_scripts.py

# Translator tests
.venv/bin/python -m pytest py2m/tests/
Rscript r2m/test_r2m.R

# Edge functions (Deno)
cd netlify/edge-functions && deno check *.ts _lib/*.ts && deno test --allow-all _lib/

# Build the static synthetic dataset (writes static_data/*.parquet + manifest.json)
.venv/bin/python build_static_data.py --persons 100000 --from 2015 --to 2023

# Propagate the engine to the microdata-api (Anvil) copy
./sync_to_api.sh            # copy; ./sync_to_api.sh --check verifies sync
```

CI lives in `.github/workflows/` (pytest + manual scripts, py2m, r2m, edge).

## Deployment

The site deploys on Netlify (`netlify.toml`): static files + the three edge
functions. `sw.js` precaches Pyodide — **bump `CACHE` whenever the precache
list changes.**

## Syncing the engine to the API

`m2py.py` and `functions.py` are the source of truth here. The copies in
`microdata-api/server_code/` are **generated** — edit the engine here, then run
`./sync_to_api.sh`. The copies carry a "GENERATED COPY — edit in m2py" header;
`./sync_to_api.sh --check` (exit 1 on drift) can gate CI.
