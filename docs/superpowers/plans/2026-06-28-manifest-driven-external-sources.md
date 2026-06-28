# Manifest-driven external sources — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the offline translator read external CSV/parquet sources described by a manifest, resolving merge keys and source locations from that manifest at translate time, plus infer variable metadata when a source declares none.

**Architecture:** A `Manifest` object (loaded from a plain dict / JSON) carries per-dataset location, format, key(s), entity, sensitivity, and optional variable metadata. `m2py_translate.translate()` gains a `manifest=` argument; `KeyTracker` seeds each dataset's columns and key from it (the declared key flows through the resolver's existing collapse-key slot, so the shared `resolve_merge_key` is unchanged). The emitted program loads each dataset via a format-dispatched `read_source()` seam (pandas/polars native readers now; DuckDB-backed reading for URL/SQL/larger-than-memory is a named follow-on that plugs into the same seam). A `profile.infer_schema()` fills variable metadata when undeclared.

**Tech Stack:** Python 3.13, pandas, polars, pytest. No new third-party dependencies (DuckDB is deliberately *not* required by this slice).

## Global Constraints

- This slice is the public / non-sensitive **floor** of the platform. Out of scope here (named follow-ons, do **not** implement): IAM / user-database / login, the disclosure-control output layer, DuckDB compute push-down, DuckDB-backed reading of URL/SQL sources, and the front-end tab-complete wiring (this slice produces the inferred schema; consuming it in `index.html` is a separate front-end plan).
- The microdata emulator is the oracle; where this slice touches the emulator's parser it must preserve existing behavior (the full suite must stay green: `python -m pytest -q` → currently `508 passed, 1 xfailed`).
- Explicit always wins: an inline `keys()`/`on()` or in-script declaration overrides anything the manifest says.
- Keys are optional; a keyless source supports single-table verbs and only needs a key to combine sources.
- Variable metadata is optional; when absent it is inferred. Run-time dtype stays authoritative — schema is UX/validation only.
- Labels stay display-only — no silent code→string conversion.
- Match surrounding code style: small focused modules under `m2py_runtime/`, docstrings in the existing voice, tests under `tests/` using plain `pytest` functions (see `tests/test_key_resolution.py`).
- Commit after each task. Branch: work on `dev` (current branch) or a feature branch off it.

**Manifest dict shape (the contract every task shares):**

```python
{
  "datasets": {
    "persons": {
      "source": "data/persons.parquet",   # location string (required)
      "format": "parquet",                  # optional; inferred from source extension
      "version": 1,                          # optional
      "keys": ["PERSONID_1"],               # optional list; [] / absent = keyless
      "entity": "person",                    # optional unit type
      "sensitive": False,                    # optional; default False
      "variables": {                         # optional; inferred when absent
        "alder": {"dtype": "int", "level": "continuous", "cardinality": 80},
        "kjonn": {"dtype": "int", "level": "nominal", "cardinality": 2}
      }
    }
  }
}
```

---

### Task 1: Manifest model

**Files:**
- Create: `m2py_runtime/manifest.py`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `class Manifest` with `Manifest.from_dict(d) -> Manifest`, and instance methods `names() -> list[str]`, `has(name) -> bool`, `location(name) -> str`, `format(name) -> str` (explicit, else inferred from the source extension via the same rules as Task 3), `keys(name) -> list[str]` (empty list if keyless), `entity(name) -> str | None`, `is_sensitive(name) -> bool`, `variables(name) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_manifest.py
from m2py_runtime.manifest import Manifest

M = {
    "datasets": {
        "persons": {"source": "data/persons.parquet", "keys": ["PERSONID_1"],
                    "entity": "person", "variables": {"alder": {"dtype": "int"}}},
        "survey":  {"source": "s/survey.csv"},  # keyless, no format, no vars
    }
}


def test_names_and_has():
    m = Manifest.from_dict(M)
    assert set(m.names()) == {"persons", "survey"}
    assert m.has("persons") and not m.has("missing")


def test_location_and_inferred_format():
    m = Manifest.from_dict(M)
    assert m.location("persons") == "data/persons.parquet"
    assert m.format("persons") == "parquet"     # inferred from extension
    assert m.format("survey") == "csv"


def test_keys_default_empty_and_entity():
    m = Manifest.from_dict(M)
    assert m.keys("persons") == ["PERSONID_1"]
    assert m.keys("survey") == []               # keyless
    assert m.entity("persons") == "person"
    assert m.entity("survey") is None


def test_variables_default_empty_and_sensitive_default():
    m = Manifest.from_dict(M)
    assert m.variables("persons") == {"alder": {"dtype": "int"}}
    assert m.variables("survey") == {}
    assert m.is_sensitive("persons") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_manifest.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'm2py_runtime.manifest'`

