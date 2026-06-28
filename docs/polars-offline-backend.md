# Offline polars / pandas backend (`m2py_runtime` + `m2py_translate`)

Translate a microdata.no script into a **standalone, runnable Python program**
that executes *outside* the browser — using **polars** (lazy + streaming, for
larger-than-memory data) or **pandas**. The in-browser emulator is unchanged;
this is a new, purely additive code path for offline / large-data analysis.

Branch: `feature/polars-offline-backend`.

## Why

polars' streaming engine, multithreading, and real-file access only exist
*natively* — they cannot run in Pyodide (the streaming engine doesn't build for
wasm). So polars belongs in an **offline translator**, not in the browser
emulator. The emulator stays on pandas; this backend emits code you run on a
server / worker / your own machine where polars' strengths are real.

## Quick start

```python
import pandas as pd
import m2py_translate as T

df = pd.DataFrame({"kommune": [1, 2, 1, 2], "inntekt": [10., 20, 30, 40]})

# 1) get the runnable program as a string (this is what you send to a worker/API)
code = T.translate(
    "generate logi = log(inntekt)\n"
    "collapse (mean) inntekt -> snitt, by(kommune)",
    backend="polars",        # or "pandas"
    source_path=None,        # None = operate on in-memory `data`/`df`; or "extract" -> extract.parquet
)
print(code)

# 2) or translate + execute locally in one call (convenience for testing)
out = T.run(script, {"df": df}, backend="polars")   # returns a polars DataFrame
```

With `source_path="extract"` the emitted program is fully self-contained:
`pl.scan_parquet("extract.parquet") -> ... -> collect(engine="streaming") ->
write_parquet("result.parquet")`.

## Anvil / API integration (later)

The design target is "send the microdata script as a string to an endpoint that
runs polars". Keep the trust boundary at the **DSL**, not arbitrary Python:

```python
# server side (Anvil server module / Uplink / FastAPI):
import m2py_translate as T
def run_microdata(script: str, parquet_path: str) -> str:
    code = T.translate(script, backend="polars", source_path=parquet_path)
    exec(compile(code, "<m2py>", "exec"), {})   # writes result.parquet
    return "result.parquet"
```

Accept the **script** (constrained microdata DSL) and translate server-side —
never accept arbitrary Python over the wire. For sensitive register data, run
the worker *next to the data* (Anvil Uplink / on-prem), so only the script
crosses the network, not the data.

## Supported verbs

| Category | Verbs |
|---|---|
| Datasets / session | `create-dataset`, `use`, `clone-dataset`, `rename-dataset`, `delete-dataset` |
| Labels (no-op on data) | `define-labels`, `assign-labels`, `drop-labels`, `list-labels` |
| Shaping | `generate`, `replace`, `recode`, `keep`, `drop`, `rename`, `destring`, `reshape-to-panel`, `reshape-from-panel` |
| Aggregation | `collapse`, `aggregate` |
| Merge | `merge X on K` (symmetric), `merge vars into TARGET on K` (into-form, via `merge_into`); join key resolved + baked at translate time |
| Analysis (side output) | `summarize`, `tabulate`, `correlate`, `normaltest`, `ci`, `anova`, `hausman`, `summarize-panel`, `tabulate-panel`, `transitions-panel` |
| Regression (coef table) | `regress`, `logit`, `probit`, `poisson`, `negative-binomial` |
| Panel / IV (coef table) | `regress-panel` (fe/re/be/pooled), `regress-panel-diff` (diff-in-diff), `ivregress` (2SLS) |
| Other models | `mlogit` (multinomial), `rdd` (regression discontinuity, sharp/fuzzy) |
| Predict (adds columns) | `regress-predict`, `logit-predict`, `probit-predict`, `negative-binomial-predict`, `mlogit-predict`, `ivregress-predict`, `regress-panel-predict` |
| Survival (lifelines) | `cox`, `kaplan-meier`, `weibull` |
| Plots (side output) | `histogram`, `barchart`, `scatter`, `boxplot`, `piechart`, `hexbin`, `sankey`, `coefplot` |

