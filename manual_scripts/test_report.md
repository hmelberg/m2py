# Manual Script Test Report

Generated: 2026-04-04

## Status: ALL FIXES IMPLEMENTED — 17/17 scripts pass.

## Summary (after fixes)

| # | Script | Status | Errors |
|---|--------|--------|--------|
| 01-17 | All 17 scripts | OK | 0 |

**Totals**: OK: 17 | PARTIAL: 0 | CRASH: 0

## Original Results (before fixes)

| # | Script | Status | Errors |
|---|--------|--------|--------|
| 05 | 05_kursdata.txt | PARTIAL | 2 |
| 06 | 06_kursdata_dato.txt | PARTIAL | 2 |
| 07 | 07_wide_to_long.txt | PARTIAL | 3 |
| 08 | 08_long_to_wide.txt | PARTIAL | 5 |

All other 13 scripts passed from the start.

---

## Detailed Errors

### Script 05: 05_kursdata.txt

**Error 1:**
- **Command**: `merge ant_kurs into bosatte`
- **Error message**: `FEIL: Finner ingen felles koblingsvariabel mellom datasettene. Kilden 'kursdata' ble laget med collapse by(fnr). Hvis 'fnr' finnes i bosatte, bruk: merge ... into bosatte on fnr`
- **Root cause**: The script creates a `kursdata` dataset with `NUDB_KURS_FNR` (aliased `fnr`), collapses by `fnr`, then tries to merge into `bosatte`. The `bosatte` dataset has `PERSONID_1` as its unit key, but no `fnr` column. In real microdata.no, `fnr` values are actual person IDs that match `PERSONID_1`. In mock mode, `NUDB_KURS_FNR` is generated independently with no link to `PERSONID_1`.
- **Fix plan**: In `MockDataEngine`, when generating `NUDB_KURS_FNR` values, sample from the existing `PERSONID_1` values of the current population rather than generating random IDs. This ensures cross-entity merges work. Specifically, in `m2py.py` `MockDataEngine._generate_series()` (around line 2140), add a special case for FNR-type variables that references existing person IDs. The variable metadata or naming convention (`*_FNR`) can be used to detect these.

**Error 2:**
- **Command**: `replace utdanning_hoy = 1 if ant_kurs >= 1`
- **Error message**: `FEIL PA KOMMANDO 'replace': name 'ant_kurs' is not defined`
- **Root cause**: Cascading failure. Because `merge ant_kurs into bosatte` failed, the variable `ant_kurs` was never added to the `bosatte` dataset. When `replace` tries to use it in a condition, it fails.
- **Fix plan**: No separate fix needed -- resolving Error 1 will fix this.

---

### Script 06: 06_kursdata_dato.txt

**Error 1:**
- **Command**: `merge ant_kurs into bosatte`
- **Error message**: `FEIL: Finner ingen felles koblingsvariabel mellom datasettene. Kilden 'kursdata' ble laget med collapse by(fnr). Hvis 'fnr' finnes i bosatte, bruk: merge ... into bosatte on fnr`
- **Root cause**: Same as Script 05 Error 1. The `fnr` variable from `NUDB_KURS_FNR` doesn't match `PERSONID_1` in the `bosatte` dataset because mock data generates them independently.
- **Fix plan**: Same fix as Script 05.

**Error 2:**
- **Command**: `replace studerer = 1 if ant_kurs >= 1`
- **Error message**: `FEIL PA KOMMANDO 'replace': name 'ant_kurs' is not defined`
- **Root cause**: Cascading failure from Error 1.
- **Fix plan**: No separate fix needed.

---

### Script 07: 07_wide_to_long.txt

**Error 1 (x3 occurrences):**
- **Command**: `tabulate-panel regstat sivstand, missing` (and similar two-variable tabulate-panel commands: `tabulate-panel regstat kjonn, missing`, `tabulate-panel sivstand kjonn, missing`)
- **Error message**: `FEIL PA KOMMANDO 'tabulate-panel': Cannot broadcast np.ndarray with operand of type <class 'list'>`
- **Root cause**: In `StatsEngine` at line 3582-3584, when `tabulate-panel` receives two variables, it creates tuple-based row values via `df[row_idx].apply(tuple, axis=1)`. This tuple Series is passed to `pd.crosstab()` as the `index` parameter. The numpy broadcasting error occurs because `pd.crosstab` can't handle the tuple-typed Series properly against the `df['tid']` column. The single-variable case (line 3586) works fine.
- **Fix plan**: In `m2py.py` at line 3582-3587 (`StatsEngine`, `tabulate-panel` handler), change the multi-variable case to create a proper composite index. Instead of `apply(tuple, axis=1)`, create a combined string column like `df[row_idx].astype(str).agg('_'.join, axis=1)` or use `pd.MultiIndex`. Alternatively, run separate `pd.crosstab` for each variable pair, since the real microdata.no shows separate tables for each dimension anyway.

  Concrete fix at `m2py.py:3582-3587`:
  ```python
  if vars_rest:
      # Create a combined string label for multi-variable rows
      row_vals = df[row_idx].astype(str).agg(' | '.join, axis=1)
      row_vals.name = ' x '.join(row_idx)
  else:
      row_vals = df[var1]
  ```

**Note**: The single-variable `tabulate-panel` commands (`tabulate-panel regstat, missing`, `tabulate-panel sivstand, missing`, `tabulate-panel kjonn, missing`, `summarize-panel lonn`) all work correctly. Only the two-variable cross-tabulation variant fails.

---

### Script 08: 08_long_to_wide.txt

