# Offline self-contained script generation for Anvil — design

**Status:** approved design (2026-06-28), pre-implementation
**Branch:** `feature/polars-offline-backend`
**Related:** `docs/polars-offline-backend.md`, `docs/webex-validation.md`

## Goal

Let a user translate a microdata.no script into a **self-contained Python
script** (pandas *or* polars) that Anvil can run directly on its own data. The
script performs analysis, statistics, shaping, and merging on datasets that
Anvil already holds (from `create-dataset` and its imports), and may build new
datasets from them (`collapse`, `merge`, `aggregate`, …).

The emulator (`m2py.MicroInterpreter`) remains the oracle: the translated
script must produce the same results the emulator would. Where the emulator is
itself wrong, fix the emulator.

## Decisions (from brainstorming)

1. **Two backends, both already exist.** `translate(script, backend="pandas")`
   and `backend="polars"`. No new backend work; the entry point just exposes the
   choice.
2. **Merge keys resolved at translation time**, baked as a literal `on=` into
   the emitted code. Feasible because the translator runs next to the live
   catalog in the browser.
3. **Unresolved key → flag, don't fail.** Bake the best guess, prefix the line
   with `# TODO: verify join key …`, and append a translation-summary block
   listing every flagged merge. Matches the translator's existing style.
4. **Packaging = depend on `m2py_runtime`.** Anvil mirrors the whole `m2py/`
   folder (emulator included), so the emitted script does
   `from m2py_runtime import pandas_ops as ops` and that resolves on Anvil
   exactly as locally. **No decoupling, vendoring, or tree-shaking.**
5. **Missing input dataset → emulator fallback behind an opt-in flag.** Real data
   is the default path; when an input is absent *and* `allow_emulated=True`, the
   script synthesizes it via the emulator (logging that it did); otherwise it
   raises `KeyError`. `allow_emulated` defaults to `False`.
6. **Entry point now = hamburger-menu item** that runs `translate()` in the
   browser's Pyodide and writes the returned text to the output window. No file
   download, no API call yet. The `translate()` signature is the stable seam a
   later Anvil API call reuses.
7. **Key resolution = Approach A:** one shared pure resolver, called by both the
   emulator and the translator; the translator maintains per-dataset
   column-sets and key columns via a static walk.

## Architecture

```
microdata script
   │
   ├─ m2py.MicroParser.parse_line ──────────► IR (unchanged, shared)
   │
   ▼
m2py_translate.translate(script, backend, allow_emulated)
   │  ├─ _expand_loops            (existing: unroll for/let, preprocess)
   │  ├─ KeyTracker (NEW)         static walk: dataset_cols, dataset_key
   │  │     └─ at each merge → resolve_merge_key(...)  ◄── shared resolver
   │  ├─ _emit / _emit_analysis / _emit_plot   (existing emitters)
   │  └─ header emitter (UPDATED): datasets.get + emulator fallback
   ▼
self-contained .py  ──►  Anvil runs it (has m2py_runtime + m2py)
```

### Components

#### 1. Shared merge-key resolver — `m2py_runtime/keys.py` (NEW)

A pure function extracted from the emulator's merge handler (m2py.py:8086+):

```python
def resolve_merge_key(src_cols, tgt_cols, on_var, src_key, tgt_key,
                      catalog=None):
    """Return (left_on, right_on, status) where status is 'ok' or 'unresolved'.

    Mirrors the emulator's precedence:
      1. explicit on_var (present in src, tgt, or both)
      2. src_key present in tgt  → join on src_key
      3. tgt_key present in src   → join on tgt_key
      4. a single shared column
      5. person-ref FNR→PERSONID_1 / car↔owner linkage via `catalog`
         (var_alias_to_path person-ref detection)
      6. otherwise status='unresolved' (caller bakes best guess + TODO)
    """
```

- `src_key`/`tgt_key` come from `_get_df_key_col` (entity keys: `PERSONID_1`,
  `ARBEIDSFORHOLD_ID`, `KJORETOY_ID`, `NUDB_KURS_LOEPENR`, `AGGRSHOPPID`,
  `NPRID`, `unit_id`) or the tracked collapse key.
- `catalog` is the label-manager metadata (`var_alias_to_path`) used for the
  cross-entity person-ref linkage. `None` (no catalog at translate time) just
  means steps 5 can't fire → falls through to 'unresolved' → TODO.
- **Single source of truth:** the emulator's merge handler is refactored to call
  this function (behavior-preserving; the existing 416-test suite + per-command
  web-example harness guard the refactor).

#### 2. KeyTracker — static walk in `m2py_translate.py` (NEW)

Maintains, per dataset name:
- `dataset_cols[name] : set[str]` — known columns
- `dataset_key[name]  : str | None` — current key column

Seeding and updates (mirroring emulator state):
- `create-dataset` / `import` → seed `dataset_cols` + `dataset_key` from catalog
  metadata for the imported variables (entity key from entity type).
- `generate` / `clone-variables` → add target column(s).
- `collapse` / `aggregate` → set `dataset_key[name]` to the `by`/group var; reset
  cols to group + produced columns.
- `merge` → union right-side cols into the active dataset's col-set.
- `rename` / `drop` / `keep` → adjust col-set accordingly.

At each `merge`, KeyTracker supplies `src_cols/tgt_cols/src_key/tgt_key` to
`resolve_merge_key`. The walk runs after `_expand_loops`, over the same flat
instruction stream the emitters consume, so keys and emitted lines stay aligned.

