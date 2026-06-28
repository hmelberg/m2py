# Translation equivalence harness — design

> 2026-06-13. A behavioral verification harness for the translators: run a
> snippet two ways and diff the results, catching translations that are
> string-plausible but behaviorally wrong — the class of bug golden/string
> tests cannot catch.

## Goal

For a translatable data-transform snippet, prove that the **translated microdata
script produces the same data as the original code**:

- **A (ground truth):** run the original Python in real pandas/numpy.
- **B (under test):** translate Python → microdata (py2m), run that in the
  m2py emulator (`MicroInterpreter`).
- Assert A and B are equivalent DataFrames.

## Scope (v1)

- **Idioms:** data-transform only — `generate` (arithmetic, np funcs,
  `where`/`mask`), `replace` (`.loc`), `keep`/`drop` (filter/query),
  `recode`/`.map`, `aggregate` (groupby transform), `collapse` (groupby agg).
- **Data:** small synthetic fixtures per case (deterministic; we test
  translation faithfulness, not data realism).
- **Backend:** py2m only. r2m is a structured follow-up (same pipeline, with
  two `Rscript` subprocesses for truth + translation).
- **Excluded:** analysis commands (regress/tabulate/summarize → text output),
  `sample` (random), the browser/WebR path, static parquet.

## Pipeline (per case)

A case = `(python_snippet, input_data_dict, result_var="df")`.

1. `df_in = pd.DataFrame(input_data_dict)`
2. **A:** `ns = {"df": df_in.copy(), "pd": pd, "np": np}; exec(snippet, ns);
   df_a = ns[result_var]`
3. **Translate:** `script = py2m.transform(snippet).script()`
4. **B:** `it = MicroInterpreter(metadata_path=None)`;
   `it.datasets["df"] = df_in.copy(); it.active_name = "df"`;
   run each line via `it._execute_instruction(it.parser.parse_line(line))`;
   `df_b = it.datasets[result_var]`
5. **Compare:** `assert_equivalent(df_a, df_b)`

`result_var` is `"df"` by default; for `collapse` it is the new dataset name
(e.g. `summary`), which is both the Python LHS and the microdata
`clone-dataset` name.

## Comparison (`assert_equivalent`)

The crux. Normalize before comparing so only genuine differences fail:

- **Columns:** require the same set (order-independent). Different set → fail
  with the symmetric difference.
- **Missing:** pandas `NaN` and emulator `NA`/`NaN` both treated as missing.
- **Numerics:** coerce numeric columns to float; compare with tolerance
  (`rtol/atol`), so Int64-vs-float and formatting differences don't fail.
- **Strings:** exact.
- **Row order:** sort by all columns, reset index (groupby/collapse may order
  groups differently).

A genuine mismatch means the harness is working — it is a finding.

## Disclosure control

The harness forces `m2py.M2PY_DISCLOSURE_CONTROL = "0"` so small synthetic
populations are not blocked by T1/T6 thresholds.

## Mismatch policy

Mismatches **fail** the suite. Genuine, documented semantic differences (e.g.
microdata NaN-in-condition rules) go in an explicit allow-list as `xfail` with a
written reason — visible, not silently skipped, and not blocking CI.

## Location & CI

- `tests/test_equivalence.py` (repo-root suite, which already exercises the
  m2py engine; `tests/conftest.py` already adds the repo root to the path and
  will add `py2m/`).
- Run by pytest; included in the repo test CI.

## r2m backend (implemented)

Same pipeline, R side: `tests/r_equiv_helper.R` runs the R snippet in base R
(ground truth A) and emits the r2m translation; the Python harness runs that
microdata in the emulator (B) and compares. Scoped to base-R idioms (df$col<-,
ifelse, %in%, pmax, subset, df[cond,], transform, aggregate) so no R packages
are required; dplyr/tidyverse cases would need dplyr installed. CI installs R so
these run rather than skip.

dplyr/tidyverse cases are also covered (mutate, filter, case_when first-match,
if_else, mutate chains, group_by+summarise) — snippets `library(dplyr)` so base
execution works and r2m drops the library() call; guarded by a dplyr-available
skipif, and CI installs dplyr (binary via RSPM).

## Out of scope / later

- Analysis-command comparison (coefficients, counts, stats with tolerance).
- Browser/WebR + static-parquet end-to-end (the heaviest, production-closest
  variant).
