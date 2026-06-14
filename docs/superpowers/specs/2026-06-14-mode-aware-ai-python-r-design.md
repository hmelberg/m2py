# Design: Mode-aware AI (Python/R code generation) for kode-svar-v2

Date: 2026-06-14
Status: Approved (pending written-spec review)
Branch: dev

## Goal

Make the "Spør raskt" v2 AI generate code in the editor's active language —
**Python** (Pyodide) or **R** (WebR) — when the user is in those modes, instead
of always emitting microdata.no DSL. In Python/R mode the data is still loaded
from microdata.no variables via a `#micro` hybrid block, then analyzed in
pandas/statsmodels or tidyverse/base R.

## Current behavior (verified)

- The client sends `{ question, lang, script }` to `/api/kode-svar(-v2)` —
  `lang` is the human language (NO/EN), NOT the programming mode. `activeEditorMode`
  (`microdata`/`python`/`r`) is never sent.
- The edge functions are microdata-only: `SYSTEM_INTRO` instructs "lag et
  microdata.no-script"; `OUTPUT_INSTRUCTION` asks for a ```microdata block.
- Result: in Python/R mode, the AI still returns microdata DSL.

## Decisions (locked)

1. **No auto-repair for Python/R** in this version — m2py cannot validate
   Python/R. Keep variable-name grounding on the `#micro` import block.
2. **v2 only** (pilot). v1 (`/api/kode-svar`) stays microdata-only and unchanged.
3. **Hybrid is the model**: the AI emits a `#micro` block for data loading +
   `#python`/`#r` for analysis.

## Hybrid `#micro` convention (from existing examples)

```
#micro
require no.ssb.fdb:53 as fd
create-dataset folk
import fd/BEFOLKNING_KJOENN as kjonn
import fd/INNTEKT_WLONN 2022-01-01 as inntekt

#python            (or #r)
folk.groupby("kjonn")["inntekt"].agg(["mean","median","count"])
```

The dataset name (`folk`) becomes a pandas DataFrame / R data.frame; columns are
the import aliases (`kjonn`, `inntekt`); missing values are NaN/NA.

## Available packages (for the language preamble)

- **Python (Pyodide):** preloaded `pandas`, `numpy`, `scipy`, `statsmodels`,
  `matplotlib`, `seaborn`, `plotly`; `micropip` installs more on demand.
- **R (WebR):** `tidyverse` (dplyr/ggplot2/tidyr/…) + base R; more via
  `webR installPackages`.

## Architecture

Mode-aware code generation in `kode-svar-v2.ts` only. The picker pass and the
focused block are **language-agnostic and unchanged** — variable selection does
not depend on the output language. Only the generation system prefix varies by
mode.

### Prompt partitioning

`buildCachedPrefix(origin)` becomes `buildCachedPrefix(origin, mode)` returning
three byte-stable, independently cached variants. `RULE_BLOCKS` splits into:

**SHARED_DATA_BLOCKS (all modes)** — knowledge about the data/registers, language-agnostic:
- variable catalog, kommune codes
- `DATABANK_CHEATSHEET` (import command by temporalitet — needed for `#micro`)
- `DATASET_STRUCTURE`, `RELATIONS_LINKS`, `PSEUDONYM_RULES`, `TYPE_RULES`,
  `DATE_QUIRKS`, `PRIVACY_RULES`, `MISSING_VALUES`, `NPR_RULES`
- the analytic-strategy essence of `INFERENCE_RULES` (confounders / heterogeneity /
  proxy mindset — language-agnostic)

`INFERENCE_RULES` is split into two constants: `INFERENCE_STRATEGY` (the
"Analytisk strategi" bullets — shared) and `INFERENCE_METHODS` (the
microdata method/factor syntax: regress/ivregress/regress-panel/coefplot/… —
microdata-only). In microdata mode the two are concatenated in the original
order so the assembled text is unchanged.

**MICRODATA_BLOCKS (microdata mode only)** — the DSL language:
- `GRAMMAR_CHEATSHEET`, `STATA_DIFFERENCES`, `MERGE_CHEATSHEET`
- command reference, function reference
- `VISUALIZATION_RULES` (barchart/boxplot/…)
- `CANONICAL_EXAMPLES`
- the method-syntax portion of `INFERENCE_RULES`
- microdata `SYSTEM_INTRO`, microdata `OUTPUT_INSTRUCTION`

**New, small blocks for Python/R (replace the microdata analysis half):**
- `LANG_PREAMBLE_PY` / `LANG_PREAMBLE_R` — short: "write idiomatic Python; the
  packages above are loaded; `micropip`/`installPackages` for more."