- [ ] **Step 3: Write minimal implementation**

```python
# m2py_runtime/manifest.py
"""Source manifest — the generalized, source-agnostic catalog.

Carries, per logical dataset, where it lives, its format, its key(s), entity,
sensitivity, and optional variable metadata. The non-sensitive schema the
browser/translator consumes; physical resolution + secrets stay server-side.
"""


def _format_from(location, explicit=None):
    """Format from explicit field, else inferred from the source extension."""
    if explicit:
        return explicit
    loc = location.lower()
    for ext, fmt in (
        (".parquet", "parquet"), (".csv", "csv"),
        (".duckdb", "duckdb"), (".db", "duckdb"),
        (".sqlite", "sql"), (".json", "manifest"),
    ):
        if loc.endswith(ext):
            return fmt
    raise ValueError(f"cannot infer format for source {location!r}")


class Manifest:
    """Read-only view over a manifest dict (see the plan's contract shape)."""

    def __init__(self, datasets):
        self._d = datasets

    @classmethod
    def from_dict(cls, d):
        return cls(dict((d or {}).get("datasets") or {}))

    def names(self):
        return list(self._d)

    def has(self, name):
        return name in self._d

    def location(self, name):
        return self._d[name]["source"]

    def format(self, name):
        e = self._d[name]
        return _format_from(e["source"], e.get("format"))

    def keys(self, name):
        return list(self._d[name].get("keys") or [])

    def entity(self, name):
        return self._d[name].get("entity")

    def is_sensitive(self, name):
        return bool(self._d[name].get("sensitive", False))

    def variables(self, name):
        return dict(self._d[name].get("variables") or {})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_manifest.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add m2py_runtime/manifest.py tests/test_manifest.py
git commit -m "feat(manifest): source manifest model (location/format/keys/variables)"
```

---

### Task 2: Variable inference

**Files:**
- Create: `m2py_runtime/profile.py`
- Test: `tests/test_profile.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `infer_schema(df) -> dict[str, dict]` mapping each column to `{"dtype": str, "level": str, "cardinality": int}`. `dtype` ∈ {int,float,bool,date,string}; `level` ∈ {nominal,continuous} (ordinality is never inferred — only declared). Numeric columns with ≤10 distinct values are `nominal`, else `continuous`; bool/string are `nominal`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_profile.py
import pandas as pd
from m2py_runtime.profile import infer_schema


def test_infers_dtype_level_cardinality():
    df = pd.DataFrame({
        "age": [20, 31, 44, 55, 66, 70, 81, 90, 25, 39],   # numeric, high-card -> continuous
        "sex": [1, 2, 1, 2, 1, 2, 1, 2, 1, 2],             # numeric, low-card  -> nominal
        "name": list("abcdefghij"),                         # string -> nominal
    })
    s = infer_schema(df)
    assert s["age"] == {"dtype": "int", "level": "continuous", "cardinality": 10}
    assert s["sex"]["level"] == "nominal" and s["sex"]["cardinality"] == 2
    assert s["name"]["dtype"] == "string" and s["name"]["level"] == "nominal"


def test_bool_is_nominal():
    df = pd.DataFrame({"flag": [True, False, True]})
    assert infer_schema(df)["flag"]["level"] == "nominal"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_profile.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'm2py_runtime.profile'`

- [ ] **Step 3: Write minimal implementation**