Analysis and plot verbs honour a trailing `if <cond>` (rows are filtered for the
computation via the `keep` op, without changing the working frame), and they
match the emulator's per-verb statistics. **`correlate`** matches the emulator:
by default rows with any missing value are dropped (listwise) before Pearson
correlation; `pairwise` keeps them (pairwise correlation); `covariance` returns
the covariance matrix (`sig`/`obs` text/extra-column variants are deferred).
**`tabulate`** drops the missing category by default and keeps it with `missing`,
for both one-way and two-way tables (this corrected an emulator bug where the
one-way path kept missing by default — `m2py.py` was fixed to match the two-way
path and convention). The long output omits zero-count combinations that the
emulator's wide crosstab shows explicitly (format, not data).
The **regression family** (`regress`/`logit`/`probit`/`poisson`/
`negative-binomial`) fits via statsmodels exactly as the emulator does and
returns a coefficient table `[term, coef, se, t, p]` (verified against the
emulator's summary output; `noconstant` supported, `or`/`irr`/`robust`/`exposure`
deferred). **Survival** (`cox`/`kaplan-meier`/`weibull`) uses lifelines as the
emulator does: `cox` returns `[term, coef, hazard_ratio, se, z, p]`,
`kaplan-meier` the survival function `[time, survival]`, `weibull` the fitted
`lambda`/`rho` (+`n`/`events`). **`rdd`** uses the `rdrobust` package when present
(returning the Conventional/Bias-Corrected/Robust estimates, matching the
emulator's preferred path) and falls back to local-polynomial OLS otherwise —
unlike the in-browser engine, the offline target can install rdrobust. In
particular **`summarize`** mirrors
the emulator's two paths exactly (verified against `StatsEngine`): ungrouped →
`mean, std, count, p1, p25, p50, p75, p99` (percentiles incl. median, no min/max);
grouped (`by`) → `mean, std, min, max, count`; `gini`/`iqr` append in either path.
Note: the emulator's **disclosure control** (winsorising before mean/std,
3-sig-fig percentile rounding) is *not* reproduced — the offline backend reports
raw statistics, matching the emulator with disclosure control off.

**Control flow.** `for … end` loops and `let` bindings are resolved at translate
time: loops are **unrolled** (microdata loops are statically unrollable — no
nested for-blocks; `;` separates nested levels, space zips) and `$name`/`${expr}`/
`++` substitution reuses the emulator's own `_substitute_bindings`, so the
flattened script translates exactly as the emulator would run it.

**Multiple datasets.** Scripts that switch the active dataset (`create-dataset
A` … `use B` …) translate faithfully: the active dataset is resolved *statically*
at translate time (it's fixed by the script text), so each command is emitted on
a per-dataset variable `df_<name>` / `lf_<name>`, mirroring the emulator's
`datasets` dict + `active_name`. `use`/`create-dataset` switch the active frame,
`clone-dataset`/`rename-dataset` map to variable assignment, and `merge` of an
already-created dataset references its variable directly. The final active
dataset is what's collected/written. (One semantic note: offline
`create-dataset N` *loads* the extract `N.parquet` / `datasets["N"]`, since
`import` is out of scope — whereas the in-browser engine makes an empty frame
that `import` then populates.)

Coverage on the repo's real `manual_scripts/` + `examples/`: **186/187 (99%)**
of these verbs translate. `import`/session plumbing is intentionally out of
scope — point the offline script at a parquet/CSV extract you already have
(e.g. one DuckDB mode built).

