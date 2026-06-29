# SafeStat → remote compute-to-data: handoff brief

> **Status:** kickoff brief for a fresh session. Goal: make remote analysis real
> (send the translated script to an API service that holds the data, run it
> there, return results — data never leaves the server). Today this is a UI
> placeholder only.
>
> **Start here:** read `docs/extended-mode-architecture.md` (the standing
> guardrail) before designing anything.

## Project context

**Repo:** m2py (`/Users/hom/Documents/GitHub/m2py`) — a microdata.no emulator
that has grown a second capability: translating microdata scripts into
self-contained Python (pandas/polars) that can run on real data. "SafeStat" is
the editor mode that does this. Working branch `dev`; main is `master`.

## Two-engine architecture (the load-bearing fact)

- **Emulator** (`m2py.py`, `MicroInterpreter`) — the oracle; runs traditional
  microdata mode on deterministic mock data. Do **not** touch its logic for
  SafeStat work.
- **Translator** (`m2py_translate.py` + `m2py_runtime/`) — parses microdata,
  emits runnable pandas/polars. SafeStat runs on this. Dependency is
  one-directional: translator → emulator, never the reverse.

Three orthogonal axes the design insists on:

| Axis | What it decides | Selector |
|---|---|---|
| **Mode** | semantics (microdata vs extended) | source kind |
| **Executor** | where it runs + trust envelope | source sensitivity/location (most-restrictive wins) |
| **Backend** | pandas / polars / DuckDB | executor (size/locality) |

**Remote analysis is the Executor axis — not a new mode.** "Translate once, run
anywhere, under the envelope the source demands."

## Current state of remote

- `index.html` has `var safeStatTarget = 'local' | 'remote'` (~line 7479) with a
  manual toggle. `remote` currently just prints a placeholder warning (~7484).
  There is **no `Executor` abstraction** — it's an inline `if`. The architecture
  doc wants the target *derived from source sensitivity* (most-restrictive-source
  -wins), not toggled, behind an `Executor.run(artifact, sources)` interface.
- Translation already produces a portable artifact:
  `translate(script, backend=..., source_path=..., manifest=..., print_results=...)`
  in `m2py_translate.py` returns a runnable Python string.
- SafeStat collects results into a JSON structure (`_results`, `_figs`) in
  `runSafeStatScript` and renders them (formatted tables + plotly figures
  matching microdata styling).

## What needs designing/building (the agenda)

1. **The Executor seam** — define `Executor.run(artifact, sources) → Result`;
   make `LocalPyodideExecutor` the current path, add `RemoteApiExecutor`.
   Translate once, run via executor.
2. **The API contract** — what gets sent (translated script + source bindings +
   backend + which manifest sources), what comes back (the same
   `_results`/`_figs` JSON SafeStat already renders). Auth, errors, timeouts.
3. **The server side** — where it runs (Anvil? a Netlify function? a dedicated
   service?), sandboxing, how it loads the real data the script references.
4. **Target derivation** — manifest `sensitivity`/location implies executor; a
   sensitive source ⇒ forced remote; most-restrictive-source-wins. Replaces the
   manual toggle.
5. **Statistical disclosure control** (the safety gap) — the translated runtime
   has *none* (`m2py_runtime/__init__.py` says so explicitly); all
   suppression/winsorising lives only in the emulator (`m2py.py`,
   `_is_disclosure_control`). A compute-to-data service serving sensitive data
   must apply this server-side before returning results. The emulator is the
   oracle to mirror.
6. **Source auth & schema** — external sources may need username/password/api_key;
   variable-level schema optional (inferred if absent). Specced but thin.

## Design constraints (non-negotiable — from the architecture doc)

- Never fork the emulator; build on the translator.
- Shared surfaces (parser `MicroParser`, `m2py_runtime` ops, reused `m2py.py`
  helpers): **additive and behavior-preserving only**, guarded by the full
  pytest suite.
- No `if extended:` / no mode-branching for divergence — put it behind a
  source-kind policy object.
- Default path stays microdata/local; the untouched path is the baseline.

## Verification regimes

- Translator changes → `python -m pytest -q` (baseline: 531 passed, 1 xfailed).
- Browser changes → `node --check` on the inline `<script>` + manual reload;
  there is no JS test harness.

## Suggested first move

Start with the **brainstorming** skill on items 1–4 to produce a design doc —
the API contract and where-it-runs are genuine open questions, not yet decided.
Disclosure control (item 5) can be a parallel or follow-on spec.

## Key files

- `docs/extended-mode-architecture.md` — the guardrail (read first).
- `m2py_translate.py` — the translator (`translate(...)`, `KeyTracker`).
- `m2py_runtime/` — runtime ops (`pandas_ops.py`, `polars_ops.py`, `keys.py`,
  `manifest.py`, `sources.py`, `profile.py`).
- `index.html` — `runSafeStatScript`, `safeStatTarget` toggle (~7479).
- `m2py.py` — emulator + `_is_disclosure_control` (the disclosure-control oracle).
- `docs/superpowers/specs/2026-06-28-manifest-and-require-design.md` — manifest /
  `require` / "microdata is a source kind" design.