```python
# m2py_runtime/profile.py
"""Best-effort variable metadata inference for sources without a schema.

Fills dtype + a nominal/continuous guess + cardinality. Ordinality and code-set
meaning are never inferred (they must be declared). UX/validation only — the
run-time dtype remains authoritative for actual behaviour.
"""

import pandas as pd

_NOMINAL_MAX_CARD = 10


def infer_schema(df):
    out = {}
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_bool_dtype(s):
            dtype = "bool"
        elif pd.api.types.is_integer_dtype(s):
            dtype = "int"
        elif pd.api.types.is_float_dtype(s):
            dtype = "float"
        elif pd.api.types.is_datetime64_any_dtype(s):
            dtype = "date"
        else:
            dtype = "string"
        card = int(s.nunique(dropna=True))
        if dtype in ("int", "float"):
            level = "nominal" if card <= _NOMINAL_MAX_CARD else "continuous"
        else:
            level = "nominal"
        out[col] = {"dtype": dtype, "level": level, "cardinality": card}
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_profile.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add m2py_runtime/profile.py tests/test_profile.py
git commit -m "feat(profile): infer variable dtype/level/cardinality for sources without schema"
```

---

### Task 3: Source reader seam

**Files:**
- Create: `m2py_runtime/sources.py`
- Test: `tests/test_sources.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `read_source(location, fmt=None) -> pandas.DataFrame` and `scan_source(location, fmt=None) -> polars.LazyFrame`. Format inferred from the extension when `fmt` is None (same rules as Task 1). Supported now: `csv`, `parquet`. `duckdb`/`sql`/url raise `NotImplementedError` naming the DuckDB-backed follow-on. This is the seam DuckDB later plugs into.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sources.py
import pandas as pd
import pytest
from m2py_runtime.sources import read_source, scan_source


def test_read_csv_and_parquet(tmp_path):
    df = pd.DataFrame({"id": [1, 2], "x": [10, 20]})
    csv = tmp_path / "d.csv"; df.to_csv(csv, index=False)
    pq = tmp_path / "d.parquet"; df.to_parquet(pq)
    pd.testing.assert_frame_equal(read_source(str(csv)), df)
    pd.testing.assert_frame_equal(read_source(str(pq)), df)


def test_scan_returns_lazyframe(tmp_path):
    import polars as pl
    df = pd.DataFrame({"id": [1, 2]})
    pq = tmp_path / "d.parquet"; df.to_parquet(pq)
    lf = scan_source(str(pq))
    assert isinstance(lf, pl.LazyFrame)
    assert lf.collect().to_pandas()["id"].tolist() == [1, 2]


def test_unsupported_format_names_followon(tmp_path):
    with pytest.raises(NotImplementedError, match="DuckDB"):
        read_source("x.sqlite")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sources.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'm2py_runtime.sources'`

- [ ] **Step 3: Write minimal implementation**

```python
# m2py_runtime/sources.py
"""Source reader seam: location + format -> DataFrame / LazyFrame.

Reads csv/parquet via the native pandas/polars readers. DuckDB-backed reading
(url/sql/duckdb and larger-than-memory) is a named follow-on that plugs into this
same interface.
"""

import pandas as pd

from .manifest import _format_from


def read_source(location, fmt=None):
    fmt = _format_from(location, fmt)
    if fmt == "parquet":
        return pd.read_parquet(location)
    if fmt == "csv":
        return pd.read_csv(location)
    raise NotImplementedError(
        f"source format {fmt!r} needs the DuckDB-backed reader (follow-on)")


def scan_source(location, fmt=None):
    import polars as pl
    fmt = _format_from(location, fmt)
    if fmt == "parquet":
        return pl.scan_parquet(location)
    if fmt == "csv":
        return pl.scan_csv(location)
    raise NotImplementedError(
        f"source format {fmt!r} needs the DuckDB-backed reader (follow-on)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sources.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add m2py_runtime/sources.py tests/test_sources.py
git commit -m "feat(sources): csv/parquet read_source + scan_source seam (DuckDB is a follow-on)"
```

---

### Task 4: KeyTracker consumes the manifest

**Files:**
- Modify: `m2py_translate.py` (the `KeyTracker` class, ~line 145; `translate()` signature + state init)
- Test: `tests/test_merge_into.py` (append)

