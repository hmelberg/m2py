# Dashboard view — interactive, shareable result pages from plain scripts

**Date:** 2026-07-09
**Applies to:** SafeStat (source of truth) → ported to OpenStat
**Status:** design, pending implementation plan

## Summary

A script can declare `#options.view = dashboard` and become a shareable,
interactive dashboard: input widgets (slider, dropdown, checkbox) bound to
runtime variables, output cells rendered as cards in a responsive grid, and
live re-execution of affected cells when a widget changes. A recipient opens
a URL (`…/#dodsarsaker`, resolved through a names registry, or an existing
dotted/`output=` link), sees the dashboard skeleton immediately, and watches
the cards fill as the runtime loads and cells run. The recipient never sees
code unless they click "show code".

Primary audience: **passive recipients** — a researcher authors a script,
shares a URL, a decision-maker sees a polished dashboard. Interaction model:
**live re-execution** in the browser runtime (Pyodide/webR), not precomputed
results.

Everything is comment directives, so a dashboard script is still a plain,
runnable script in the normal split view.

## Design constraints (agreed)

1. **Isolation.** All new code lives in `js/dashboard.js` + `css/dashboard.css`.
   Removing the `<script>` tag must leave the app exactly as today. Integration
   with the rest of the app is four narrow surfaces (see *Module contract*).
2. **Open data only in v1.** Dashboards execute locally against open sources.
   Remote/strict execution, encrypted sources, and key dialogs are out of scope
   (the directive architecture lets them in later without syntax changes).
3. **Small widget set.** Three widgets. The risk in this feature is scope creep
   toward a BI tool, not the tech.
4. **Framework: home-built.** Dash needs a server (incompatible with the static
   architecture). Panel via `panel convert` is Python-only (kills r/duckdb
   modes), pulls in the Bokeh stack, and bypasses the directive philosophy.
   The home-built layer reuses five existing subsystems (see *Reuse map*).

## Reuse map (what already exists)

| Capability | Existing anchor |
|---|---|
| Script options parsing | `extractScriptOptions()` — `index.html:6700` (`#`/`//`/`--` markers) |
| Output-only view toggle | `#options.view = output-only` handling — `index.html:9573` |
| Autorun from URL + trust gate | `NotebookLinks.classifyHash` / `autorunNeedsGate` — `js/notebook-links.js` |
| Dotted-ref → raw URL | `NotebookLinks.resolveDotted` — `js/notebook-links.js:25` |
| Data loading directives | `# load … as df` — `js/data-directives.js` (setup zone uses these as-is) |
| Run machinery (py/r/duckdb) | existing run flow in `index.html`, wrapped as `ctx.run` |
| Output rendering (plots/tables/text) | existing output renderer, wrapped as `ctx.renderOutput` |
| Widget-line parsing precedent | `ForklarWidgets.parseWidgetLine` — `widgets/forklar-widgets.js` (pattern, not reused directly) |
| i18n | existing layer, injected as `ctx.t` |
| deno test convention | `data-directives.test.ts` style (eval the IIFE, test pure functions) |

## 1. Syntax

Three directive families, all comments in the mode's comment marker
(`#`, `//`, `--` — same triple as `extractScriptOptions`).

### 1.1 View options

```python
#options.view = dashboard
#options.title = "Dødsårsaker i Norge"
#options.description = "Utforsk utviklingen 1990–2024"   # optional subtitle
```

### 1.2 Input widgets — `#input <var> = <type>(…)`

```python
#input year = slider(1990, 2024, step=1, default=2020)
#input cause = dropdown("Kreft", "Hjertesykdom", "Ulykker")
#input per100k = checkbox(default=True, label="Per 100 000 innbyggere")
```

- The variable becomes an ordinary variable in the runtime scope.
- `label=` optional everywhere; defaults to the variable name.
- `slider`: positional min, max; `step` (default 1), `default` (default min).
  Values are always numbers.
- `dropdown`: positional string choices; `default` (default: first choice).
- `checkbox`: `default` (default False). Values are booleans.
- v1 has exactly these three. No free-text input (see *Security*). No
  `dropdown(from=data)` (v1.1).

### 1.3 Cells — `#%% Name[, wide][, row=<name>][, tab=<name>][, deps=<vars>]`