**Implicit merge keys.** microdata merges implicitly on the entity/relative key;
pandas and polars need an explicit join column. The translator resolves each
`merge`'s key *at translate time* and bakes a literal `left_on`/`right_on`,
using the **same resolver the emulator uses** (`m2py_runtime/keys.py:
resolve_merge_key`, which the emulator's merge handler also calls — single source
of truth). A static `KeyTracker` walk maintains each dataset's columns and its
collapse key, and builds an `alias → registry-path` map from the script's own
`import` lines so cross-entity **person-ref FNR linkage** (mother/father/owner →
`PERSONID_1`) is detected without a live catalog. The two merge forms are
emitted distinctly: `merge X on K` updates the active frame (symmetric key);
`merge vars into TARGET` updates the target via `ops.merge_into`, which mirrors
the emulator's dedup/suffix/drop column handling (always a left-join). When a key
can't be resolved, the line is baked with a best guess and flagged
`# TODO: verify join key` — never silently wrong. This brings family / sibling /
job-to-person linkage scripts (previously out of scope) into coverage; e.g.
`merge snittlønn_søsken ant_søsken into bosatte on søskennr` bakes
`left_on='søskennr', right_on='søskennr'`.

**Input resolution + emulator fallback.** In in-memory mode the emitted program
resolves each input dataset through a `_load(name)` helper: it returns
`datasets[name]` when the caller provides it, else — only when the runtime
`allow_emulated` flag is set — synthesises a base population via the emulator
(`ops.emulate_import`), else raises `KeyError`. `translate(..., allow_emulated=)`
sets that flag's default in the emitted file; an Anvil caller can still override
it before running. This lets a generated script run end-to-end for testing before
real data is wired in, while never silently faking data in production.

**In the app.** The hamburger menu's **“Vis offline Python”** (pandas / polars)
translates the current script and shows the standalone program in the output
pane — the artifact you hand to Anvil. (polars translation needs the `polars`
package, which isn't always available in the browser; pandas always works there,
and polars runs fine offline.)

**Expressions** (for `generate`/`replace`/`if`): **all 85 microdata functions are
supported.** The polars `exprcompile` maps the element-wise ones natively (stays
lazy) — arithmetic/comparisons/boolean, math+trig (`log`/`exp`/`sqrt`/`sin`/
`acos`/…), strings (`substr`/`lower`/`trim`/`startswith`/…), row-wise
(`rowmean`/`rowmax`/`rowtotal`/`rowmissing`/…), `inlist`/`inrange`/`logit`,
`np.where`. Anything it can't express natively (scipy distributions like
`chi2tail`/`ttail`/`normal`, date construction, label functions) falls back at
runtime to the emulator's own pandas evaluator (`materialise → eval → re-lazy`),
so the result is identical to the browser. Only a **genuinely unknown function
name** is emitted as `# UNTRANSLATED` — never silently-wrong code.

**Options** are guarded by a per-verb allow-list (`HANDLED_OPTIONS`): a verb
honours `by()` (collapse/aggregate/summarize/tabulate), `outer_join`/`on()`
(merge), `gini`/`iqr` (summarize), `missing`/`freq`/`cellpct`/`rowpct`/`colpct`/
`chi2`/`top`/`bottom` (tabulate), `force` (destring), and the `if` condition
everywhere. Any *other* option on a line — e.g. tabulate `nolabels`/`rowsort`/
`summarize()`, correlate `sig`, destring `dpcomma` — makes the line
`# UNTRANSLATED` rather than being silently ignored. Two-way `tabulate x y` is
supported (via args); percentages are `0-100` columns within any `by` group;
`chi2` adds `chi2`/`chi2_p`/`chi2_dof` (scipy chi-square, two-way); `top(n)`/
`bottom(n)` keep the first/last n categories of the first variable (positional,
value-sorted — same as microdata/the emulator; bare `top` -> 10). List all gaps (unknown verb, expression, or option) for a script with
`m2py_translate.unsupported(script)`.

## Architecture

```
microdata script ──MicroParser──► instruction dicts (IR) ──m2py_translate──► program string
                                                              │
                          ┌───────────────────────────────────┴────────────────┐
              backend="pandas"                                       backend="polars"
        m2py_runtime/pandas_ops (eager pd.DataFrame)        m2py_runtime/polars_ops (lazy pl.LazyFrame)
        reuses m2py._py_eval_expr (emulator fidelity)       m2py_runtime/exprcompile (expr -> pl.Expr)
```