**Interfaces:**
- Consumes: `Manifest` (Task 1).
- Produces: `KeyTracker(manifest=None)`. Manifest-seeding is folded into `ensure()`/`create()` (not a separate method), so a manifest-known dataset gets `cols = variables ∪ keys` and its declared key the first time it's introduced, never clobbering accumulated columns, and `manifest=None` preserves today's behavior exactly. `translate(script, backend, source_path, allow_emulated, manifest=None)` passes the manifest into the tracker. Merge resolution uses the manifest key with **no change to `resolve_merge_key`** (the declared key flows through the existing `src_collapse_key`/`tgt_collapse_key` slot).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_merge_into.py  (append)
def test_manifest_key_resolves_merge():
    from m2py_runtime.manifest import Manifest
    man = Manifest.from_dict({"datasets": {
        "persons": {"source": "p.parquet", "keys": ["id"]},
        "income":  {"source": "i.parquet", "keys": ["id"]},
    }})
    code = t.translate(
        "use income\nmerge wage into persons",
        backend="pandas", source_path=None, manifest=man)
    assert "left_on='id', right_on='id'" in code
    assert "# TODO" not in code            # resolved, not flagged
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_merge_into.py::test_manifest_key_resolves_merge -q`
Expected: FAIL — `TypeError: translate() got an unexpected keyword argument 'manifest'`

- [ ] **Step 3: Write minimal implementation**

In `m2py_translate.py`, give `KeyTracker.__init__` a manifest + a declared-key map, fold manifest-seeding into `ensure`/`create`, add `_key`, and have `resolve` use it. Replace `__init__`, `ensure`, `create`, and `resolve`:

```python
    def __init__(self, manifest=None):
        self.cols = {}            # name (None = implicit frame) -> set[str]
        self.collapse_key = {}    # name -> str
        self.alias_path = {}      # alias -> registry path
        self.declared_key = {}    # name -> str (manifest keys[0])
        self.manifest = manifest

    def ensure(self, name):
        if name not in self.cols:
            m = self.manifest
            if m is not None and m.has(name):
                keys = m.keys(name)
                self.cols[name] = set(m.variables(name)) | set(keys)
                if keys:
                    self.declared_key[name] = keys[0]
            else:
                self.cols[name] = {self.DEFAULT_KEY}
        return self.cols[name]

    def create(self, name):
        self.cols.pop(name, None)
        self.collapse_key.pop(name, None)
        self.ensure(name)

    def _key(self, name):
        """Current key for a dataset: collapse key, else manifest-declared."""
        return self.collapse_key.get(name) or self.declared_key.get(name)

    def resolve(self, active, into, on_var):
        self.ensure(active)
        self.ensure(into)
        return resolve_merge_key(
            source_cols=self.cols[active],
            target_cols=self.cols[into],
            on_var=on_var,
            src_collapse_key=self._key(active),
            tgt_collapse_key=self._key(into),
            is_person_ref=self.is_person_ref,
        )
```

Because seeding is in `ensure`/`create`, no per-call `seed()` is needed — `use`/`create-dataset`/the merge target all already go through `ensure`/`create`, and `manifest=None` reproduces today's behavior. In `translate()`, change the signature line:

```python
def translate(script, backend="pandas", source_path="df", allow_emulated=False,
              manifest=None):
```

and the tracker construction:

```python
    tracker = KeyTracker(manifest)   # per-dataset cols + key, for baking merge join keys
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_merge_into.py -q`
Expected: PASS (all existing + the new test)

- [ ] **Step 5: Run the full suite (no regression)**

Run: `python -m pytest -q`
Expected: `509 passed, 1 xfailed` (508 prior + 1 new)

- [ ] **Step 6: Commit**

```bash
git add m2py_translate.py tests/test_merge_into.py
git commit -m "feat(translate): KeyTracker seeds cols+key from a manifest (resolver unchanged)"
```

---

### Task 5: Emit manifest-driven source loading

**Files:**
- Modify: `m2py_translate.py` (`_load_dataset`, ~line 332; `_load_other`; thread `manifest` to them)
- Test: `tests/test_merge_into.py` (append — an end-to-end run on real parquet files)

**Interfaces:**
- Consumes: `Manifest` (Task 1), `read_source`/`scan_source` (Task 3).
- Produces: when the manifest knows a dataset, the emitted loader is `ops.read_source("<loc>", "<fmt>")` (pandas) / `ops.scan_source(...)` (polars) with location+format baked in; otherwise the existing `_load(name)` / `datasets` path is kept. Requires re-exporting `read_source`/`scan_source` from the backends so emitted `ops.read_source` resolves.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_merge_into.py  (append)
def test_runs_end_to_end_from_manifest(tmp_path):
    import pandas as pd
    from m2py_runtime.manifest import Manifest
    persons = pd.DataFrame({"id": [1, 2, 3], "alder": [20, 30, 40]})
    income  = pd.DataFrame({"id": [1, 2, 3], "wage": [100, 200, 300]})
    p = tmp_path / "persons.parquet"; persons.to_parquet(p)
    i = tmp_path / "income.parquet"; income.to_parquet(i)
    man = Manifest.from_dict({"datasets": {
        "persons": {"source": str(p), "keys": ["id"], "variables": {"alder": {}}},
        "income":  {"source": str(i), "keys": ["id"], "variables": {"wage": {}}},
    }})
    code = t.translate(
        "use income\nmerge wage into persons\nuse persons",
        backend="pandas", source_path=None, manifest=man)
    assert "ops.read_source(" in code
    ns = {"pd": pd}
    exec(code, ns)
    out = ns["df"].sort_values("id").reset_index(drop=True)
    assert out["wage"].tolist() == [100, 200, 300]   # joined on id from the manifest
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_merge_into.py::test_runs_end_to_end_from_manifest -q`
Expected: FAIL — emitted code uses `_load('income')` (no manifest read), and/or `ops.read_source` is undefined.

