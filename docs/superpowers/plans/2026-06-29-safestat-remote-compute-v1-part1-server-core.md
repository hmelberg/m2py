# SafeStat Remote Compute — v1 Part 1: Server Compute Core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the pure-Python compute core that translates a microdata script, runs it on a provided real dataset, applies result-side disclosure suppression, and returns the exact JSON shape the SafeStat client already renders.

**Architecture:** A new module `m2py_remote.py` mirrors the client's in-Pyodide run path (`m2py_translate.translate(..., source_path=None, print_results=...)` → `exec` → collect `result_*`/`fig_*` from the namespace → serialize), and inserts one new stage: each `result_*` object passes through a `PandasProtect` adapter (wrapping the existing `protect` package) governed by a `ProtectionPolicy` resolved from source protection levels. This is the milestone-1 deliverable from the design spec's build order; it is pure CPython and fully testable in this repo without Anvil or a browser.

**Tech Stack:** Python 3.13 (miniforge), pandas, the in-repo translator (`m2py_translate.py` + `m2py_runtime/`), the sibling `protect` package (installed editable), pytest.

## Global Constraints

- **Build on the translator; never fork or edit the emulator** (`m2py.py`). This module only *imports* `m2py_translate`. (spec: Guardrail compliance)
- **Shared surfaces are additive and behavior-preserving only.** No edits to `m2py_translate.py`, `m2py_runtime/`, or `protect.py` in this plan — only new files. (spec: Guardrail compliance)
- **v1 is strictly public-capable but governance is data-driven, not branched.** All divergence lives in `resolve_policy` / the adapter — **zero `if extended:`**. (spec: Guardrail compliance)
- **The returned JSON shape must match the client contract exactly:** keys `code, out, html, n, err, figs, results` (the client renderer at `index.html:7605-7641` consumes these). (spec: Data flow; verified against `index.html:7600-7603`)
- **The full test suite must not regress.** Run `python -m pytest -q` and record the real baseline before starting (the spec notes the brief's 531/1 figure is disputed by local-env notes — reconcile first). (spec: Verification)
- The translator emits `result_N = ops.<verb>(...)` when `print_results=False` and `print(result_N)` when `True` (verified `m2py_translate.py:673`). The core uses `print_results=raw` and collects the `result_*` namespace variables.

---

## File Structure

- **Create `m2py_protection.py`** (repo root) — `ProtectionLevel` constants, `resolve_policy(levels) -> ProtectionPolicy`, and the `PandasProtect` adapter. One responsibility: turn protection levels into behavior and apply result-side suppression. Lives at repo root next to `m2py_translate.py` so it is import-resolvable in the same way and can join the sync manifest later (Part 4).
- **Create `m2py_remote.py`** (repo root) — `run_remote(...)`: the translate→exec→collect→suppress→serialize core. Depends on `m2py_translate` and `m2py_protection`.
- **Create `tests/test_m2py_protection.py`** — unit tests for `resolve_policy` and `PandasProtect`.
- **Create `tests/test_m2py_remote.py`** — end-to-end tests for `run_remote`, including the "suppress is live" demonstration.

---

### Task 0: Environment setup — make `protect` importable

**Files:**
- None created; environment only.

**Interfaces:**
- Produces: a Python env where `import protect`, `import pandas`, and `import m2py_translate` all succeed from the m2py repo root.

- [ ] **Step 1: Confirm pandas + translator import**

Run:
```bash
cd /Users/hom/Documents/GitHub/m2py
python -c "import pandas, m2py_translate; print('ok', pandas.__version__)"
```
Expected: `ok <version>` with no ImportError.

- [ ] **Step 2: Install the sibling `protect` package editable**

Run:
```bash
cd /Users/hom/Documents/GitHub/m2py
python -m pip install -e /Users/hom/Documents/GitHub/protect
```
Expected: `Successfully installed protect-...` (or "already satisfied").

- [ ] **Step 3: Confirm `protect` imports and exposes `suppress`**

Run:
```bash
python -c "import protect as p; print(callable(p.suppress))"
```
Expected: `True`

- [ ] **Step 4: Record the pytest baseline**

Run:
```bash
cd /Users/hom/Documents/GitHub/m2py && python -m pytest -q 2>&1 | tail -5
```
Expected: a pass/fail summary line. **Write the exact numbers down** — this is the regression baseline. Do not proceed if the suite errors at collection time.

---

### Task 1: `resolve_policy` — levels → policy (most-restrictive-wins)

**Files:**
- Create: `m2py_protection.py`
- Test: `tests/test_m2py_protection.py`

**Interfaces:**
- Produces:
  - Constants `PUBLIC = "public"`, `PROTECTED = "protected"`, `SENSITIVE = "sensitive"`.
  - `resolve_policy(levels: list[str]) -> dict` returning keys
    `{"level": str, "auth_required": bool, "log": bool, "pre_recipe": dict|None, "post_suppress": dict|None}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_m2py_protection.py
from m2py_protection import resolve_policy, PUBLIC, PROTECTED, SENSITIVE


def test_resolve_policy_public_is_all_pass():
    pol = resolve_policy([PUBLIC])
    assert pol["level"] == PUBLIC
    assert pol["auth_required"] is False
    assert pol["log"] is False
    assert pol["pre_recipe"] is None
    assert pol["post_suppress"] is None


def test_resolve_policy_protected_suppresses_and_logs():
    pol = resolve_policy([PROTECTED])
    assert pol["auth_required"] is True
    assert pol["log"] is True
    assert pol["post_suppress"] == {"min_n": 5}


def test_resolve_policy_most_restrictive_wins():
    pol = resolve_policy([PUBLIC, PROTECTED, PUBLIC])
    assert pol["level"] == PROTECTED


def test_resolve_policy_empty_defaults_public():
    assert resolve_policy([])["level"] == PUBLIC
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/hom/Documents/GitHub/m2py && python -m pytest tests/test_m2py_protection.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'm2py_protection'`.

- [ ] **Step 3: Write minimal implementation**

```python
# m2py_protection.py
"""Protection policy + the pandas ProtectionAdapter for SafeStat remote compute.

resolve_policy turns one-or-more source protection levels into a single policy
(most-restrictive-source-wins). PandasProtect is the v1 reference adapter; it
wraps the `protect` package for result-side disclosure control. No emulator or
translator code is touched here — this is purely additive.
"""
from __future__ import annotations

PUBLIC = "public"
PROTECTED = "protected"
SENSITIVE = "sensitive"

_ORDER = {PUBLIC: 0, PROTECTED: 1, SENSITIVE: 2}


def resolve_policy(levels):
    """Most-restrictive-source-wins. Returns a ProtectionPolicy dict."""
    level = max(levels, key=lambda lv: _ORDER[lv]) if levels else PUBLIC
    if level == PUBLIC:
        return {"level": PUBLIC, "auth_required": False, "log": False,
                "pre_recipe": None, "post_suppress": None}
    if level == PROTECTED:
        return {"level": PROTECTED, "auth_required": True, "log": True,
                "pre_recipe": None, "post_suppress": {"min_n": 5}}
    return {"level": SENSITIVE, "auth_required": True, "log": True,
            "pre_recipe": {"profile": "microdata_no"},
            "post_suppress": {"min_n": 5, "secondary": True}}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_m2py_protection.py -q`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add m2py_protection.py tests/test_m2py_protection.py
git commit -m "feat(safestat): resolve_policy — protection levels to policy"
```

---

### Task 2: `PandasProtect.suppress` — result-side disclosure control

**Files:**
- Modify: `m2py_protection.py`
- Test: `tests/test_m2py_protection.py`

**Interfaces:**
- Consumes: `protect.suppress` (sibling package). `protect.suppress(series, min_n=K)` returns the series with values `< K` replaced by `NaN` (verified `protect/protect.py:1509-1520`, the `min_n` branch).
- Produces: class `PandasProtect` with method
  `suppress(self, result, spec: dict | None) -> object`. For a frequency-table `DataFrame` (one carrying an `n` count column, as `ops.tabulate` returns — verified `m2py_runtime/pandas_ops.py:487`), it NaNs the `n` of rows below `spec["min_n"]`. All other result types and `spec is None` pass through unchanged in v1.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_m2py_protection.py
import pandas as pd
from m2py_protection import PandasProtect


def test_suppress_nans_small_counts_in_freq_table():
    table = pd.DataFrame({"x": [1, 2, 3], "n": [12, 3, 7]})
    out = PandasProtect().suppress(table, {"min_n": 5})
    # row with n=3 is below threshold -> NaN; others intact
    assert pd.isna(out.loc[1, "n"])
    assert out.loc[0, "n"] == 12
    assert out.loc[2, "n"] == 7
    # category keys are never touched
    assert list(out["x"]) == [1, 2, 3]


def test_suppress_none_spec_passes_through():
    table = pd.DataFrame({"x": [1], "n": [2]})
    out = PandasProtect().suppress(table, None)
    assert out.loc[0, "n"] == 2


def test_suppress_non_table_passes_through():
    obj = {"not": "a table"}
    assert PandasProtect().suppress(obj, {"min_n": 5}) is obj
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_m2py_protection.py -q`
Expected: FAIL — `ImportError: cannot import name 'PandasProtect'`.

- [ ] **Step 3: Write minimal implementation**

```python
# append to m2py_protection.py
class PandasProtect:
    """v1 reference ProtectionAdapter. Result-side suppression for pandas.

    `suppress` is the post-protect hook (design stage 7): it runs on the
    structured result object BEFORE it is serialized to HTML. v1 handles the
    frequency-table case (a DataFrame with an 'n' count column); other result
    types pass through unchanged. pre()/admissible() arrive in later parts.
    """

    def suppress(self, result, spec):
        if spec is None:
            return result
        try:
            import pandas as pd
        except Exception:
            return result
        if isinstance(result, pd.DataFrame) and "n" in result.columns:
            import protect as p
            out = result.copy()
            out["n"] = p.suppress(out["n"], min_n=spec["min_n"])
            return out
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_m2py_protection.py -q`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add m2py_protection.py tests/test_m2py_protection.py
git commit -m "feat(safestat): PandasProtect.suppress — min-cell on freq tables"
```

---

### Task 3: `run_remote` — translate, execute, collect, serialize

**Files:**
- Create: `m2py_remote.py`
- Test: `tests/test_m2py_remote.py`

**Interfaces:**
- Consumes:
  - `m2py_translate.translate(script, backend="pandas", source_path=None, allow_emulated=False, print_results=raw)` → Python source string (verified signature `m2py_translate.py:808`). With `source_path=None` the emitted program resolves named datasets via a `_load(name)` helper that reads from a `datasets` dict in the exec namespace (verified `m2py_translate.py:842-855`).
  - `m2py_protection.PandasProtect`.
- Produces: `run_remote(script, *, datasets, backend="pandas", policy=None, raw=False) -> dict` with keys `{"code","out","html","n","err","figs","results"}` — the client contract. `datasets` is a `{name: pandas.DataFrame}` mapping of REAL data (the caller fetches it; the emulator is not used). `policy` is a `resolve_policy(...)` result or `None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_m2py_remote.py
import pandas as pd
from m2py_remote import run_remote
from m2py_protection import resolve_policy, PUBLIC, PROTECTED

# A microdata script that loads a named dataset and tabulates a column.
# create-dataset binds `df_demo = _load("demo")`; tabulate emits result_1.
SCRIPT = "create-dataset demo\ntabulate grp"


def _data():
    # grp value 9 appears 3x (below min_n=5), grp 1 appears 6x (kept).
    return {"demo": pd.DataFrame({"grp": [1]*6 + [9]*3})}


def test_run_remote_returns_client_contract_keys():
    res = run_remote(SCRIPT, datasets=_data(), policy=resolve_policy([PUBLIC]))
    assert set(res) == {"code", "out", "html", "n", "err", "figs", "results"}
    assert res["err"] is None, res["err"]
    assert res["results"], "expected at least one rendered result"


def test_run_remote_public_keeps_small_counts():
    res = run_remote(SCRIPT, datasets=_data(), policy=resolve_policy([PUBLIC]))
    # public => no suppression => the count 3 survives in the rendered table
    assert ">3<" in res["results"][0] or "3.0" in res["results"][0]


def test_run_remote_protected_suppresses_small_counts():
    res = run_remote(SCRIPT, datasets=_data(), policy=resolve_policy([PROTECTED]))
    html = res["results"][0]
    # protected => n=3 row suppressed to NaN; the surviving count 6 still shows
    assert ">6<" in html or "6.0" in html
    assert "NaN" in html  # suppressed cell renders as NaN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_m2py_remote.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'm2py_remote'`.

- [ ] **Step 3: Write minimal implementation**

```python
# m2py_remote.py
"""SafeStat remote compute core (pure CPython).

Mirrors the client's in-Pyodide run path (index.html ~7536-7603) on the server:
translate the microdata script, exec it against provided REAL data, collect the
result_* / fig_* objects, apply result-side suppression per the protection
policy, and serialize to the JSON shape the SafeStat client renderer consumes.
The emulator is NOT used here — `datasets` carries real data the caller fetched.
"""
from __future__ import annotations

import contextlib
import io

import m2py_translate as _mt
from m2py_protection import PandasProtect


def _render_result(r):
    if hasattr(r, "to_html"):
        return r.to_html(border=0, classes="output-table")
    if hasattr(r, "summary"):
        return "<pre>" + str(r.summary()) + "</pre>"
    return "<pre>" + str(r) + "</pre>"


def run_remote(script, *, datasets, backend="pandas", policy=None, raw=False):
    code = _mt.translate(script, backend=backend, source_path=None,
                         allow_emulated=False, print_results=raw)
    ns = {"datasets": dict(datasets)}
    buf = io.StringIO()
    err = None
    try:
        with contextlib.redirect_stdout(buf):
            exec(code, ns)
    except Exception as exc:
        err = repr(exc)

    adapter = PandasProtect()
    spec = (policy or {}).get("post_suppress")

    figs = []
    for k in sorted(ns):
        if k.startswith("fig_"):
            try:
                figs.append(ns[k].to_json())
            except Exception:
                pass

    results = []
    for k in sorted(ns):
        if k.startswith("result_"):
            results.append(_render_result(adapter.suppress(ns[k], spec)))

    df = ns.get("df")
    html = ""
    if df is not None:
        try:
            html = df.head(50).to_html(border=0)
        except Exception:
            html = "<pre>" + str(df)[:5000] + "</pre>"

    return {"code": code, "out": buf.getvalue(), "html": html,
            "n": (None if df is None else int(len(df))),
            "err": err, "figs": figs, "results": results}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_m2py_remote.py -q`
Expected: 3 passed. If `test_run_remote_protected_suppresses_small_counts` fails on the `"NaN"` assertion, inspect `res["results"][0]` — pandas renders `NaN` for suppressed cells in `to_html`; adjust the assertion to the actual rendered token (e.g. empty cell) only after confirming the `n=3` value is genuinely absent.

- [ ] **Step 5: Commit**

```bash
git add m2py_remote.py tests/test_m2py_remote.py
git commit -m "feat(safestat): run_remote — server compute core with live suppress"
```

---

### Task 4: Guard the full suite (no regression)

**Files:**
- None.

- [ ] **Step 1: Run the full suite**

Run: `cd /Users/hom/Documents/GitHub/m2py && python -m pytest -q 2>&1 | tail -5`
Expected: the same pass/xfail counts as the Task 0 baseline, plus the new tests (7 + 3). No previously-passing test now fails.

- [ ] **Step 2: Confirm no emulator/translator/protect files changed**

Run: `git diff --name-only HEAD~3 | sort`
Expected: only `m2py_protection.py`, `m2py_remote.py`, `tests/test_m2py_protection.py`, `tests/test_m2py_remote.py`. If `m2py.py`, `m2py_translate.py`, `m2py_runtime/*`, or `protect.py` appear, a Global Constraint was violated — revert those edits.

---

## Self-Review

**Spec coverage (this part only — server compute core / spec build-order step 1):**
- "translate + run the real translator on a provided source" → Task 3 (`run_remote`, `allow_emulated=False`, injected `datasets`). ✓
- "`protect` post-`suppress` wired live on result tables" → Task 2 + Task 3 (`test_run_remote_protected_suppresses_small_counts` proves it). ✓
- "`resolve_policy` is the one place levels turn into behavior" → Task 1. ✓
- "return the JSON shape SafeStat already renders" → Task 3 (`test_run_remote_returns_client_contract_keys`). ✓
- "prove suppress is live, not just present" (v1 discipline) → Task 3 demonstration test. ✓
- Deferred and correctly ABSENT here: auth/authz, logging, registry, async, the Anvil endpoint, the client seam, `pre`/`admissible`, the sync script — these are Parts 2–4.

**Placeholder scan:** none — every step has runnable code/commands.

**Type consistency:** `resolve_policy` returns the dict whose `post_suppress` key Task 2/3 read; `PandasProtect.suppress(result, spec)` signature matches its call in `run_remote`; the returned dict keys match the client contract asserted in tests. ✓

---

## Subsequent plans (written when this part is green)

Per the design spec's build order, the remaining v1 parts each get their own plan:

- **Part 2 — Anvil endpoint + registry + async.** `m2py_shim.run_extended` wraps `run_remote` (fetching the real CSV via `read_source` and building `datasets`); `@http_endpoint("/run_extended")` launches a background task; poll via existing `/task_status`; minimal `Source` table + `resolve_source` with one seeded public source; `resolve_policy` fed from the looked-up level. Requires the Anvil app; not locally TDD-able.
- **Part 3 — Client Executor seam.** Refactor `runSafeStatScript` (`index.html`) behind `LocalPyodideExecutor` / `RemoteApiExecutor` (submit-and-poll to `/run_extended` + `/task_status`, `Authorization: Bearer ${window.mdAuth.token}`, base from `localStorage 'md_ai_api_base'`), `deriveExecutor`, replacing the placeholder at `index.html:7483-7487`. Verified via `node --check` + manual reload.
- **Part 4 — Sync script.** `sync_to_api.py` + manifest covering `m2py.py`, `m2py_translate.py`, `m2py_runtime/`, `protect.py`, **and the two new files `m2py_remote.py` + `m2py_protection.py`**; report-only first run; clobber-safety check on the server's `m2py.py`.