`#%%` is the VS Code/Spyder/Jupytext cell convention. The cell name is the
card title. Attributes after commas:

- `wide` — card spans the full grid width (default: half, flowing 2-across).
  Norwegian alias `bred` accepted (and `halv` for the default).
- `row=<name>` — consecutive cells sharing a row name render side by side,
  splitting the width evenly (KPI rows; generalizes `wide`/`half`).
- `tab=<name>` — consecutive cells with `tab=` form one tab set; the value is
  the tab label. A cell without `tab=` closes the set. Multiple cells may
  share a tab. Hidden tabs re-run lazily (on first open).
- `deps=<var>[+<var>…]` — manual override of the automatic dependency
  analysis. Normally unnecessary.

Code before the first `#input` is the **setup zone** (data loading, prep) and
runs once. Code between the widget block and the first `#%%`, or without any
`#%%` markers at all, still works: each output-producing segment becomes an
unnamed, auto-numbered card, and every widget change re-runs everything below
the changed widget (the always-correct floor semantics).

No nested containers, no explicit widths, no begin/end blocks. `row=` and
`tab=` may combine on one cell later without a syntax break.

## 2. Module contract (isolation)

All new logic in `js/dashboard.js` (parsing, dependency graph, re-run
orchestration, dashboard DOM inside one container node it is handed) and
`css/dashboard.css` (builds on `app.css` variables; theme inherited).

Exactly four integration surfaces:

1. **Activation** (~5 lines, `index.html`): where the run flow checks
   `view === 'output-only'`, add a branch: `view === 'dashboard'` →
   `Dashboard.mount(container, script, ctx)`, skip normal output rendering.
2. **`ctx.run(code) → Promise<{outputs, error}>`** — the existing run
   machinery wrapped. Dashboard knows nothing about Pyodide/webR/DuckDB;
   modes, the safestat gate, and strict handling stay where they are.
3. **`ctx.renderOutput(outputs, node)`** — the existing output renderer.
   Tables/plots look identical in dashboard and split view, fixed in one place.
4. **Name lookup** (~10 lines, `js/notebook-links.js`): one new
   `classifyHash` case (see §4). The registry fetch itself lives in
   dashboard.js (or a tiny `names.js`).

Also injected: `ctx.t` (i18n). No changes to editor, forklar-widgets,
data-directives, modes, or AI layer.

## 3. Execution model

### Startup

1. Hash → (name lookup →) script fetched via existing autorun flow, including
   the safestat trust gate.
2. `view=dashboard` detected → `Dashboard.mount()` renders the **full skeleton
   immediately**: title, widgets at their defaults, empty cards with titles and
   a loading shimmer. Structure visible in <1s while the runtime loads behind a
   progress line ("Laster Python … Henter data …").
3. Setup zone runs once (load directives materialize as today).
4. Cells run in document order; each card fills as its result arrives. Cells
   in hidden tabs are deferred until the tab opens.

### On widget change

1. The variable is set in the runtime scope with a single assignment statement
   via `ctx.run` (`year = 2021` / `year <- 2021` — the mode's translation
   layer knows which). Values are serialized safely: numbers as numbers,
   booleans as the mode's literal, strings JSON-encoded.
2. Invalidation analysis (§3.1) picks the cells to re-run; they run in
   document order. Affected cards dim with a spinner; unaffected cards are
   untouched.

### Debounce and queueing

Changes are collected for ~250 ms before running. At most **one pending run**:
new changes while a run is in flight replace the pending one (only the latest
values matter), so dragging a slider never builds a queue. Runs are strictly
sequential — one runtime, no concurrency.

### 3.1 Invalidation (which cells re-run)

Layered semantics with correctness as the floor:

1. **No `#%%` cells** → re-run everything below the changed widget.
2. **With cells** → conservative automatic text analysis: a cell re-runs if it
   mentions the changed widget variable as a word, or mentions a name assigned
   in a cell that itself re-runs (transitive invalidation). Assignment
   detection is per-mode regex (python `name =`/`name +=`; R `name <-`/`name =`).
   If the analysis cannot be confident (e.g. `globals()`, `assign()`, exec),
   fall back to re-running everything below — always correct.
3. `deps=` overrides the analysis for that cell.

