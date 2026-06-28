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
| Shaping | `generate`, `replace`, `recode`, `keep`, `drop`, `rename`, `destring` |
| Aggregation | `collapse`, `aggregate` |
| Merge | `merge` |
| Analysis (side output) | `summarize`, `tabulate`, `correlate`, `regress` |

Coverage on the repo's real `manual_scripts/` + `examples/`: **186/187 (99%)**
of these verbs translate. `import`/session plumbing is intentionally out of
scope — point the offline script at a parquet/CSV extract you already have
(e.g. one DuckDB mode built).

**Expressions** (for `generate`/`replace`/`if`): arithmetic, comparisons,
boolean, `substr`, `int`, `sysmiss`/`missing`, `string`/`lower`/`upper`/`length`,
`log`/`exp`/`sqrt`/`abs`/`round`/`min`/`max`, `np.where`. Anything outside this
set is emitted as a `# UNTRANSLATED` comment — **never silently-wrong code**.

**Options** are guarded by a per-verb allow-list (`HANDLED_OPTIONS`): a verb
honours `by()` (collapse/aggregate/summarize/tabulate), `outer_join`/`on()`
(merge), `gini`/`iqr` (summarize), `missing`/`freq`/`cellpct`/`rowpct`/`colpct`/
`chi2`/`top`/`bottom` (tabulate), `force` (destring), and the `if` condition
everywhere. Any *other* option on a line — e.g. tabulate `nolabels`/`rowsort`/
`summarize()`, correlate `sig`, destring `dpcomma` — makes the line
`# UNTRANSLATED` rather than being silently ignored. Two-way `tabulate x y` is
supported (via args); percentages are `0-100` columns within any `by` group;
`chi2` adds `chi2`/`chi2_p`/`chi2_dof` (scipy chi-square, two-way); `top(n)`/
`bottom(n)` keep the n highest/lowest-frequency rows (bare `top` -> 10). List all gaps (unknown verb, expression, or option) for a script with
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

## Extending

1. New verb: add a pure op to `pandas_ops` (and `polars_ops`), add an emit case
   in `m2py_translate._emit` (TRANSFORM) or `_emit_analysis` (ANALYSIS), add the
   verb to `TRANSFORM`/`ANALYSIS`, and add a cross-engine case to the test.
2. New expression function: add a case to `exprcompile._conv_call` mapping it to
   a `pl.Expr`; verify the polars result matches the emulator in a test.
