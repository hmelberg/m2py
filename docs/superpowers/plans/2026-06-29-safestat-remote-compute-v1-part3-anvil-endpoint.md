# SafeStat Remote Compute — v1 Part 3: Anvil /run_extended Endpoint — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make remote compute-to-data real end-to-end: a SafeStat script POSTed to the Anvil app runs the real translator on a registered public CSV source and returns the `_results`/`_figs` JSON the client renders — data fetched server-side, results suppressed per policy.

**Architecture:** Split by testability. (3a) A locally-TDD-able core in the m2py repo — `run_remote_from_sources(script, sources, …)` fetches each source via `read_source`, resolves the protection policy, and calls the Part-1 `run_remote`. (3b) Thin Anvil glue in `microdata-api` — a minimal `resolve_source` registry (one seeded public source), `m2py_shim.run_extended` wrapping the core, a `@background_task`, and the `@http_endpoint("/run_extended")` that launches it and is polled by the existing `/task_status`. The core is synced to the server by `sync_to_api.py` (Part 2), so the Anvil side stays a thin wrapper.

**Tech Stack:** Python 3.13 (PATH python; pandas 2.3.3) + pytest for 3a; Anvil server runtime (`anvil.server`, deploy-and-verify-live, no local pytest) for 3b; `python -m py_compile` for server-module syntax checks.

## Global Constraints

- **3a is additive to the m2py repo and fully locally tested.** It adds `run_remote_from_sources` to `m2py_remote.py` (and tests); it imports `read_source` (`m2py_runtime/sources.py`) and `resolve_policy` (`m2py_protection.py`) — no edits to those or to the emulator/translator. (spec: Guardrail.)
- **3b is verified by deploy, not local pytest.** `microdata-api` server modules import `anvil` and cannot run under local pytest. Each 3b task's check is `python -m py_compile <module>` (syntax, no import) plus a deploy-and-verify checklist step the operator runs. (confirmed: no local Anvil runtime.)
- **The existing `/run` (emulator-on-mock) and `/query` are untouched.** `/run_extended` is a new endpoint; reuse the existing `/task_status` poll and `auth` helpers. (verified `api_endpoints.py`.)
- **Protection level is resolved server-side from the registered source, never from the request.** The request sends `source_id`; `resolve_source` returns its `location`/`level`. (spec: decision 6.)
- **v1 source is public** — `resolve_policy(["public"])` ⇒ all-pass (no auth/log/pre); the post-`suppress` still runs live. The registry is a module-level dict with one seeded public source (the Anvil Data Table is the deferred admin-layer upgrade). (spec: v1 discipline.)
- **The client contract is unchanged:** the endpoint ultimately returns `m2py_remote.run_remote`'s `{code,out,html,n,err,figs,results}` (under `/task_status`'s `result` key). (verified Part 1 + `/task_status` shape.)
- The server must already have the synced engine (Part 2 `--apply` done). `read_source(url)` does `pd.read_csv(url)` for a `.csv` location (verified `m2py_runtime/sources.py:13-18`).

---

## File Structure

- **Modify `m2py_remote.py`** (m2py repo) — add `run_remote_from_sources`. Keep it small; it only orchestrates fetch → policy → `run_remote`.
- **Create `tests/test_run_remote_from_sources.py`** (m2py repo) — local TDD against a temp CSV.
- **Modify `microdata-api/server_code/m2py_shim.py`** — add `run_extended` (wraps the core).
- **Create `microdata-api/server_code/source_registry.py`** — `resolve_source` + the seeded public source dict.
- **Modify `microdata-api/server_code/api_endpoints.py`** — add `bg_run_extended` background task + the `/run_extended` endpoint.

(`m2py_remote.py` is on the sync manifest, so after 3a, re-run `python sync_to_api.py --apply` to push the new core to the server before 3b deploy.)

---

## Part 3a — Locally-tested core (m2py repo)

### Task 1: `run_remote_from_sources` — fetch sources, resolve policy, run

**Files:**
- Modify: `m2py_remote.py`
- Test: `tests/test_run_remote_from_sources.py`