- `MICRO_IMPORT_BRIDGE` — load microdata variables in a `#micro` block
  (`require`/`create-dataset`/`import … as alias`); the dataset name becomes a
  DataFrame/data.frame with the aliases as columns; missing → NaN/NA; write the
  analysis in a `#python`/`#r` block.
- Mode variant of `SYSTEM_INTRO` (expert assistant that writes Python/R over
  microdata register data) and `OUTPUT_INSTRUCTION` (emit `#micro` + ```python /
  ```r blocks).

Prefix composition per mode:
- `microdata`: the SHARED + MICRODATA blocks reassembled in **exactly today's
  `RULE_BLOCKS` order** (+ catalog/kommune/command/function/examples in the same
  positions), so `buildCachedPrefix(origin, "microdata")` is byte-identical to
  the current output — v1 parity preserved and guarded by a golden test.
- `python`/`r`: SHARED_DATA_BLOCKS + catalog + kommune + LANG_PREAMBLE_* +
  MICRO_IMPORT_BRIDGE + mode SYSTEM_INTRO/OUTPUT. (No command/function reference,
  no microdata grammar/examples/viz.)

### Caching

Replace the single `_cachedPrefix` with a per-mode map
(`Record<Mode, string|null>`). Each variant is byte-stable → Anthropic prompt
cache still hits per mode. Slightly higher cold-start cost (up to 3 prefixes),
each independent.

## Data flow

```
client (Send⚗︎, mode = activeEditorMode)
  → POST /api/kode-svar-v2 { question, lang, script, mode }
  → picker (unchanged) → focused block (unchanged)
  → buildCachedPrefix(origin, mode)
  → stream generation → client renders markdown live
  → client:
      microdata → validate via m2py + name-grounding → 1 repair round (as today)
      python/r  → SKIP m2py validation/repair; run name-grounding on the
                  #micro block only (db/NAME tokens vs microdataVariableNames)
```

## Components & files

- **index.html**
  - `runFastQueryV2` / `streamKodeSvarV2`: include `mode: activeEditorMode` in
    the payload.
  - Branch the validation/repair tail on `mode === 'microdata'`: only microdata
    runs m2py validation + repair; python/r runs name-grounding only (extract the
    `#micro` block, check `db/NAME` against `microdataVariableNames`; surface a ⚠
    if any are unknown, no auto-repair).
- **kode-svar.ts**
  - Split `RULE_BLOCKS` into `SHARED_DATA_BLOCKS` and `MICRODATA_BLOCKS`.
  - `buildCachedPrefix(origin, mode = "microdata")`: per-mode assembly + per-mode
    module cache. `microdata` output unchanged.
  - Export what v2 needs (the shared assembler / blocks).
- **kode-svar-v2.ts**
  - Read `mode` from the body (default `microdata`); validate to the enum.
  - New constants: `LANG_PREAMBLE_PY`, `LANG_PREAMBLE_R`, `MICRO_IMPORT_BRIDGE`,
    `SYSTEM_INTRO_PY`, `SYSTEM_INTRO_R`, `OUTPUT_PY`, `OUTPUT_R` (or a small
    builder). Pass `mode` to `buildCachedPrefix`.
  - The `SVARFORMAT_TILLEGG` (considerations section) stays — it is
    language-agnostic prose advice.

## Error handling / fallback

- Unknown/missing `mode` → `microdata` (today's behavior).
- python/r: no m2py repair (m2py can't validate Python/R); name-grounding kept as
  the cheap safety check on the import block.
- Picker failure → no focused block, as today (degrades to data-blocks only).

## Testing

- **Deno unit tests:**
  - `buildCachedPrefix(origin, "microdata")` is byte-identical to the pre-change
    output (v1 parity) — golden assertion.
  - `("python")` / `("r")` include the catalog + shared data blocks + the
    language preamble + `MICRO_IMPORT_BRIDGE`, and **exclude** the command
    reference, function reference, and microdata grammar/examples.
  - mode validation: an unknown mode string resolves to microdata.
- **Manual:** Python mode → "snitt-lønn etter kjønn 2022" → response has a
  `#micro` block + a `#python` block (pandas). R mode → `#micro` + `#r` (dplyr).
  microdata mode → unchanged (still microdata + repair).
- Existing pytest + Deno suites unaffected (no m2py change).

## Deliberately out of scope (YAGNI, first version)

- Run-based validation/repair for Python/R (could execute in Pyodide/WebR later).
- Python/R-specific few-shot beyond the bridge block (the LLM knows the languages).
- Mode-awareness in v1 (`/api/kode-svar`) — stays microdata-only.

## Rollout / rollback

- Additive: a new `mode` field + v2-internal branching. v1 untouched.
- Rollback = stop sending `mode` (v2 falls back to microdata) or revert the v2
  changes.
- Port candidates to `prompts.py` (Anvil) are noted but out of scope.