- [ ] **Step 3: Write minimal implementation**

Re-export the readers from both backends. In `m2py_runtime/pandas_ops.py` add near the top (after imports):

```python
from .sources import read_source  # noqa: F401  (used by generated code: ops.read_source)
```

In `m2py_runtime/polars_ops.py` add:

```python
from .sources import scan_source as read_source  # noqa: F401  (generated code calls ops.read_source)
```

In `m2py_translate.py`, give `_load_dataset` and `_load_other` access to the manifest and bake `read_source` when known. Replace `_load_dataset`:

```python
def _load_dataset(backend, name, source_path, manifest=None):
    """Materialise dataset ``name``: manifest source (read_source) if known, else
    parquet (file mode) or the in-memory ``_load`` helper."""
    var = _dsvar(backend, name)
    if manifest is not None and manifest.has(name):
        src = f"ops.read_source({manifest.location(name)!r}, {manifest.format(name)!r})"
    elif source_path is not None:
        src = (f'pl.scan_parquet("{name}.parquet")' if backend == "polars"
               else f'pd.read_parquet("{name}.parquet")')
    else:
        src = f"_load({name!r})"
    return f"{var} = {src}"
```

Replace `_load_other`'s body to take + use `manifest` (add `manifest=None` param, and before the `source_path` branch):

```python
    if manifest is not None and manifest.has(name):
        return [f"{_dsvar(backend, name)} = "
                f"ops.read_source({manifest.location(name)!r}, {manifest.format(name)!r})"], _dsvar(backend, name)
```

Thread `manifest` through the calls without widening every signature — the tracker already holds it (Task 4):
- In `translate()`, the SESSION-branch `_load_dataset(...)` calls become `_load_dataset(backend, a[0], source_path, manifest)` (`manifest` is the `translate()` param, in scope here).
- In `_emit_merge`, replace `_load_other(into, backend, known, source_path)` with `_load_other(into, backend, known, source_path, tracker.manifest)`, and the old-syntax `_load_other(name, backend, known, source_path)` with `_load_other(name, backend, known, source_path, tracker.manifest)`.

No `manifest` parameter is added to `_emit`/`_emit_merge` — they read `tracker.manifest`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_merge_into.py::test_runs_end_to_end_from_manifest -q`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: `510 passed, 1 xfailed`

- [ ] **Step 6: Commit**

```bash
git add m2py_translate.py m2py_runtime/pandas_ops.py m2py_runtime/polars_ops.py tests/test_merge_into.py
git commit -m "feat(translate): emit manifest-driven read_source loading; runs end-to-end"
```

---

### Task 6: `require` binds names + URL source parsing

**Files:**
- Modify: `m2py.py` (the `require` parse branch, lines 613-616)
- Modify: `m2py_translate.py` (the `require`-is-currently-UNTRANSLATED path: record the alias→name binding in the tracker)
- Test: `tests/test_merge_into.py` (append) and `tests/test_key_resolution.py` (append a parser test)

**Interfaces:**
- Consumes: `Manifest` (Task 1), `KeyTracker` (Task 4).
- Produces: `MicroParser.parse_line("require <url> as d")` returns `{"source": "<url>", "alias": "d"}` (URLs no longer swallowed by the `//` comment rule). In `translate()`, a `require <name> as <alias>` seeds the tracker for both `<name>` and `<alias>` from the manifest so a later `use <alias>`/`merge … into <alias>` resolves.