False positives cost a redundant run; false negatives are prevented by the
conservative fallback. The analysis is one pure function
(script → dependency graph), deno-tested with a table of script → expected
re-run set.

### Errors

- **Setup-zone error** → the dashboard is replaced by a single error card with
  the message and an "Åpne i editor" link (switches to split view with the
  script loaded; debugging happens there, not in the dashboard).
- **Cell error** → the message renders inside that card; the rest of the
  dashboard stays alive. Cards depending on the failed cell (per the graph)
  are marked "utdatert" instead of showing stale numbers as if valid.

A discreet "Vis koden" link at the bottom opens the script in normal view —
transparency is half the point.

## 4. Names registry

One file, `names.json`, in a dedicated small GitHub repo (e.g.
`hmelberg/dashstatlink`), fetched by **both** apps — one registry, not one per
app. Deliberately dumb format:

```json
{
  "dodsarsaker": "hansmelberg.demo.dodsarsaker.py",
  "kommunehelse": "https://raw.githubusercontent.com/ola/helse/main/kommune.py"
}
```

Values are dotted refs or raw URLs — exactly what
`classifyHash`/`resolveDotted` already understand. The registry is an alias
layer only; downstream resolution is untouched. (An object form with metadata
— title, author — can be added later; values may be string *or* object.)

### Lookup flow

1. `#dodsarsaker` → `classifyHash` sees a single `[a-z0-9-]+` token without
   dots → `{action: 'name', name: …}`. No collision with today's forms:
   `s=`/`url=`/`output=` are checked first, and dotted refs need ≥4 tokens —
   a single token currently returns `null`, so this claims a free case.
2. `names.json` fetched from raw.githubusercontent (~5 min GitHub cache).
   Response cached in localStorage as a fallback when the fetch fails.
3. The value is re-classified and enters the **existing autorun flow** —
   including the safestat gate. A name behaves like the `#output.` form
   (recipients see results, not the editor); the script's `#options.view`
   decides output-only vs dashboard.
4. Unknown name → friendly error page ("Fant ikke ‘…’ i navneregisteret")
   linking to the registry.

### Registration and trust

Registration is a commit/PR to the registry repo — curation and history for
free; deliberately no self-service (that is what would require a writable
backend). Known weakness, accepted: a name points at a URL the author
controls, so content can change after registration — the same trust model as
sharing any link, with the safestat gate as the execution backstop. Content
pinning (commit-hash in the dotted branch slot) is a natural v2.

## 5. Security

No new doors:

1. **Execution**: dashboards open no new execution path — same autorun,
   same safestat gate; the name form inherits the gate by construction (§4).
2. **Widget values** are the one new injection surface (values are embedded in
   an executed assignment). Hence: slider → always numbers, checkbox → always
   booleans, dropdown → author-authored strings JSON-encoded into the
   assignment. **No free-text widget in v1** — that is the widget that would
   make this a real injection problem.
3. **DOM**: titles/labels set via `textContent`, never innerHTML (same
   discipline forklar-widgets enforces); outputs go through the existing
   `ctx.renderOutput` path and its sanitization. The registry is fetched from
   one fixed URL and its values can only become raw.githubusercontent URLs or
   what the `url=` form already allows today.

## 6. Testing

- **deno unit tests** (`dashboard.test.ts`, style of `data-directives.test.ts`)
  for the pure functions: `#input`/`#%%`/options parsing, dependency graph +
  invalidation (table-driven), name-hash classification, debounce/queue state
  machine.
- **Living example**: one dashboard script in `examples/` — documentation and
  manual test in one, verified in py and r modes.
- **Isolation test**: remove `<script src="js/dashboard.js">` → the app must
  be identical to today.

## 7. Explicitly not in v1

All have a syntax-compatible path in later:

- duckdb/jamovi modes (needs `${var}` text substitution — v1.1)
- remote/strict execution and encrypted sources (agreed: open data first)
- free-text widget, date picker; `dropdown(from=data)` (v1.1)
- nested containers, explicit column widths
- self-service name registration; pinning names to commits
- static/precomputed export

## 8. Footprint

`js/dashboard.js` (~600–900 lines), `css/dashboard.css` (~150),
`dashboard.test.ts`, one example script, the `names.json` repo, and ~15
integration lines across `index.html` and `js/notebook-links.js`.