#### 3. Merge emit — `_emit` merge branch (UPDATED)

Replaces today's `_merge_parts` "honor explicit `on` or return None":

```python
left_on, right_on, status = resolve_merge_key(...)
on = left_on if left_on == right_on else (left_on, right_on)
line = f"{var} = ops.merge({var}, {other}, left_on={left_on!r}, "
       f"right_on={right_on!r}, how={how!r})"
if status == "unresolved":
    line = "# TODO: verify join key (could not resolve from catalog)\n" + line
    flagged.append((lineno, name))
```

`ops.merge` gains `left_on`/`right_on` (keep `on=` as a convenience alias) on
both `pandas_ops` and `polars_ops` so asymmetric person-ref joins
(`left_on='inntekt_mor_id', right_on='PERSONID_1'`) are expressible.

#### 4. Header / input resolution (UPDATED)

For each input dataset the script reads, emit:

```python
def _load(name):
    df = (datasets or {}).get(name)
    if df is None:
        if allow_emulated:
            print(f"[m2py] dataset {name!r} not provided — emulating")
            return ops.emulate_import(name)
        raise KeyError(f"dataset {name!r} not provided "
                       f"(pass it in `datasets`, or set allow_emulated=True)")
    return df
```

- `allow_emulated` is a module-level variable near the top of the emitted file,
  default `False`, overridable by the Anvil caller before running.
- `ops.emulate_import(name)` (NEW, in both backends) constructs a
  `MicroInterpreter`, runs the minimal import for `name`, and returns the
  resulting frame (pandas; polars wraps via `pl.from_pandas`). This is the only
  runtime touch-point with the emulator and is reached only on the opt-in path.

#### 5. Entry point — hamburger menu (UPDATED `index.html`)

- A menu item (e.g. "Vis offline Python ▸ pandas | polars").
- Handler calls, in the existing Pyodide runtime,
  `m2py_translate.translate(current_script, backend=<choice>)` and writes the
  returned string to the output window (same surface the emulator output uses).
- No download, no network. `translate()`'s signature is unchanged except for the
  new optional `allow_emulated=False` parameter, so the later Anvil API call is
  the same function.

## Data flow (merge example)

```
create-dataset persons              KeyTracker: persons.key = PERSONID_1
import INNTEKT_MOR as inntekt_mor    persons.cols += {inntekt_mor, inntekt_mor_id?}
create-dataset famtab               famtab.key = PERSONID_1
use persons
merge inntekt into famtab
   resolve_merge_key(src=persons.cols, tgt=famtab.cols,
                     on=None, src_key=PERSONID_1, tgt_key=PERSONID_1)
   → ('PERSONID_1','PERSONID_1','ok')
   emit: df_persons = ops.merge(df_persons, df_famtab,
                                left_on='PERSONID_1', right_on='PERSONID_1',
                                how='left')
```

## Error handling

- **Unresolved merge key:** bake best guess + `# TODO: verify join key`; collect
  into a `# --- translation summary ---` block at the end listing
  `line N: <active> <- <other>`.
- **Missing input at runtime:** `KeyError` (default) or emulator fallback
  (`allow_emulated=True`), per decision 5.
- **Multi-key merge:** unchanged — the emulator already rejects it with a
  composite-key workaround message; the translator emits that message as a
  comment and skips the merge (no silent wrong join).

## Testing

1. **Resolver refactor parity:** existing 416-test suite + per-command
   web-example harness must stay green after the emulator is refactored to call
   `resolve_merge_key`. This is the guard that behavior didn't change.
2. **Key-tracking unit tests** (`tests/test_polars_backend.py` and/or a new
   `tests/test_key_resolution.py`): for representative scripts (same-entity
   merge, collapse-then-merge, person-ref family merge, car↔owner merge), assert
   the translator's chosen `(left_on, right_on)` equals the emulator's.
3. **Cross-engine merge cases:** add implicit-merge scripts to the existing
   cross-engine table so pandas and polars outputs agree with the emulator.
4. **Emulator fallback:** a test that an absent input raises `KeyError` by
   default and returns an emulated frame when `allow_emulated=True`.
5. **Web-example re-run:** the family/car scripts that previously failed with
   NameError/KeyError (out-of-scope linkage) should now resolve their merges;
   re-run the harness and update `docs/webex-validation.md` with the new numbers.

## Out of scope

- Standalone / tree-shaken single-file output (superseded by the package model).
- UI file download and the Anvil API call (later; `translate()` is the seam).
- Real external-data import beyond the opt-in emulator fallback.
- Import semantics themselves (Anvil holds imported data; we only resolve keys
  and optionally emulate).

## File touch list

- `m2py_runtime/keys.py` — NEW: `resolve_merge_key`.
- `m2py.py` — refactor merge handler (8086+) to call `resolve_merge_key`
  (behavior-preserving).
- `m2py_translate.py` — NEW KeyTracker walk; UPDATED merge emit; UPDATED header
  emitter; new `allow_emulated` param.
- `m2py_runtime/pandas_ops.py` — `merge` gains `left_on`/`right_on`; NEW
  `emulate_import`.
- `m2py_runtime/polars_ops.py` — same surface (`merge`, `emulate_import`).
- `index.html` — hamburger menu item + handler.
- `tests/test_polars_backend.py` (+ maybe `tests/test_key_resolution.py`).
- `docs/polars-offline-backend.md`, `docs/webex-validation.md` — update.