- [ ] **Step 1: Write the failing test (parser)**

```python
# tests/test_key_resolution.py  (append)
def test_require_parses_url_source():
    import m2py
    out = m2py.MicroParser().parse_line("require https://h/x.csv as d")
    assert out["args"] == {"source": "https://h/x.csv", "alias": "d"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_key_resolution.py::test_require_parses_url_source -q`
Expected: FAIL — `args == {}` (the `//` in the URL is stripped as a comment).

- [ ] **Step 3: Fix the parser**

The line-comment stripper truncates at `//`, eating the URL scheme. Guard `://`. Find the comment-strip in `m2py.py` (search `'//'` in `MicroParser`); the require branch sees an already-truncated `remainder`. The minimal, localized fix is to protect a `scheme://` before comment stripping. In `MicroParser.parse_line`, locate where line comments are removed (a `split('//')` or regex). Replace the bare `//` handling so a `//` immediately preceded by `:` (i.e. `://`) is not treated as a comment:

```python
# where the code currently strips line comments, e.g.:
#   line = line.split('//', 1)[0]
# replace with a scheme-aware strip:
import re as _re
line = _re.sub(r'(?<!:)//.*$', '', line)
```

(Use the existing comment variable name; the regex removes `//…` only when the preceding char is not `:`.)

- [ ] **Step 4: Run the parser test + full suite**

Run: `python -m pytest tests/test_key_resolution.py::test_require_parses_url_source -q && python -m pytest -q`
Expected: parser test PASS; full suite still green (the comment change must not break existing comment handling — if any test fails, the regex is the culprit).

- [ ] **Step 5: Write the failing test (require binds names)**

```python
# tests/test_merge_into.py  (append)
def test_require_alias_resolves_from_manifest():
    from m2py_runtime.manifest import Manifest
    man = Manifest.from_dict({"datasets": {
        "no.ssb/persons": {"source": "p.parquet", "keys": ["id"]},
        "no.ssb/income":  {"source": "i.parquet", "keys": ["id"]},
    }})
    code = t.translate(
        "require no.ssb/persons as persons\n"
        "require no.ssb/income as income\n"
        "use income\nmerge wage into persons",
        backend="pandas", source_path=None, manifest=man)
    assert "left_on='id', right_on='id'" in code and "# TODO" not in code
```

- [ ] **Step 6: Make the require binding seed the tracker**

In `m2py_translate.py`, the translate loop currently emits `require` as `# import (data assumed present)` only for `cmd == "import"`; `require` falls through to UNTRANSLATED. Add a `require` branch right after the `import` branch:

```python
        # ---- require: bind an alias to a manifest source; seed keys/cols ----
        if cmd == "require":
            src = a.get("source") if isinstance(a, dict) else None
            alias = a.get("alias") if isinstance(a, dict) else None
            if src and tracker.manifest is not None and tracker.manifest.has(src):
                # alias is how the script refers to it; mirror the manifest entry
                tracker.declared_key[alias] = (tracker.manifest.keys(src)[:1] or [None])[0]
                tracker.cols[alias] = set(tracker.manifest.variables(src)) | set(tracker.manifest.keys(src))
            body.append(f"# require {src} as {alias} (bound from manifest)")
            continue
```

- [ ] **Step 7: Run the test + full suite**

Run: `python -m pytest tests/test_merge_into.py::test_require_alias_resolves_from_manifest -q && python -m pytest -q`
Expected: both PASS; full suite `512 passed, 1 xfailed` (510 + 2 new).

- [ ] **Step 8: Commit**

```bash
git add m2py.py m2py_translate.py tests/test_merge_into.py tests/test_key_resolution.py
git commit -m "feat(require): parse URL sources; bind alias->manifest source, seed keys"
```

---

### Task 7: Composite keys (explicit / manifest-declared)

