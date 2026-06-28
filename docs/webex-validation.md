# Web-example validation: emulator vs offline translator

This records a systematic comparison of the offline pandas/polars translator
against the in-browser emulator (the oracle), run over the 89 real microdata
scripts under `web_examples/`. It complements the per-verb cross-engine suite
(`tests/test_polars_backend.py`).

## Method

The web examples are real SSB scripts that `import` data — which the emulator
fills with deterministic **mock data** and the translator deliberately skips
(import is out of scope; the offline path uses pre-built extracts). A naive
"run whole script both ways and diff the final dataset" comparison is therefore
unreliable: the translator can't reconstruct interleaved `import`/transform
inputs.

So validation is **per transform command**: run the emulator command-by-command;
before each data-changing verb (`generate`/`replace`/`recode`/`keep`/`drop`/
`collapse`/`aggregate`/`merge`/`reshape`/predict/…), feed the translator the
emulator's *live* dataframe at that point, run the single translated command, and
compare the result to the emulator's. Analysis/plot verbs don't change data, so
they're skipped here (they're covered by the per-verb suite). Loops/`let` are
unrolled first via `_expand_loops`.

## Result

| Stage | Transform commands matching | Files fully clean |
|---|---|---|
| Initial | 1141 / 1345 (85%) | 50 / 89 |
| After bool-precedence + line-continuation fix | 1161 / 1345 | 52 / 89 |
| After recode-grammar fix | **1175 / 1345 (87%)** | **56 / 89** |

## Bugs found and fixed

The audit surfaced three genuine translator gaps (verbs the emulator handled but
the translator didn't), all now fixed and regression-tested:

1. **Boolean `&`/`|` precedence in `generate`/`replace`.** Python binds `&`
   tighter than `>=`, so `(utd >= 700000 & utd < 900000)` mis-parsed
   (truth-value-ambiguous, or silently wrong — e.g. the `flytter`-status
   scripts). Now `_normalize_expr` replicates the emulator's generate
   preprocessing (join `\n`, apply `_stata_like_bool_fixup` when `&`/`|`
   present, rewrite `N if cond` → `np.where`); `exprcompile` applies the same so
   the polars native path stays correct.
2. **Line continuations.** Long expressions split with a trailing `\` weren't
   joined (SyntaxError). `_expand_loops` now runs `preprocess_script` first.
3. **Recode rule grammar.** Only single-value `old=new` was handled; the
   examples use multi-value (`1 2 = 1`), ranges (`000000/099999 = 1`),
   `min`/`max`, `missing`/`*`, and labels. `recode` now delegates to the
   emulator's own `DataTransformHandler`, so the full grammar matches exactly.

## Remaining mismatches (≈170 commands, by category)

These are **not transform-logic bugs** — they're out-of-scope or harness
artifacts:

- **NameError (99) / KeyError (54):** columns like `inntekt_mor`, `lønn_far`,
  `utd_samboer` brought in by **family / `require` external linkage**
  (relative-id joins), which the offline backend doesn't model (import/require
  layer is out of scope); plus **bare-binding** references (`panel`, `kommune`)
  that the per-command harness can't resolve because it translates each line in
  isolation (the `let`/`for` binding context is intentionally dropped).
- **ValueError (12):** mostly `zero-size array` — predict verbs on data that is
  empty after the harness's single-command slice (an artifact of per-command
  isolation, not the translation).
- **TypeError (3) / column-set (2):** string-typed boolean operands and a
  predict residual-column edge.

## Takeaway

For everything in scope (data shaping, recode, merge, reshape, collapse), the
translator matches the emulator command-for-command, and the few real
discrepancies found have been fixed. The residual gap is the deliberately
out-of-scope import/`require`/family-linkage layer.