- **TRANSFORM** verbs reassign the working frame (`df`/`lf`).
- **ANALYSIS** verbs compute a side result, `print` it, and leave the frame
  unchanged (matching the emulator). polars analysis sinks `collect()` and
  delegate to the tested pandas implementation; the lazy/streaming benefit is in
  the transform pipeline.
- **PLOT** verbs build a `plotly` Figure into `fig_<n>` (the same library the
  emulator uses, so offline charts equal the in-browser ones — verified by
  comparing every trace's x/y to `m2py.PlotHandler`). File mode emits
  `fig_<n>.write_html("plot_<n>.html")`; `fig.to_json()` gives the spec for an
  API. Supported:
  - `histogram` — numeric (`bin(n)`, default 30; `percent`/`density` histnorm)
    or categorical/`discrete` value-counts (`percent`)
  - `barchart` — single-var `count`/`percent`, or a numeric `(mean|median|sum|
    sd|min|max)` statistic; grouped over `over()` (count → grouped bars, stat →
    per-group bars)
  - `scatter x y` — one trace per `by()` group when given
  - `boxplot` — single variable, grouped over `over()`, or one box per variable
  - `piechart` — value counts, or `(percent)`
  - `hexbin x y` — 2-D density (`Histogram2d`, `bin(n)`)
  - `sankey a b …` — transitions across categorical variables
  - `coefplot <reg> dep x1 …` — fits the regression (`regress`/`logit`/`probit`/
    `poisson`) and plots non-intercept coefficients with 95% CI error bars
    (`standardize`, `noconstant`); the reg-command is required, so `coefplot y x1`
    is flagged
  For `barchart`/`piechart` the statistic comes from the **parenthesised**
  `(stat)` form (e.g. `barchart (mean) x`, `piechart (percent) x`) — matching the
  emulator, which ignores bare `, mean`/`, percent` flags (so those are flagged).
  `histogram` also supports `normal` (overlaid fitted-normal curve, numeric);
  `barchart` supports `horizontal`, `stack` (grouped bars), and multi-variable
  (one bar per variable). Deferred and flagged: scatter `lfit` (regression-line
  overlay). Needs plotly installed (`kaleido` for static images).
- `pandas_ops` reuses the emulator's own evaluator, so the pandas backend
  matches the emulator bit-for-bit; the cross-engine test proves the polars
  backend matches too.

## Tests

`tests/test_polars_backend.py` (57 cases): for each script,
`emulator == pandas backend == polars backend` across shaping, statistics,
merge, and the real-world idioms; `regress == statsmodels`; analysis steps don't
clobber the pipeline; unsupported expressions are flagged not mis-emitted.

```
python -m pytest tests/test_polars_backend.py -q
```

(The repo's full suite has 4 pre-existing failures unrelated to this work:
missing `plotly`, and a pandas-3.0 parquet dtype nuance in the duckdb bridge.)

## Manifest-driven external sources

`translate(script, manifest=Manifest.from_dict({...}))` reads external CSV/parquet
sources described by a manifest. Each dataset declares its `source`, optional
`format` (else inferred from the extension), `keys` (optional; keyless sources do
single-table analysis and only need a key to *combine*), and optional `variables`
metadata (inferred via `m2py_runtime.profile.infer_schema` when absent). The
emitted program loads each dataset with `ops.read_source(location, format)` and
bakes the manifest's join key into merges (`KeyTracker` consumes the manifest;
the shared resolver is unchanged). Composite keys (`keys: ["id", "yr"]`) bake a
list `on`. `require <src> as <alias>` binds an alias to a manifest entry.

DuckDB-backed reading (URL/SQL sources, larger-than-memory) and the
disclosure/IAM layers are follow-ons; this is the public/non-sensitive floor.

## Extending

1. New verb: add a pure op to `pandas_ops` (and `polars_ops`), add an emit case
   in `m2py_translate._emit` (TRANSFORM) or `_emit_analysis` (ANALYSIS), add the
   verb to `TRANSFORM`/`ANALYSIS`, and add a cross-engine case to the test.
2. New expression function: add a case to `exprcompile._conv_call` mapping it to
   a `pl.Expr`; verify the polars result matches the emulator in a test.