**Files:**
- Modify: `m2py_runtime/keys.py` (allow a list key through), `m2py_runtime/pandas_ops.py` + `m2py_runtime/polars_ops.py` (`merge`/`merge_into` accept list `on`), `m2py_translate.py` (`_old_syntax_key` + `_emit_merge` carry a list)
- Test: `tests/test_merge_into.py` (append)

**Interfaces:**
- Consumes: Tasks 4-5.
- Produces: a manifest `keys: ["a", "b"]` (or explicit `on(a b)`) bakes `on=['a','b']`; `ops.merge(df, other, on=['a','b'])` and `ops.merge_into(..., left_on=['a','b'], right_on=['a','b'])` join on the column list. Composite keys are explicit-only (never inferred).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_merge_into.py  (append)
def test_composite_key_from_manifest(tmp_path):
    import pandas as pd
    from m2py_runtime.manifest import Manifest
    a = pd.DataFrame({"id": [1, 1, 2], "yr": [2020, 2021, 2020], "v": [10, 11, 20]})
    b = pd.DataFrame({"id": [1, 1, 2], "yr": [2020, 2021, 2020], "w": [1, 2, 3]})
    pa = tmp_path / "a.parquet"; a.to_parquet(pa)
    pb = tmp_path / "b.parquet"; b.to_parquet(pb)
    man = Manifest.from_dict({"datasets": {
        "a": {"source": str(pa), "keys": ["id", "yr"], "variables": {"v": {}}},
        "b": {"source": str(pb), "keys": ["id", "yr"], "variables": {"w": {}}},
    }})
    code = t.translate("use a\nmerge v into b\nuse b",
                       backend="pandas", source_path=None, manifest=man)
    assert "['id', 'yr']" in code
    ns = {"pd": pd}; exec(code, ns)
    out = ns["df"].sort_values(["id", "yr"]).reset_index(drop=True)
    assert out["v"].tolist() == [10, 11, 20]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_merge_into.py::test_composite_key_from_manifest -q`
Expected: FAIL — only the first key (`id`) is used, so the join multiplies rows / mismatches.

- [ ] **Step 3: Implement composite keys**

In `m2py_translate.py`, `KeyTracker._key` returns the first key today; add `_keys(name)` returning the full list, and make `_emit_merge` bake a list when the declared key is composite. Add to `KeyTracker`:

```python
    def _keys(self, name):
        """Full declared/collapse key list (composite-aware)."""
        ck = self.collapse_key.get(name)
        if ck:
            return [ck]
        m = self.manifest
        if m is not None and m.has(name) and m.keys(name):
            return m.keys(name)
        dk = self.declared_key.get(name)
        return [dk] if dk else []
```

In `_emit_merge`, after `res = tracker.resolve(...)`, override with the composite list when the manifest declares >1 key and the resolver picked a single column that is the first of them:

```python
        keys = tracker._keys(into)
        if len(keys) > 1 and res.status == "ok" and res.left_on == res.right_on == keys[0]:
            left_on = right_on = keys
        else:
            left_on, right_on = res.left_on, res.right_on
        # ... use left_on/right_on in the merge_into call below
```

(Replace the existing `left_on={res.left_on!r}, right_on={res.right_on!r}` with `left_on={left_on!r}, right_on={right_on!r}`.) Do the analogous change in `_old_syntax_key` so a composite manifest key returns the list.

In `m2py_runtime/pandas_ops.py`, `merge_into` already passes `left_on`/`right_on` to `pd.merge`, which accepts lists; only the `drop_duplicates(subset=[right_on])` and the `right_cols`/`endswith` logic assume a scalar. Make them list-aware:

```python
def merge_into(target, source, vars, left_on, right_on):
    lon = left_on if isinstance(left_on, list) else [left_on]
    ron = right_on if isinstance(right_on, list) else [right_on]
    cols_from_source = [c for c in (vars or []) if c in source.columns]
    right_cols = list(dict.fromkeys(list(ron) + cols_from_source))
    right = source[right_cols].drop_duplicates(subset=ron)
    if lon == ron:
        return pd.merge(target, right, on=lon, how="left")
    merged = pd.merge(target, right, left_on=lon, right_on=ron,
                      how="left", suffixes=("", "_src_dup"))
    merged = merged.drop(columns=[c for c in merged.columns if c.endswith("_src_dup")])
    drop = [c for c in ron if c not in lon and c not in target.columns and c in merged.columns]
    return merged.drop(columns=drop) if drop else merged