**Interfaces:**
- Consumes: `read_source(location, fmt=None) -> pandas.DataFrame` (`m2py_runtime/sources.py`); `resolve_policy(levels)` and `run_remote(...)` (Part 1).
- Produces: `run_remote_from_sources(script, sources, *, backend="pandas", raw=False) -> dict` where `sources` is a list of `{"alias": str, "location": str, "level": str}`. Returns the same `{code,out,html,n,err,figs,results}` dict as `run_remote`. The `alias` is the dataset name the script loads (e.g. `create-dataset demo` ⇒ alias `"demo"`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_remote_from_sources.py
import pandas as pd
from m2py_remote import run_remote_from_sources

SCRIPT = "create-dataset demo\ntabulate grp"


def _csv(tmp_path):
    p = tmp_path / "demo.csv"
    pd.DataFrame({"grp": [1] * 6 + [9] * 3}).to_csv(p, index=False)
    return str(p)


def test_from_sources_public_runs_and_keeps_small_counts(tmp_path):
    sources = [{"alias": "demo", "location": _csv(tmp_path), "level": "public"}]
    res = run_remote_from_sources(SCRIPT, sources)
    assert res["err"] is None, res["err"]
    assert res["results"]
    # public => count 3 survives
    assert ">3<" in res["results"][0] or "3.0" in res["results"][0]


def test_from_sources_protected_suppresses_small_counts(tmp_path):
    sources = [{"alias": "demo", "location": _csv(tmp_path), "level": "protected"}]
    res = run_remote_from_sources(SCRIPT, sources)
    html = res["results"][0]
    assert "NaN" in html
    assert ">3<" not in html and "3.0" not in html
    assert ">6<" in html or "6.0" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/hom/Documents/GitHub/m2py && python -m pytest tests/test_run_remote_from_sources.py -q`
Expected: FAIL — `ImportError: cannot import name 'run_remote_from_sources'`.

- [ ] **Step 3: Write minimal implementation**

```python
# append to m2py_remote.py
from m2py_runtime.sources import read_source
from m2py_protection import resolve_policy


def run_remote_from_sources(script, sources, *, backend="pandas", raw=False):
    """Fetch each registered source into a DataFrame, resolve the protection
    policy (most-restrictive across sources), and run the script.

    `sources` is a list of {"alias", "location", "level"}; `alias` is the
    dataset name the script loads. Real data only — the emulator is not used.
    """
    datasets = {s["alias"]: read_source(s["location"]) for s in sources}
    policy = resolve_policy([s.get("level", "public") for s in sources])
    return run_remote(script, datasets=datasets, backend=backend,
                      policy=policy, raw=raw)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run_remote_from_sources.py -q`
Expected: 2 passed.

- [ ] **Step 5: Full suite + commit**

Run: `python -m pytest -q 2>&1 | tail -2` → no regression.
```bash
git add m2py_remote.py tests/test_run_remote_from_sources.py
git commit -m "feat(safestat): run_remote_from_sources — fetch + policy + run"
```

- [ ] **Step 6: Re-sync the core to the server (report-only first)**

Run: `python sync_to_api.py` → confirm `m2py_remote.py` now shows `drift` (the new function). Then `python sync_to_api.py --apply` to stage it into `microdata-api/server_code/`. (The operator commits/pushes `microdata-api` at the 3b deploy step.)

---

## Part 3b — Anvil glue (microdata-api; deploy-and-verify-live)

> Each task's local check is `python -m py_compile <module>` (syntax only — these modules import `anvil`, so they cannot be imported/run locally). Behavioral verification is the deploy checklist in Task 4.

### Task 2: Minimal source registry

**Files:**
- Create: `microdata-api/server_code/source_registry.py`

**Interfaces:**
- Produces: `resolve_source(source_id: str) -> dict` returning `{"source_id","location","level","kind","status"}`; raises `KeyError` for unknown/`revoked` ids. Seeded with ONE public CSV source.

- [ ] **Step 1: Write the module**

```python
# microdata-api/server_code/source_registry.py
"""Minimal source registry for SafeStat remote compute (v1).

The protection level + location live HERE (server-side), keyed by source_id;
the request only references source_id. v1 is a hardcoded dict with one public
source — the Anvil Data Table + admin CRUD (register/revoke/version, upload,
access policy) is the deferred admin-layer upgrade behind this same
resolve_source() seam.
"""
from __future__ import annotations

# One seeded public source: a public hospital teaching dataset (synthetic;
# cols: lnr, lopenr, innDato, utDato, tilstand_1_1, fodselsar, kjonn; ~100k rows).
_SOURCES = {
    "hospital_public_csv": {
        "source_id": "hospital_public_csv",
        "kind": "url",
        "location": "https://raw.githubusercontent.com/hmelberg/health-analytics-using-python/refs/heads/master/hospital.csv",
        "level": "public",
        "status": "active",
    },
}


def resolve_source(source_id: str) -> dict:
    src = _SOURCES.get(source_id)
    if src is None or src.get("status") != "active":
        raise KeyError(f"unknown or inactive source_id: {source_id!r}")
    return src
```

- [ ] **Step 2: Syntax check**

Run: `python -m py_compile microdata-api/server_code/source_registry.py`
Expected: no output (exit 0).

- [ ] **Step 3: Commit**

```bash
git -C /Users/hom/Documents/GitHub/microdata-api add server_code/source_registry.py
git -C /Users/hom/Documents/GitHub/microdata-api commit -m "feat(safestat): minimal source registry (one seeded public source)"
```

### Task 3: `run_extended` shim + `/run_extended` endpoint + background task

**Files:**
- Modify: `microdata-api/server_code/m2py_shim.py`
- Modify: `microdata-api/server_code/api_endpoints.py`

**Interfaces:**
- Consumes: `m2py_remote.run_remote_from_sources` (synced in 3a Step 6); `source_registry.resolve_source`; the existing `_authenticate_or_fail`, `_load_body`, `_json`, and `anvil.server.launch_background_task` + `/task_status`.
- Produces: `m2py_shim.run_extended(script, sources_req, backend, raw) -> dict`; a `@anvil.server.background_task bg_run_extended(...)`; and `@http_endpoint("/run_extended", POST)` returning `{task_id, mode:"async"}`.

- [ ] **Step 1: Add `run_extended` to `m2py_shim.py`**

```python
# append to microdata-api/server_code/m2py_shim.py

def run_extended(script: str, sources_req, backend: str = "pandas",
                 raw: bool = False) -> dict:
    """Resolve each requested source_id to its registered location+level, then
    run the translator on the real data via the synced m2py_remote core.

    sources_req: list of {"alias": str, "source_id": str}. The protection level
    and location come from the registry, never from the request.
    """
    import m2py_remote
    from source_registry import resolve_source
    bound = []
    for s in sources_req:
        src = resolve_source(s["source_id"])
        bound.append({"alias": s["alias"], "location": src["location"],
                      "level": src["level"]})
    return m2py_remote.run_remote_from_sources(
        script, bound, backend=backend, raw=raw)
```

- [ ] **Step 2: Add the background task + endpoint to `api_endpoints.py`**

```python
# add near the other background tasks / endpoints in api_endpoints.py

@anvil.server.background_task
def bg_run_extended(script, sources_req, backend, raw):
    return m2py_shim.run_extended(script, sources_req, backend=backend, raw=raw)


@anvil.server.http_endpoint("/run_extended", methods=["POST"],
                            cross_site_session=False, enable_cors=True)
def http_run_extended():
    # v1: the seeded source is public, so no auth is required; when a non-public
    # source is referenced this is where authn+authz will gate (deferred).
    body = _load_body()
    script = (body.get("script") or "").strip()
    if not script:
        return _json({"error": "missing 'script'"}, status=400)
    sources_req = body.get("sources") or []
    backend = body.get("backend") or "pandas"
    raw = bool(body.get("raw", False))
    task = anvil.server.launch_background_task(
        "bg_run_extended", script, sources_req, backend, raw)
    return _json({"task_id": task.get_id(), "mode": "async"})
```

- [ ] **Step 3: Syntax check both modules**

Run:
```bash
python -m py_compile microdata-api/server_code/m2py_shim.py microdata-api/server_code/api_endpoints.py
```
Expected: no output (exit 0).

- [ ] **Step 4: Commit**

```bash
git -C /Users/hom/Documents/GitHub/microdata-api add server_code/m2py_shim.py server_code/api_endpoints.py
git -C /Users/hom/Documents/GitHub/microdata-api commit -m "feat(safestat): /run_extended endpoint + bg task + run_extended shim"
```

### Task 4: Deploy + live verification

**Files:** none (operator deploy + manual verification).

- [ ] **Step 1: Push so Anvil deploys**

The operator runs: `git -C /Users/hom/Documents/GitHub/microdata-api push` (this also pushes the Part-2 synced engine + registry + endpoint). Anvil redeploys from GitHub.

- [ ] **Step 2: Smoke-test imports on the server**

In the Anvil server console: `anvil.server.call` is not needed; instead hit the endpoint (next step). If deploy fails on import, the most likely cause is a missing dependency — confirm `pandas`/`numpy` resolve (present via `statsmodels` in `requirements.txt`); `polars` is NOT required for the pandas path.

- [ ] **Step 3: POST a script and poll**

```bash
curl -s -X POST "https://mdataapi.anvil.app/_/api/run_extended" \
  -H "Content-Type: application/json" \
  -d '{"script":"create-dataset demo\ntabulate kjonn","sources":[{"alias":"demo","source_id":"hospital_public_csv"}]}'
# -> {"task_id":"...","mode":"async"}
curl -s "https://mdataapi.anvil.app/_/api/task_status?task_id=<id>"
# -> {"status":"completed","result":{"code":...,"results":[...],"figs":[],...}}
```
Expected: `result.results` contains an HTML frequency table of `kjonn` (sex) from the real ~100k-row hospital CSV — proving the translator ran on server-fetched real data and returned the client-render shape. (`hospital.csv` columns: `lnr, lopenr, innDato, utDato, tilstand_1_1, fodselsar, kjonn`; try `tabulate tilstand_1_1` for a many-category diagnosis table.)

- [ ] **Step 4: Confirm `/run` and `/query` still work** (regression): a quick existing-endpoint call returns as before.

---

## Self-Review

**Spec coverage (the Executor seam's server half + the slice's data flow):**
- "server translates + runs the real translator on a registered source" → Task 1 core + Task 3 shim. ✓
- "request references source_id; level resolved server-side" → Task 2 `resolve_source` + Task 3 shim binds from registry. ✓
- "async submit → poll via /task_status" → Task 3 endpoint launches bg task; existing `/task_status` polls. ✓
- "post-suppress live; returns the client JSON shape" → inherited from `run_remote` via the core. ✓
- "minimal registry, one public source; Data Table deferred" → Task 2 dict. ✓
- Deferred and ABSENT (correct): auth/authz gate, logging, pre-protect, Data Table CRUD, upload, the client `RemoteApiExecutor` wiring (that is the next part — the client half of the Executor seam).

**Placeholder scan:** the seeded source URL is a real public CSV (penguins.csv); swap it for one you control if preferred. No TODOs.

**Type consistency:** `run_remote_from_sources(script, sources=[{alias,location,level}])` is produced in 3a and consumed by `run_extended`, which builds exactly that shape from `resolve_source`'s `{location,level}`. The endpoint passes `sources:[{alias,source_id}]` → shim resolves to `{alias,location,level}`. ✓

---

## Next part (after this is green)

- **Part 4 — client Executor seam** (`index.html`): `LocalPyodideExecutor`/`RemoteApiExecutor` (submit to `/run_extended`, poll `/task_status`, `Authorization: Bearer ${window.mdAuth.token}` only when non-public), `deriveExecutor`, replacing the placeholder at `index.html:7483-7487`. Verified via `node --check` + manual reload against the deployed endpoint. This closes the end-to-end loop the spec's data-flow diagram describes.