**Error 1:**
- **Command**: `reshape-from-panel`
- **Error message**: `FEIL PA KOMMANDO 'reshape-from-panel': agg function failed [how->mean,dtype->object]`
- **Root cause**: In `DataTransformHandler` at line 2854, `reshape-from-panel` uses `df.pivot_table(index=id_col, columns='tid')` which defaults to `aggfunc='mean'`. When the panel DataFrame contains string/object columns (like `regstat`, `sivstand` which are categorical status codes stored as strings), `mean` aggregation fails on object dtype.
- **Fix plan**: In `m2py.py` at line 2854, use `aggfunc='first'` instead of the default `'mean'`, since reshape-from-panel is a structural operation that should just pick the value (each unit-time combination should have exactly one value). Alternatively, separate numeric and non-numeric columns and use `'mean'` for numeric and `'first'` for object dtypes.

  Concrete fix at `m2py.py:2854`:
  ```python
  wide = df.pivot_table(index=id_col, columns='tid', aggfunc='first')
  ```

**Errors 2-5 (cascading):**
- **Commands**: `tabulate regstat19`, `tabulate regstat20`, `tabulate sivstand19`, `tabulate sivstand20`
- **Error message**: `FEIL PA KOMMANDO 'tabulate': 'regstat19'` (column not found)
- **Root cause**: Because `reshape-from-panel` failed, the wide-format columns (`regstat19`, `regstat20`, etc.) were never created. The subsequent `tabulate` commands can't find these columns.
- **Fix plan**: No separate fix needed -- resolving Error 1 will fix these.

**Note**: The second `reshape-from-panel` (at the end of the script, on the `paneltest` dataset) succeeds without error, likely because that dataset was created via `import-panel` which may have different column types.

---

## Implemented Fixes

### Fix 1: `reshape-from-panel` fails on string columns (Priority: HIGH) — DONE

- **Affects**: Script 08 (and potentially any script using reshape-from-panel with categorical data)
- **File**: `m2py.py`, line 2854
- **Change**: Replace `df.pivot_table(index=id_col, columns='tid')` with `df.pivot_table(index=id_col, columns='tid', aggfunc='first')`
- **Complexity**: Low -- single line change
- **Risk**: Low -- `first` is semantically correct for reshape (one value per unit-time)

### Fix 2: `tabulate-panel` fails with two variables (Priority: HIGH) — DONE

- **Affects**: Script 07 (and any multi-variable tabulate-panel usage)
- **File**: `m2py.py`, lines 3582-3587
- **Change**: Replace `df[row_idx].apply(tuple, axis=1)` with a proper composite index that `pd.crosstab` can handle. Options:
  - (a) Use string concatenation: `df[row_idx].astype(str).agg(' | '.join, axis=1)`
  - (b) Run separate crosstab for var1 x tid and var2 x tid, and concatenate results
- **Complexity**: Low-medium
- **Risk**: Low

### Fix 3: Mock data for FNR variables doesn't link to PERSONID_1 (Priority: MEDIUM) — DONE

- **Affects**: Scripts 05, 06 (cross-entity merge via fnr)
- **File**: `m2py.py`, `MockDataEngine._generate_series()` (~line 2140)
- **Change**: When generating variables whose name ends with `_FNR` (like `NUDB_KURS_FNR`, `BEFOLKNING_FAR_FNR`, `BEFOLKNING_MOR_FNR`), sample values from the existing `PERSONID_1` population rather than generating random synthetic IDs. This creates a realistic linkage between datasets.
- **Complexity**: Medium -- requires checking if person-level data exists and sampling from it
- **Risk**: Medium -- need to ensure the sampling logic doesn't break other FNR use cases (like FAR_FNR and MOR_FNR in script 03 which already works)

## Implementation Details

### Fix 1 (m2py.py:2854)
Changed `df.pivot_table(index=id_col, columns='tid')` to `df.pivot_table(index=id_col, columns='tid', aggfunc='first')`.

### Fix 2 (m2py.py:3582-3586)
Replaced `df[row_idx].apply(tuple, axis=1)` with `df[row_idx].astype(str).agg(' | '.join, axis=1)` to produce a crosstab-compatible composite Series.

### Fix 3 (m2py.py:2501-2512 + merge fallback at ~5720-5742)
- Extended `_PERSONID_REF_VARS` to include `NUDB_KURS_FNR`, `BEFOLKNING_MRK_FNR`, `BEFOLKNING_STATUSKODE_FNR_SAMORD`, `ELHUB_PERS_MALEPUNKTID_FNR`, `KJORETOY_KJORETOYID_FNR`, `TRAFULYK_PERS_FNR`.
- Added auto-detection in the merge fallback: when no common columns exist between source and target, and the source has a collapse key that is an FNR-type variable, automatically match it against `PERSONID_1` in the target. Uses `label_manager.var_alias_to_path` to look up the register origin of the collapse key column.

### Script 08 extraction fix
The extracted script was missing the `drop kjonn20` / `rename kjonn19 kjonn` lines that are in the manual. These are needed because `reshape-to-panel` followed by `reshape-from-panel` recreates time-suffixed versions of invariant columns (like `kjonn`). Added the drop/rename pair for both reshape pathways.

## Verification
- All 17 manual scripts pass: `python manual_scripts/run_manual_scripts.py`
- Existing test suite (13 tests) still passes: `python -m pytest test_bindings.py test_delete_rename.py test_figures.py test_functions.py test_mockdata_norway.py test_normaltest_transitions.py test_require_import.py test_stata_bool_fixup.py test_sync_datasets_globals.py test_textblock.py`