```

`merge` (symmetric) already forwards `on` to `pd.merge`, which accepts a list — no change needed. In `m2py_runtime/polars_ops.py`, `merge_into` delegates to pandas (Task from prior work) so it inherits the fix; `merge` forwards `on` to `lf.join`, which accepts a list — no change.

- [ ] **Step 4: Run the test + full suite**

Run: `python -m pytest tests/test_merge_into.py::test_composite_key_from_manifest -q && python -m pytest -q`
Expected: PASS; full suite `513 passed, 1 xfailed`.

- [ ] **Step 5: Commit**

```bash
git add m2py_translate.py m2py_runtime/keys.py m2py_runtime/pandas_ops.py m2py_runtime/polars_ops.py tests/test_merge_into.py
git commit -m "feat(keys): composite keys via explicit/manifest declaration (list on=)"
```

---

### Task 8: Integration test + docs

**Files:**
- Create: `tests/test_manifest_integration.py`
- Modify: `docs/polars-offline-backend.md`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: one end-to-end test mixing a keyed parquet source, a keyless CSV, a cross-source merge, and a single-table analysis; plus a docs section.

- [ ] **Step 1: Write the integration test**

```python
# tests/test_manifest_integration.py
import pandas as pd
import m2py_translate as t
from m2py_runtime.manifest import Manifest


def test_keyed_merge_plus_keyless_csv(tmp_path):
    persons = pd.DataFrame({"PERSONID_1": [1, 2, 3], "kommnr": [1, 1, 2]})
    income = pd.DataFrame({"PERSONID_1": [1, 2, 3], "wage": [100, 200, 300]})
    survey = pd.DataFrame({"resp": [5, 6, 7]})            # keyless
    pp = tmp_path / "p.parquet"; persons.to_parquet(pp)
    pi = tmp_path / "i.parquet"; income.to_parquet(pi)
    sc = tmp_path / "s.csv"; survey.to_csv(sc, index=False)
    man = Manifest.from_dict({"datasets": {
        "persons": {"source": str(pp), "keys": ["PERSONID_1"],
                    "variables": {"kommnr": {}}},
        "income":  {"source": str(pi), "keys": ["PERSONID_1"],
                    "variables": {"wage": {}}},
        "survey":  {"source": str(sc)},                   # keyless, csv
    }})
    code = t.translate(
        "use income\nmerge wage into persons\n"
        "use persons\ncollapse (mean) wage, by(kommnr)",
        backend="pandas", source_path=None, manifest=man)
    ns = {"pd": pd}; exec(code, ns)
    out = ns["df"].sort_values("kommnr").reset_index(drop=True)
    assert out["wage"].tolist() == [150.0, 300.0]   # (100+200)/2, 300


def test_keyless_single_table_needs_no_key(tmp_path):
    survey = pd.DataFrame({"resp": [5, 6, 7, 8]})
    sc = tmp_path / "s.csv"; survey.to_csv(sc, index=False)
    man = Manifest.from_dict({"datasets": {"survey": {"source": str(sc)}}})
    code = t.translate("use survey\ngenerate big = 1 if resp > 6",
                       backend="pandas", source_path=None, manifest=man)
    ns = {"pd": pd}; exec(code, ns)
    assert ns["df"]["big"].fillna(0).tolist() == [0, 0, 1, 1]
```

- [ ] **Step 2: Run the integration test**

Run: `python -m pytest tests/test_manifest_integration.py -q`
Expected: PASS (2 passed)

- [ ] **Step 3: Document it**

Append to `docs/polars-offline-backend.md` a section:

```markdown
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
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -q`
Expected: `515 passed, 1 xfailed`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_manifest_integration.py docs/polars-offline-backend.md
git commit -m "test+docs: manifest-driven external sources end-to-end"
```

---

## Notes for the implementer

- Run `python -m pytest -q` after every task; the count rises by the new tests each time and must never drop below the prior green baseline.
- If a step's line numbers have drifted, search by the quoted code rather than trusting the line number.
- Do **not** add a `duckdb` dependency — Task 3's seam intentionally defers it.
- Keep emitted code readable (the output is shown to users in the menu); prefer baked literals over runtime indirection.
