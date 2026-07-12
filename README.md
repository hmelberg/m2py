# SafeStat — browser statistics workbench (full build)

> Sister projects: [OpenStat](https://github.com/hmelberg/openstat) — the open,
> simplified edition (no login, no protected/encrypted sources, no remote
> execution, BYOK-only AI) — and
> [Microdata](https://github.com/hmelberg/microdata) — the dedicated
> microdata.no emulator (persona locked on, UI tracking microdata.no; cloned
> from openstat 2026-07-10 with full git history, so `git cherry-pick` works
> across the repos). The engine (`m2py.py`) is the source of truth here;
> fixes land in SafeStat first and are ported to the siblings.

A browser app for running statistics scripts in several languages — microdata,
Python, R, DuckDB, Brython, jamovi, Statx, SafeStat (remote) — with the
microdata language powered by an engine that emulates
[microdata.no](https://microdata.no): it translates microdata scripts to Python
and runs them in the browser via Pyodide, and generates synthetic register data
from metadata. Around it: Python/R runners, Python/R → microdata translators,
a step-by-step tutorial mode, and AI features (code generation, a
data-minimization/privacy review, and result interpretation). Microdata is an
ordinary mode here (its special UI shows only while microdata mode is active);
the always-on emulator experience lives in the `microdata` sibling repo. The
default mode is chosen per subdomain (`js/notebook-links.js` `hostnameMode()`),
with **python** as the fallback.

## Layout

| Path | What |
|------|------|
| `index.html` | The front-end app shell (editor, runners, mode system, settings) + remaining inline modules. |
| `app.css`, `js/` | Extracted front-end: `app.css` (styles); `js/login.js`, `js/ai-chat.js`, `js/github-storage.js` (classic `<script src>` modules loaded after the inline block, sharing the `window.*` surface). |
| `m2py.py` | The interpreter: `MicroParser` + `MicroInterpreter` (engine, mock-data, stats, disclosure control). **Source of truth** — the `microdata-api` copy is generated. |
| `functions.py` | microdata functions used in generate/replace/if expressions. |
| `protect.py` | `scrub-*` data-protection verbs (noise, swap, k-anon, risk, …). |
| `mockdata_export.py`, `static_source.py`, `build_static_data.py` | Static synthetic-data build (Parquet/DuckDB) + the static data source. |
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
# Edge functions (Deno)
cd netlify/edge-functions && deno check *.ts _lib/*.ts && deno test --allow-all _lib/

# Build the static synthetic dataset (writes static_data/*.parquet + manifest.json)
.venv/bin/python build_static_data.py --persons 100000 --from 2015 --to 2023

# Propagate the engine to the microdata-api (Anvil) copy
.venv/bin/python sync_to_api.py --apply   # copy; without --apply it only reports drift

# Diff delte kjernefiler mot søsken-repoene (../openstat, ../microdata)
sh scripts/sync_check.sh                  # exit 1 ved avvik; UI-filer er bevisst utelatt
```

CI lives in `.github/workflows/` (pytest + manual scripts, edge).

## Examples

Built-in examples live in `examples/<mode>/` — one folder per editor mode
(`micropython/`, `microdata/`, …), with an optional one level of `NN_category/`
subfolders (e.g. `microdata/03_deskriptiv_statistikk/`) that become categories
in the modal. Add or remove a file, then regenerate the manifest:

```bash
# Rebuild examples/manifest.json from the folder tree
.venv/bin/python examples/generate_manifest.py
```

The «Eksempler» button opens a mode-scoped modal built from
`examples/manifest.json` (fetched lazily the first time the modal opens — no
startup cost). Each example's label comes from a `# label: <text>` line in the
file (else `#options.title`, else the filename). No `index.html` edit is
needed to add or remove examples.

## Deployment

The site deploys on Netlify (`netlify.toml`): static files + the three edge
functions. `sw.js` precaches Pyodide — **bump `CACHE` whenever the precache
list changes.**

## Syncing the engine to the API

`m2py.py` and `functions.py` are the source of truth here. The copies in
`microdata-api/server_code/` are **generated** — edit the engine here, then run
`sync_to_api.py --apply`. The copies carry a "GENERATED COPY — edit in m2py"
header; running `sync_to_api.py` without `--apply` reports drift (can gate CI).
