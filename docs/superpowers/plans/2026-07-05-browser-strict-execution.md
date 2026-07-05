# Browser-STRICT Execution Implementation Plan (V1–V4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the safepy STRICT facade (pandas + translated-R) inside Pyodide so scripts behave identically locally and remotely, gated by owner-declared `local_mode`, with per-run server authorization/logging and decrypt-only-at-run hardening.

**Architecture:** safepy ships to the browser as `vendor/safepy.zip` (built by the existing sync script). The SafeResult→client-shape converter moves from `safepy_shim` (server) into `safepy/client_shape.py` (shared). A strict run routes the whole script through `safepy.run(..., profile="strict")` in Pyodide and renders through the existing `renderSafeStatResult`. Server side: `local_mode` on the sources row, grant table in `source_access`, and a `/local_run_authorize` endpoint that logs every run and is the only key channel for strict sources.

**Tech Stack:** Pyodide (pandas included), safepy (pure Python), Anvil HTTP endpoints, Deno tests (JS), pytest (Python), Playwright (browser verification).

**Spec:** `docs/superpowers/specs/2026-07-05-browser-strict-execution-design.md` (m2py repo).

## Global Constraints

- Repos: m2py, microdata-api, safepy — all on `dev`, pushed to `origin dev` after each version completes.
- **A strict source never executes under the open engine, under any failure mode** (hard invariant — every error path refuses the run).
- Nothing from a strict run crosses back into the open session namespace; only rendered releases.
- Norwegian user-facing messages; 404-not-401/403 for denied lookups; keys never logged (reuse `query_audit.scrub_keys`).
- No new JS dependencies. Browser modules use the `(function (global) {...})` pattern.
- safepy engine files change only via the safepy repo + `sync_to_api.py` (GENERATED copies elsewhere).
- Test commands: `python -m pytest tests/ -x -q` per repo; `cd netlify/edge-functions && deno test --allow-read --allow-env _lib/`.
- Versions ship separately: complete + test + commit + push V1 before starting V2, etc.

## File Structure

| File | Repo | Responsibility |
|---|---|---|
| `safepy/client_shape.py` (new) | safepy | SafeResult dict → client result shape (moved from safepy_shim, shared browser/server) |
| `sync_to_api.py` (modify) | m2py | `--web` flag → build `vendor/safepy.zip` |
| `vendor/safepy.zip` (generated) | m2py | safepy package for Pyodide |
| `server_code/safepy_shim.py` (modify) | microdata-api | delegate conversion to `safepy.client_shape` |
| `index.html` (modify) | m2py | `runStrictLocal`, `ensureSafepyLoaded`, strict routing, sidebar badge |
| `server_code/owner_sources.py` (modify) | microdata-api | `local_mode` field |
| `server_code/source_access.py` (modify) | microdata-api | grant table with `local_profile`/`level`; `authorize_local_run` |
| `server_code/source_registry.py` (modify) | microdata-api | `local_mode` in `_row_to_source` |
| `server_code/api_endpoints.py` (modify) | microdata-api | `/local_run_authorize` endpoint |
| `deldata.html` (modify) | m2py | local_mode selector |
| `js/data-loader.js` (modify) | m2py | strict grants: envelope pass-through, authorize callback |
| `js/strict-worker.js` (new, V4) | m2py | isolated Pyodide worker for strict runs |
| `tests/test_client_shape.py` (new) | safepy | conversion tests |
| `tests/test_sync_web.py` (new) | m2py | zip build test |
| `tests/test_source_access.py`, `test_owner_sources.py`, `test_local_authorize.py` | microdata-api | server tests |

---

## V1 — Engine parity

### Task 1: Extract `safepy/client_shape.py` (safepy) + shim delegation (microdata-api)

**Files:**
- Create: `safepy/safepy/client_shape.py`
- Test: `safepy/tests/test_client_shape.py`
- Modify: `microdata-api/server_code/safepy_shim.py` (delete moved code, import instead)
- Run: `python /Users/hom/Documents/GitHub/m2py/sync_to_api.py --apply`

**Interfaces:**
- Produces: `safepy.client_shape.to_client_shape(script: str, d: dict) -> dict` returning `{code, out, html, n, err, figs, results, datasetInfo, audit}`; also `error_shape(script, message) -> dict` and `leaf_fragment(leaf) -> dict | None` (used by the shim's streaming path).

- [ ] **Step 1: Write the failing test**

`safepy/tests/test_client_shape.py`:

```python
"""client_shape: SafeResult dict -> the client result shape that m2py's
renderSafeStatResult consumes. Shared by safepy_shim (server) and the
browser strict runner. Moved from microdata-api/server_code/safepy_shim.py."""
import pandas as pd

import safepy
from safepy import client_shape


def _run(script, level="protected"):
    df = pd.DataFrame({"region": ["A"] * 30 + ["B"] * 30,
                       "x": [i * 1.0 for i in range(60)]})
    res = safepy.run(script, {"df": df}, level=level, profile="strict",
                     dialect="pandas", render="plotly")
    return client_shape.to_client_shape(script, res.as_dict())


def test_groupby_renders_output_table():
    out = _run("df.groupby('region')['x'].mean()")
    assert out["err"] is None
    assert len(out["results"]) == 1
    assert "output-table" in out["results"][0]
    assert out["code"].startswith("df.groupby")


def test_refusal_becomes_err():
    out = _run("df.head()")
    assert out["err"]
    assert out["results"] == []


def test_dataset_info_catalog():
    out = _run("df.groupby('region')['x'].mean()")
    assert "df" in out["datasetInfo"]
    assert out["datasetInfo"]["df"]["nrows"] == 60
    assert "region" in out["datasetInfo"]["df"]["columns"]


def test_error_shape():
    out = client_shape.error_shape("x = 1", "feilmelding")
    assert out["err"] == "feilmelding" and out["code"] == "x = 1"
    assert out["results"] == [] and out["figs"] == []


def test_leaf_fragment_defers_charts():
    frag = client_shape.leaf_fragment({"kind": "chart", "payload": {}})
    assert frag["kind"] == "note"
    frag2 = client_shape.leaf_fragment(
        {"kind": "table", "payload": {"type": "scalar", "stat": "mean", "value": 4}})
    assert frag2["kind"] == "html" and "mean" in frag2["html"]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/hom/Documents/GitHub/safepy && python -m pytest tests/test_client_shape.py -x -q`
Expected: FAIL — `cannot import name 'client_shape'`

- [ ] **Step 3: Create `safepy/safepy/client_shape.py`**

Move VERBATIM from `microdata-api/server_code/safepy_shim.py` the functions
`_error_shape`, `_to_client_shape`, `_fig_json`, `_esc`, `_cell`, `_table`,
`_leaf_html`, `_leaf_fragment` (lines ~133-259 of the shim), renaming the
three public ones (keep the private helpers as-is):

```python
# safepy/client_shape.py
"""SafeResult dict -> the m2py client result shape.

    {code, out, html, n, err, figs, results, datasetInfo, audit}

One implementation shared by microdata-api's safepy_shim (server runs) and
the browser strict runner (Pyodide) — this module is the single seam that
decides the transport format (HTML fragments for tables, plotly JSON for
figures); nothing else knows about it. Pure Python, no Anvil, no safepy
imports (operates on plain dicts from SafeResult.as_dict())."""
from __future__ import annotations

import html as _html
import json


def error_shape(script, message):
    return {"code": script, "out": "", "html": "", "n": None, "err": message,
            "figs": [], "results": [], "datasetInfo": {}, "audit": None}


def to_client_shape(script, d):
    ...  # body copied verbatim from safepy_shim._to_client_shape


def leaf_fragment(leaf):
    ...  # body copied verbatim from safepy_shim._leaf_fragment
```

(The `...` above means: paste the exact existing bodies — this is a move,
not a rewrite. Internal calls `_error_shape(...)` become `error_shape(...)`
etc. Keep `_fig_json`, `_esc`, `_cell`, `_table`, `_leaf_html` private.)

- [ ] **Step 4: Run to verify pass + full safepy suite**

Run: `cd /Users/hom/Documents/GitHub/safepy && python -m pytest tests/test_client_shape.py tests/ -x -q`
Expected: all pass

- [ ] **Step 5: Delegate in `safepy_shim.py`**

In `microdata-api/server_code/safepy_shim.py`: delete the moved function
bodies and replace with imports + thin aliases (the module's public surface
must not change — `run_extended` still calls `_error_shape`, `_to_client_shape`,
`_leaf_fragment` internally):

```python
from safepy import client_shape as _cs

_error_shape = _cs.error_shape
_to_client_shape = _cs.to_client_shape
_leaf_fragment = _cs.leaf_fragment
```

Then run the vendor sync so the Anvil copy gets the new module:

Run: `python /Users/hom/Documents/GitHub/m2py/sync_to_api.py --apply`
Expected: `safepy/client_shape.py` copied; `safepy_shim.py` NOT overwritten (it is not a generated file).

- [ ] **Step 6: Run microdata-api suite**

Run: `cd /Users/hom/Documents/GitHub/microdata-api && python -m pytest tests/ -x -q`
Expected: all pass (the he/enc shim tests exercise the delegated conversion)

- [ ] **Step 7: Commit both repos**

```bash
cd /Users/hom/Documents/GitHub/safepy
git add safepy/client_shape.py tests/test_client_shape.py
git commit -m "refactor(client_shape): shared SafeResult->client-shape converter (moved from safepy_shim)"
cd /Users/hom/Documents/GitHub/microdata-api
git add server_code/
git commit -m "refactor(shim): delegate result conversion to safepy.client_shape"
```

### Task 2: `sync_to_api.py --web` → `vendor/safepy.zip` (m2py)

**Files:**
- Modify: `m2py/sync_to_api.py`
- Create (generated): `m2py/vendor/safepy.zip`
- Test: `m2py/tests/test_sync_web.py`

**Interfaces:**
- Produces: `build_web_zip(safepy_root: Path, out_path: Path) -> list[str]` (returns archive member names); CLI `python sync_to_api.py --web` writes `m2py/vendor/safepy.zip` whose members are `safepy/<mod>.py` and `safepy/adapters/<mod>.py`, each with the GENERATED header.

- [ ] **Step 1: Write the failing test**

`m2py/tests/test_sync_web.py`:

```python
"""--web target: zip the safepy package for Pyodide (browser strict runs)."""
import subprocess
import sys
import zipfile
from pathlib import Path

import sync_to_api

ROOT = Path(sync_to_api.__file__).resolve().parent
SAFEPY_ROOT = ROOT.parent / "safepy" / "safepy"


def test_build_web_zip_members_and_importability(tmp_path):
    out = tmp_path / "safepy.zip"
    members = sync_to_api.build_web_zip(SAFEPY_ROOT, out)
    assert "safepy/__init__.py" in members
    assert "safepy/client_shape.py" in members
    assert "safepy/encfile.py" in members
    assert any(m.startswith("safepy/adapters/") for m in members)
    with zipfile.ZipFile(out) as z:
        header = z.read("safepy/client_shape.py").decode()
    assert "GENERATED COPY" in header

    # the archive must be importable as a package (what Pyodide will do)
    ex = tmp_path / "x"
    with zipfile.ZipFile(out) as z:
        z.extractall(ex)
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, sys.argv[1]); "
         "from safepy import client_shape, encfile; "
         "print(client_shape.error_shape('s', 'm')['err'])",
         str(ex)],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "m"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/hom/Documents/GitHub/m2py && python -m pytest tests/test_sync_web.py -x -q`
Expected: FAIL — `module 'sync_to_api' has no attribute 'build_web_zip'`

- [ ] **Step 3: Implement in `sync_to_api.py`**

Add (reusing the existing `build_manifest`/`_desired_bytes` machinery — read
those functions first and match their signatures):

```python
WEB_ZIP = HERE / "vendor" / "safepy.zip"


def build_web_zip(safepy_root: Path, out_path: Path) -> list[str]:
    """Zip the safepy package (GENERATED headers included) for the browser
    strict runner. Members: safepy/<mod>.py + safepy/adapters/<mod>.py."""
    import zipfile
    h = _generated_header("safepy")
    members = []
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(safepy_root.glob("*.py")):
            name = f"safepy/{p.name}"
            z.writestr(name, _desired_bytes(p, h))
            members.append(name)
        adapters = safepy_root / "adapters"
        if adapters.is_dir():
            for p in sorted(adapters.glob("*.py")):
                name = f"safepy/adapters/{p.name}"
                z.writestr(name, _desired_bytes(p, h))
                members.append(name)
    return members
```

In `main()`, add an argparse flag `--web` (store_true); when set, call
`build_web_zip(Path(args.safepy), WEB_ZIP)` and print the member count.

- [ ] **Step 4: Run test, build the real zip, commit**

```bash
cd /Users/hom/Documents/GitHub/m2py
python -m pytest tests/test_sync_web.py -x -q     # expected: 1 passed
python sync_to_api.py --web                        # writes vendor/safepy.zip
git add sync_to_api.py tests/test_sync_web.py vendor/safepy.zip
git commit -m "feat(sync): --web target builds vendor/safepy.zip for browser strict runs"
```

### Task 3: `runStrictLocal` in index.html (V1 routing via `# options.profile = strict`)

**Files:**
- Modify: `m2py/index.html`

**Interfaces:**
- Consumes: `vendor/safepy.zip` (Task 2), `safepy.client_shape` (Task 1), existing `loadPyodideAndM2py()`, `renderSafeStatResult(res, script, ctx, label)`, `extractScriptOptions` (parses `# options.profile = strict` into `_scriptOpts.profile`), `_pyLoads` items `{alias, format, path}`.
- Produces: `ensureSafepyLoaded(py) -> Promise<void>`; `runStrictLocal(script, loads, opts, ctx) -> Promise<void>` where `opts = {level: string, dialect: 'python'|'r', loads?: [...]}` — used again in V2/V3/V4.

- [ ] **Step 1: Add the two functions** (place next to `runSafeStatRemote`):

```javascript
    // ---- Lokal STRICT-kjøring (spec 2026-07-05-browser-strict-execution) ----
    // safepy-pakken hentes som zip (bygget av sync_to_api.py --web) og pakkes
    // ut i Pyodide. Kritisk invariant: feiler noe her, nektes kjøringen —
    // en strict-kilde kjøres ALDRI på den åpne motoren.
    async function ensureSafepyLoaded(py) {
      if (window.__safepyLoaded) return;
      var resp = await fetch('vendor/safepy.zip');
      if (!resp.ok) throw new Error(t('kunne ikke laste strict-motoren — prøv igjen'));
      var buf = await resp.arrayBuffer();
      py.unpackArchive(buf, 'zip', { extractDir: '/home/pyodide/' });
      window.__safepyLoaded = true;
    }

    // Kjør hele scriptet gjennom safepy STRICT i Pyodide og render resultatet
    // med samme renderer som remote-kjøringer (identisk oppførsel lokalt/remote).
    async function runStrictLocal(script, loads, opts, ctx) {
      var py = await loadPyodideAndM2py();
      await ensureSafepyLoaded(py);
      setStatus(ctx.rightStatus, t('Kjører lokalt i strict-modus…'));
      var glue = [
        'import json, os, secrets',
        '# klient-side salt: støy-nivået er dekorativt lokalt (dokumentert i spec)',
        "os.environ.setdefault('SAFEPY_NOISE_SALT', secrets.token_hex(16))",
        'import pandas as _pd',
        'import safepy',
        'from safepy import client_shape as _cs',
        '_loads = json.loads(' + JSON.stringify(JSON.stringify(loads)) + ')',
        '_frames = {}',
        'for _l in _loads:',
        "    _frames[_l['alias']] = (_pd.read_parquet(_l['path'])",
        "        if _l['format'] == 'parquet' else _pd.read_csv(_l['path']))",
        '_code = ' + JSON.stringify(script),
        '_dialect = ' + JSON.stringify(opts.dialect),
        "if _dialect == 'python':",
        '    _dialect = safepy.detect_python_dialect(_code)',
        'try:',
        '    _res = safepy.run(_code, _frames, level=' + JSON.stringify(opts.level) + ',',
        "                      profile='strict', dialect=_dialect, render='plotly')",
        '    _out = _cs.to_client_shape(_code, _res.as_dict())',
        'except Exception as _e:',
        "    _out = _cs.error_shape(_code, f'{type(_e).__name__}: {_e}')",
        'json.dumps(_out)',
      ].join('\n');
      var out = JSON.parse(await py.runPythonAsync(glue));
      renderSafeStatResult(out, script, ctx, t('lokal · strict'));
      setStatus(ctx.rightStatus, '');
    }
```

(While implementing: check how `setStatus(rightStatus, ...)` is called
elsewhere in the run handler and match it; if `ctx.rightStatus` is the
convention — it is, see `_ctx` construction — keep as written.)

- [ ] **Step 2: Route on the option, python mode**

In the run handler, immediately AFTER the `_pyLoads` block (so web loads are
already on the FS) and before the segment machinery:

```javascript
        // Lokal strict-kjøring (V1: manuelt opt-in via "# options.profile = strict";
        // grant-styrt ruting kommer i V2). Kun python-modus her; r-modus ruter i sin runner.
        if (_scriptOpts.profile === 'strict' && activeEditorMode === 'python') {
          await runStrictLocal(effectiveScript, _pyLoads, { level: 'public', dialect: 'python' }, _ctx);
          return;
        }
```

Note the ordering constraint: `_scriptOpts` is computed at `index.html:8557`
but `_pyLoads` earlier — verify the actual order in the file and place the
strict check after BOTH exist (move the check below the `_scriptOpts`
assignment if needed; `options.` lines are stripped from `effectiveScript`
right after extraction, which is correct — safepy never sees them).

- [ ] **Step 3: Route in R mode**

Find the R runner (`runHybridR`, around `index.html:7396`) where `_dlR` was
added; after the loads are materialized to `_loadsR` file bindings — R-mode
loads bind into webR's FS, not Pyodide's. For strict R runs the frames must
be in PYODIDE. So in the R runner, BEFORE any webR binding:

```javascript
      var _rOpts = extractScriptOptions(src);
      if (_rOpts.profile === 'strict') {
        var _pyLoadsR = [];
        if (_dlR.loads.length) {
          var _pyR = await loadPyodideAndM2py();
          _pyR.FS.mkdirTree('/home/pyodide/_webdata');
          _pyLoadsR = _dlR.loads.map(function (l) {
            var _p = '/home/pyodide/_webdata/' + l.alias + '.' + l.format;
            _pyR.FS.writeFile(_p, l.bytes);
            return { alias: l.alias, format: l.format, path: _p };
          });
        }
        var _srcClean = src.replace(/^\s*(?:#|\/\/)\s*options\.[A-Za-z_]\w*\s*=.*$\n?/gm, '');
        await runStrictLocal(_srcClean, _pyLoadsR, { level: 'public', dialect: 'r' }, { rightStatus: rightStatus });
        return;
      }
```

(Adapt variable names to the R runner's actuals — read the surrounding ~30
lines first; the essential points: strict R never touches webR, frames go to
Pyodide FS, options lines stripped.)

- [ ] **Step 4: Verify in the browser (Playwright)**

Serve (`python -m http.server 8123`), then in python mode run:

```python
#py
# options.profile = strict
# load https://raw.githubusercontent.com/mwaskom/seaborn-data/master/penguins.csv as df
df.groupby('island')['bill_length_mm'].mean()
```

Expected: an output-table renders with the "lokal · strict" label.
Then run `df.head()` with the same options line → a safepy refusal message
renders (NOT five rows of data). Then R mode:

```r
#r
# options.profile = strict
# load https://raw.githubusercontent.com/mwaskom/seaborn-data/master/penguins.csv as df
aggregate(bill_length_mm ~ island, data=df, FUN=mean)
```

Expected: output-table, "lokal · strict".

- [ ] **Step 5: Commit + push V1 (all repos)**

```bash
cd /Users/hom/Documents/GitHub/m2py && git add index.html && git commit -m "feat(strict): V1 — safepy STRICT runs locally in Pyodide (pandas + translated R)"
cd /Users/hom/Documents/GitHub/safepy && git push origin dev
cd /Users/hom/Documents/GitHub/microdata-api && git push origin dev
cd /Users/hom/Documents/GitHub/m2py && git push origin dev
```

---

## V2 — Grant-driven policy

### Task 4: `local_mode` on the server (microdata-api)

**Files:**
- Modify: `server_code/source_registry.py` (`_row_to_source`), `server_code/owner_sources.py` (validation), `server_code/source_access.py` (grant table)
- Test: extend `tests/test_owner_sources.py`, `tests/test_source_access.py`

**Interfaces:**
- Produces: source dicts carry `local_mode: "none"|"strict"|"open"` (default: `"open"` if level public else `"none"`). `access_decision` grants carry `local_profile: "open"|"strict"` and `level`; `local_mode="none"` on a public source → `remote_only`; `local_mode="strict"` on protected/sensitive → grant (strict).

- [ ] **Step 1: Failing tests**

Append to `tests/test_owner_sources.py`:

```python
def test_local_mode_default_by_level():
    raw, _, _ = _env_raw()
    assert owner_sources.validate_registration(_fields(), raw)["local_mode"] == "open"
    v = owner_sources.validate_registration(
        _fields(level="protected", location="https://x.example/d.csv"), CSV)
    assert v["local_mode"] == "none"


def test_local_mode_explicit_strict_on_protected():
    v = owner_sources.validate_registration(
        _fields(level="protected", local_mode="strict",
                location="https://x.example/d.csv"), CSV)
    assert v["local_mode"] == "strict"


def test_local_mode_invalid_refused():
    raw, _, _ = _env_raw()
    with pytest.raises(ValueError, match="local_mode"):
        owner_sources.validate_registration(_fields(local_mode="fri"), raw)
```

Append to `tests/test_source_access.py`:

```python
def test_grant_carries_local_profile_and_level():
    st, p = source_access.access_decision(_src(), "ana@fhi.no")
    assert st == "grant" and p["local_profile"] == "open" and p["level"] == "public"


def test_public_strict_grants_strict_profile():
    st, p = source_access.access_decision(_src(local_mode="strict"), "ana@fhi.no")
    assert st == "grant" and p["local_profile"] == "strict"


def test_public_local_none_is_remote_only():
    st, p = source_access.access_decision(_src(local_mode="none"), "ana@fhi.no")
    assert st == "remote_only"


def test_protected_strict_grants_locally_with_level():
    st, p = source_access.access_decision(
        _src(level="protected", local_mode="strict"), "ana@fhi.no")
    assert st == "grant" and p["local_profile"] == "strict"
    assert p["level"] == "protected" and p["location"]


def test_protected_default_still_remote_only():
    st, p = source_access.access_decision(_src(level="protected"), "ana@fhi.no")
    assert st == "remote_only"
```

Run: `cd /Users/hom/Documents/GitHub/microdata-api && python -m pytest tests/test_owner_sources.py tests/test_source_access.py -q` → new tests FAIL.

- [ ] **Step 2: Implement**

`owner_sources.py` — add near the other constants and inside
`validate_registration` (after `level` validation):

```python
VALID_LOCAL_MODES = {"none", "strict", "open"}
```

```python
    local_mode = (fields.get("local_mode") or "").strip() \
        or ("open" if level == "public" else "none")
    if local_mode not in VALID_LOCAL_MODES:
        raise ValueError(f"local_mode må være en av {sorted(VALID_LOCAL_MODES)}")
```

and include `"local_mode": local_mode,` in the returned dict.

`source_registry._row_to_source` — add:

```python
        "local_mode": _cell(row, "local_mode")
            or ("open" if level == "public" else "none"),
```

`source_access.access_decision` — replace the level check with the grant
table (docstring updated to match):

```python
def access_decision(src: dict, email: str | None):
    """-> (status, payload); status in {"denied", "remote_only", "grant"}.

    Grant table (spec 2026-07-05-browser-strict-execution §2): local_mode
    decides whether rows may reach the browser at all ("none" -> remote_only),
    and under which engine ("open" -> fri analyse, "strict" -> kun safepy-
    fasaden, med nivået fra registreringen som policy-tier)."""
    policy = src.get("access_policy")
    if policy is not None and not email_allowed(email, policy, src.get("owner_email") or ""):
        return "denied", None
    level = src.get("level") or "protected"
    local_mode = src.get("local_mode") or ("open" if level == "public" else "none")
    if local_mode == "none":
        return "remote_only", {"remote_only": True, "default_exec": "remote"}
    out = {
        "remote_only": False,
        "location": src.get("location"),
        "payload_format": src.get("format") or "csv",
        "fingerprint": src.get("fingerprint"),
        "encrypted": src.get("kind") == "encrypted_url",
        "local_profile": "strict" if local_mode == "strict" else "open",
        "level": level,
    }
    if src.get("kind") == "encrypted_url" and src.get("enc_key"):
        from media_crypto import decrypt_bytes
        out["key"] = decrypt_bytes(src["enc_key"].encode("ascii")).decode("ascii")
    return "grant", out
```

NOTE: this makes `local_mode` the gate and `level` the tier — the old
`test_remote_only_for_protected_never_location_never_key` test still passes
because protected defaults to `local_mode="none"`.

- [ ] **Step 3: Run suite, commit**

```bash
cd /Users/hom/Documents/GitHub/microdata-api
python -m pytest tests/ -x -q
git add server_code/ tests/
git commit -m "feat(access): local_mode dimension — none/strict/open gate with level as policy tier"
```

### Task 5: Client obeys the grant (m2py)

**Files:**
- Modify: `js/data-loader.js`, `index.html`, `deldata.html`
- Test: extend `netlify/edge-functions/_lib/data-loader.test.ts`

**Interfaces:**
- Produces: load items gain `strict: true, level: <granted level>` when `grant.local_profile === "strict"`; `runStrictLocal` is invoked with `level` = most restrictive granted level; `updateSidebarDatasets(info, badge)` gains an optional badge string.

- [ ] **Step 1: Failing Deno test**

Append to `_lib/data-loader.test.ts`:

```typescript
Deno.test("strict grant marks the load and carries level", async () => {
  const plain = new TextEncoder().encode("a,b\n1,2\n");
  const { envelope, key } = await EC.encryptBytes(plain, "csv");
  const fetchImpl = ((input: string | URL | Request) => {
    const url = String(input);
    if (url.includes("/source_access")) return Promise.resolve(jsonResp({
      remote_only: false, location: "https://x.example/d.enc.json",
      payload_format: "csv", fingerprint: envelope.fingerprint,
      encrypted: true, local_profile: "strict", level: "protected", key }));
    return Promise.resolve(jsonResp(envelope));
  }) as typeof fetch;
  const out = await DL.resolveAndFetchLoads("# connect helse as h\n# load h as df",
    { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T" });
  assertEquals(out.loads[0].strict, true);
  assertEquals(out.loads[0].level, "protected");
});

Deno.test("open grant leaves strict undefined", async () => {
  const fetchImpl = ((input: string | URL | Request) => {
    const url = String(input);
    if (url.includes("/source_access")) return Promise.resolve(jsonResp({
      remote_only: false, location: "https://x.example/d.csv",
      payload_format: "csv", fingerprint: null, encrypted: false,
      local_profile: "open", level: "public" }));
    return Promise.resolve(new Response("a,b\n1,2", { status: 200, headers: { "content-type": "text/csv" } }));
  }) as typeof fetch;
  const out = await DL.resolveAndFetchLoads("# connect demo as d\n# load d as df",
    { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T" });
  assertEquals(out.loads[0].strict, undefined);
});
```

- [ ] **Step 2: Implement in `data-loader.js`**

In `resolveAndFetchLoads`, where load results are assembled, thread the
grant through:

```javascript
    var loads = await Promise.all(localItems.map(async function (item) {
      var resp = await fetchLoadTarget(item, fetchImpl, deps.authToken || null, deps.anthropicKey || null);
      var buf = new Uint8Array(await resp.arrayBuffer());
      var format = sniffFormat(resp, item.url);
      var dec = await maybeDecrypt(item, buf, format, deps);
      var out = { alias: item.alias, bytes: dec.bytes, format: dec.format };
      if (item.grant && item.grant.local_profile === 'strict') {
        out.strict = true;
        out.level = item.grant.level || 'protected';
      }
      return out;
    }));
```

Run: `cd netlify/edge-functions && deno test --allow-read --allow-env _lib/data-loader.test.ts` → pass.

- [ ] **Step 3: index.html routing + badge**

In the run handler, extend the V1 strict check (python/duckdb block, after
`_pyLoads` is built) — grant-driven now:

```javascript
        var _strictLoads = _rawLoads.filter(function (l) { return l.strict; });
        var _strictRun = _scriptOpts.profile === 'strict' || _strictLoads.length > 0;
        if (_strictRun && activeEditorMode === 'duckdb') {
          outputArea.innerHTML = '<pre class="error">' + t('strict-kilder støttes foreløpig i python/r — ikke duckdb-modus') + '</pre>';
          return;
        }
        if (_strictRun && activeEditorMode === 'python') {
          var _lvOrder = { public: 0, protected: 1, sensitive: 2 };
          var _lvl = 'public';
          _strictLoads.forEach(function (l) { if ((_lvOrder[l.level] || 0) > _lvOrder[_lvl]) _lvl = l.level; });
          if (parseHybridScript(effectiveScript, 'pyodide').some(function (s) { return s.kind === 'microdata'; })) {
            outputArea.innerHTML = '<pre class="error">' + t('strict-kilder kan ikke blandes med #micro-segmenter (ennå)') + '</pre>';
            return;
          }
          await runStrictLocal(effectiveScript, _pyLoads, { level: _lvl, dialect: 'python' }, _ctx);
          return;
        }
```

(The V1 manual check from Task 3 Step 2 is REPLACED by this block. Verify
`parseHybridScript`'s segment `kind` value for micro segments by reading
`matchHybridMarker` — use the actual kind string.) Mirror the same
grant-driven trigger in the R runner (any `_dlR.loads` item with `.strict`
forces the strict path added in Task 3 Step 3, with the max level).

Badge: find `function updateSidebarDatasets(info)` (`index.html:4640`), add
an optional second parameter `badge`; where each dataset row's name is
rendered, append when set:

```javascript
      if (badge) nameHtml += ' <span style="opacity:.55;font-size:11px">(' + badge + ')</span>';
```

(Adapt to the function's actual DOM construction — read it first.) Then in
`runStrictLocal`, render with the badge: replace the
`renderSafeStatResult(out, script, ctx, t('lokal · strict'))` call's sidebar
effect by calling `updateSidebarDatasets(out.datasetInfo || {}, t('kun strict'))`
AFTER `renderSafeStatResult` (which itself calls the un-badged update — the
second call overwrites with badges).

- [ ] **Step 4: deldata.html selector**

After the `fLevel` row, add:

```html
      <div><label for="fLocalMode">Lokal analyse</label>
        <select id="fLocalMode">
          <option value="">automatisk (public → åpen; ellers ingen)</option>
          <option value="open">åpen — vanlig analyse i nettleseren</option>
          <option value="strict">kun strict — bare safepy-fasaden, logget</option>
          <option value="none">ingen — kun server-kjøring</option>
        </select></div>
```

and include it in the register body: `local_mode: $('fLocalMode').value || undefined,`.
Also update the mine-list row to show it: append `' · lokal: ' + esc(s.local_mode || '-')`
and add `"local_mode": _cell(row, "local_mode") or ""` to `_own_summary` in
`owner_sources.py` (microdata-api).

- [ ] **Step 5: Verify (Playwright) + commit + push V2**

Browser check with a stubbed grant: on the served page run in console —
`DataLoader.resolveAndFetchLoads` with an injected `fetchImpl` returning a
strict grant (copy the Deno test's stub) and confirm `loads[0].strict`.
Then a full strict-option run as in Task 3 Step 4 (regression).

```bash
cd /Users/hom/Documents/GitHub/m2py
git add js/data-loader.js index.html deldata.html netlify/edge-functions/_lib/data-loader.test.ts
git commit -m "feat(strict): V2 — grant-driven strict routing, sidebar badge, deldata local_mode"
cd ../microdata-api && git add server_code/ && git commit -m "feat(strict): local_mode in owner summary" && git push origin dev
cd ../m2py && git push origin dev
```

---

## V3 — Accountability

### Task 6: `/local_run_authorize` (microdata-api)

**Files:**
- Modify: `server_code/source_access.py` (pure `authorize_local_run` + stop releasing keys on strict grants), `server_code/api_endpoints.py` (endpoint)
- Test: `tests/test_local_authorize.py` + update `tests/test_source_access.py`

**Interfaces:**
- Produces: `source_access.authorize_local_run(srcs: list[dict], email: str | None) -> tuple[bool, dict, str]` → `(ok, source_keys, level)`; HTTP `POST /local_run_authorize` `{source_ids: [...], script}` → `{ok: true, source_keys, level}` or 404-style refusal; audit row `action="local_strict_run"` with scrubbed script. Strict grants from `/source_access` no longer include `key`.

- [ ] **Step 1: Failing tests**

`tests/test_local_authorize.py`:

```python
"""Per-run authorization for local strict runs (spec V3): every run is
policy-checked and logged; keys flow ONLY through this path for strict."""
import os

from cryptography.fernet import Fernet

os.environ.setdefault("MEDIA_AT_REST_KEY", Fernet.generate_key().decode())

import media_crypto
import source_access


def _src(**kw):
    base = {"source_id": "s", "kind": "encrypted_url",
            "location": "https://x.example/e.json", "format": "csv",
            "level": "protected", "local_mode": "strict",
            "fingerprint": "abc", "enc_key": None,
            "access_policy": {"emails": ["ana@fhi.no"], "domains": []},
            "owner_email": "eier@fhi.no", "status": "active"}
    base.update(kw)
    return base


def test_authorize_denied_wrong_email():
    ok, keys, level = source_access.authorize_local_run([_src()], "x@y.no")
    assert not ok and keys == {}


def test_authorize_denied_local_mode_none():
    ok, _, _ = source_access.authorize_local_run(
        [_src(local_mode="none")], "ana@fhi.no")
    assert not ok


def test_authorize_releases_stored_keys_and_level():
    wrapped = media_crypto.encrypt_bytes(b"K1").decode("ascii")
    ok, keys, level = source_access.authorize_local_run(
        [_src(enc_key=wrapped)], "ana@fhi.no")
    assert ok and keys == {"s": "K1"} and level == "protected"


def test_authorize_mode2_no_stored_key_still_ok():
    ok, keys, level = source_access.authorize_local_run([_src()], "ana@fhi.no")
    assert ok and keys == {}          # analytikeren har nøkkelen selv (mode 2)


def test_authorize_mixed_level_most_restrictive():
    wrapped = media_crypto.encrypt_bytes(b"K1").decode("ascii")
    ok, _, level = source_access.authorize_local_run(
        [_src(enc_key=wrapped), _src(source_id="p", level="sensitive")],
        "ana@fhi.no")
    assert ok and level == "sensitive"
```

Update in `tests/test_source_access.py` — the mode-3 key-release test now
applies only to OPEN grants:

```python
def test_grant_mode3_releases_unwrapped_key():
    wrapped = media_crypto.encrypt_bytes(b"K1").decode("ascii")
    st, p = source_access.access_decision(_src(enc_key=wrapped), "ana@fhi.no")
    assert st == "grant" and p["key"] == "K1"


def test_strict_grant_never_includes_key():
    wrapped = media_crypto.encrypt_bytes(b"K1").decode("ascii")
    st, p = source_access.access_decision(
        _src(enc_key=wrapped, local_mode="strict"), "ana@fhi.no")
    assert st == "grant" and "key" not in p
```

- [ ] **Step 2: Implement**

`source_access.py` — in `access_decision`, guard the key release:

```python
    if (src.get("kind") == "encrypted_url" and src.get("enc_key")
            and out["local_profile"] == "open"):
        from media_crypto import decrypt_bytes
        out["key"] = decrypt_bytes(src["enc_key"].encode("ascii")).decode("ascii")
```

and add:

```python
_LEVEL_ORDER = {"public": 0, "protected": 1, "sensitive": 2}


def authorize_local_run(srcs: list, email: str | None):
    """Per-run gate for local strict runs (spec V3). Every source must allow
    the caller AND allow local execution; returns the per-source stored keys
    (Fernet-unwrapped) and the most restrictive level for the policy tier.
    -> (ok, source_keys, level). Pure; the endpoint logs the audit row."""
    keys, level = {}, "public"
    for src in srcs:
        policy = src.get("access_policy")
        if policy is not None and not email_allowed(email, policy, src.get("owner_email") or ""):
            return False, {}, level
        local_mode = src.get("local_mode") or (
            "open" if (src.get("level") or "protected") == "public" else "none")
        if local_mode == "none":
            return False, {}, level
        if src.get("kind") == "encrypted_url" and src.get("enc_key"):
            from media_crypto import decrypt_bytes
            keys[src["source_id"]] = decrypt_bytes(
                src["enc_key"].encode("ascii")).decode("ascii")
        lv = src.get("level") or "protected"
        if _LEVEL_ORDER.get(lv, 1) > _LEVEL_ORDER[level]:
            level = lv
    return True, keys, level
```

`api_endpoints.py` — after `http_source_access`:

```python
# ---------------------------------------------------------------------------
# /local_run_authorize  (V3: hver lokale strict-kjøring autoriseres og logges;
# nøkler for strict-kilder utleveres KUN her — aldri via /source_access.)


@anvil.server.http_endpoint("/local_run_authorize", methods=["POST"],
                            cross_site_session=False, enable_cors=True)
def http_local_run_authorize():
    import source_registry
    import source_access
    import query_audit
    principal, autherr = _authenticate_or_fail()
    if autherr:
        return _json({"error": "unknown"}, status=404)
    user = auth.principal_user(principal)
    email = user["email"] if user is not None else None
    body = _load_body()
    source_ids = [str(s).strip() for s in (body.get("source_ids") or []) if str(s).strip()]
    script = body.get("script") or ""
    if not source_ids:
        return _json({"error": "missing 'source_ids'"}, status=400)
    srcs = []
    for sid in source_ids:
        try:
            srcs.append(source_registry.resolve_source(sid))
        except KeyError:
            return _json({"error": "unknown"}, status=404)
    ok, keys, level = source_access.authorize_local_run(srcs, email)
    if not ok:
        return _json({"error": "unknown"}, status=404)
    import uuid
    query_audit.log_run(auth.principal_alias(principal), str(uuid.uuid4()),
                        source_ids, level, "local-strict", script,
                        "local_strict_run", None, [], 0)
    return _json({"ok": True, "source_keys": keys, "level": level})
```

(`query_audit.log_run` scrubs the script via `scrub_keys` — already wired.)

- [ ] **Step 3: Run suite, commit**

```bash
cd /Users/hom/Documents/GitHub/microdata-api
python -m pytest tests/ -x -q
git add server_code/ tests/
git commit -m "feat(strict): V3 — /local_run_authorize logs every local strict run; strict keys only per-run"
```

### Task 7: Client authorize flow, no key caching (m2py)

**Files:**
- Modify: `js/data-loader.js`, `index.html`
- Test: extend `_lib/data-loader.test.ts`

**Interfaces:**
- Consumes: `/local_run_authorize` (Task 6).
- Produces: `deps.authorizeStrict(sourceIds: string[]) -> Promise<{[sid]: key}>` — the loader calls it ONCE when strict encrypted items lack keys; the session key cache (`__encKeyCache`) is never used for strict items.

- [ ] **Step 1: Failing Deno test**

```typescript
Deno.test("strict encrypted grant uses authorizeStrict for keys", async () => {
  const plain = new TextEncoder().encode("a\n1\n");
  const { envelope, key } = await EC.encryptBytes(plain, "csv");
  let authorizedWith: string[] = [];
  const fetchImpl = ((input: string | URL | Request) => {
    const url = String(input);
    if (url.includes("/source_access")) return Promise.resolve(jsonResp({
      remote_only: false, location: "https://x.example/d.enc.json",
      payload_format: "csv", fingerprint: envelope.fingerprint,
      encrypted: true, local_profile: "strict", level: "protected" }));
    return Promise.resolve(jsonResp(envelope));
  }) as typeof fetch;
  const out = await DL.resolveAndFetchLoads("# connect helse as h\n# load h as df",
    { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T",
      authorizeStrict: (ids: string[]) => { authorizedWith = ids; return Promise.resolve({ helse: key }); } });
  assertEquals(authorizedWith, ["helse"]);
  assertEquals(new TextDecoder().decode(out.loads[0].bytes), "a\n1\n");
});
```

- [ ] **Step 2: Implement in `data-loader.js`**

In the anvil-item loop, collect strict encrypted items that received no key,
and resolve them via one `authorizeStrict` call BEFORE the fetch/decrypt
`Promise.all`:

```javascript
    var needAuthorize = localItems.filter(function (it) {
      return it.grant && it.grant.local_profile === 'strict' && it.grant.encrypted && !it.grant.key && (!it.key || it.key === 'ask');
    });
    if (needAuthorize.length && deps.authorizeStrict) {
      var runKeys = await deps.authorizeStrict(needAuthorize.map(function (it) { return it.anvil; }));
      needAuthorize.forEach(function (it) {
        if (runKeys && runKeys[it.anvil]) it.grant = Object.assign({}, it.grant, { key: runKeys[it.anvil] });
      });
    }
```

- [ ] **Step 3: index.html — provide the callback + skip cache for strict**

In the deps object passed at both call sites, add:

```javascript
            authorizeStrict: async function (ids) {
              var r = await fetch(getMdApiBase() + '/_/api/local_run_authorize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (getAuthToken() || '') },
                body: JSON.stringify({ source_ids: ids, script: effectiveScript })
              });
              if (!r.ok) throw new Error(t('kjøringen ble ikke autorisert — mangler du tilgang?'));
              var d = await r.json();
              return d.source_keys || {};
            },
```

(In the R runner the script variable is `src` — adapt.) `mdPromptKey`'s
session cache: pass a per-run, uncached prompt for strict items by giving
`maybeDecrypt` access to `item.grant.local_profile` — in `mdPromptKey` usage
nothing changes for mode-1 URL files; strict registered sources never reach
`promptKey` because `authorizeStrict` supplies the key or the run fails.

- [ ] **Step 4: Tests, verify, commit + push V3**

```bash
cd /Users/hom/Documents/GitHub/m2py/netlify/edge-functions && deno test --allow-read --allow-env _lib/
cd /Users/hom/Documents/GitHub/m2py
git add js/data-loader.js index.html netlify/edge-functions/_lib/data-loader.test.ts
git commit -m "feat(strict): V3 client — per-run authorize supplies keys; no caching for strict sources"
git push origin dev
cd ../microdata-api && git push origin dev
```

---

## V4 — Hardening

### Task 8: Decrypt-only-at-run, no plaintext on FS (m2py)

**Files:**
- Modify: `js/data-loader.js`, `index.html`

**Interfaces:**
- Produces: strict encrypted load items return `{alias, envelope (object), key, format, strict: true, level}` — ciphertext, NOT plaintext; `runStrictLocal` accepts these, decrypts INSIDE the Python glue via `safepy.encfile`, and drops frames + keys after the run.

- [ ] **Step 1: Loader — skip JS decryption for strict items**

In `maybeDecrypt`, before decrypting:

```javascript
    if (item.grant && item.grant.local_profile === 'strict') {
      // V4: ingen klartekst i JS/FS for strict — konvolutten sendes videre
      // og dekrypteres først inne i kjøringen (safepy.encfile), spec §V4.
      return { bytes: null, format: env.payload_format || 'csv', envelope: env, key: key };
    }
```

and thread `envelope`/`key` through the load item assembly:

```javascript
      var out = { alias: item.alias, bytes: dec.bytes, format: dec.format };
      if (dec.envelope) { out.envelope = dec.envelope; out.key = dec.key; }
```

Update the Deno strict tests from Tasks 5/7: the strict item now has
`envelope` (an object with `format: "safepy-enc-v1"`) and `key`, and
`bytes: null`.

- [ ] **Step 2: index.html — no FS write for strict items; glue decrypts**

In the `_pyLoads` mapping, skip FS for envelope items:

```javascript
          _pyLoads = _rawLoads.map(function (l) {
            if (l.envelope) return { alias: l.alias, format: l.format, envelope: l.envelope, key: l.key };
            var _path = '/home/pyodide/_webdata/' + l.alias + '.' + l.format;
            py.FS.writeFile(_path, l.bytes);
            return { alias: l.alias, format: l.format, path: _path };
          });
```

In `runStrictLocal`'s glue, replace the frame-building loop with:

```python
_frames = {}
for _l in _loads:
    if _l.get('envelope'):
        from safepy import encfile as _ef
        import io as _io
        _plain = _ef.decrypt_envelope(_l['envelope'], _l['key'])
        _buf = _io.BytesIO(_plain)
        _frames[_l['alias']] = (_pd.read_parquet(_buf)
            if _l['format'] == 'parquet' else _pd.read_csv(_buf))
        del _plain, _buf
    else:
        _frames[_l['alias']] = (_pd.read_parquet(_l['path'])
            if _l['format'] == 'parquet' else _pd.read_csv(_l['path']))
```

and after the run (both success and exception paths), append:

```python
for _k in list(_frames):
    del _frames[_k]
del _frames
import gc as _gc
_gc.collect()
```

(Also blank the key fields: `for _l in _loads: _l.pop('key', None)`.)

- [ ] **Step 3: Verify (Playwright)**

Strict run with an encrypted grant stub, then in the console:
`(await loadPyodideAndM2py()).FS.readdir('/home/pyodide/_webdata')` contains
no strict alias file; `py.runPythonAsync("'_frames' in dir()")` → False.

- [ ] **Step 4: Commit**

```bash
cd /Users/hom/Documents/GitHub/m2py
git add js/data-loader.js index.html netlify/edge-functions/_lib/data-loader.test.ts
git commit -m "feat(strict): V4a — ciphertext-in-memory; decrypt only inside the run, plaintext dropped after"
```

### Task 9: Worker isolation (m2py)

**Files:**
- Create: `js/strict-worker.js`
- Modify: `index.html` (`runStrictLocal` uses the worker; main-thread path stays as fallback — falling back to main-thread STRICT is allowed, falling back to the open engine is NOT)

**Interfaces:**
- Produces: `js/strict-worker.js` — a Web Worker that owns its own Pyodide, loads pandas + safepy.zip, accepts `postMessage({script, loads, level, dialect, pyodideURL, zipURL})` and answers `{ok: true, result}` or `{ok: false, error}`.

- [ ] **Step 1: Find the Pyodide URL**

Run: `grep -n "indexURL\|pyodide.*cdn\|loadPyodide(" /Users/hom/Documents/GitHub/m2py/index.html | head -5` — note the exact `indexURL` used by `loadPyodideAndM2py` and pass the same to the worker.

- [ ] **Step 2: Write `js/strict-worker.js`**

```javascript
// Dedikert Pyodide-worker for lokale STRICT-kjøringer (spec V4): rammer og
// klartekst finnes bare i denne workeren, aldri i hovedtråden. Selvstendig —
// laster egen Pyodide + pandas + safepy.zip ved første kjøring.
'use strict';
var pyReady = null;

function ensurePy(pyodideURL, zipURL) {
  if (pyReady) return pyReady;
  pyReady = (async function () {
    importScripts(pyodideURL + 'pyodide.js');
    var py = await loadPyodide({ indexURL: pyodideURL });
    await py.loadPackage('pandas');
    var resp = await fetch(zipURL);
    if (!resp.ok) throw new Error('kunne ikke laste strict-motoren — prøv igjen');
    py.unpackArchive(await resp.arrayBuffer(), 'zip', { extractDir: '/home/pyodide/' });
    py.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
    return py;
  })();
  return pyReady;
}

self.onmessage = async function (ev) {
  var msg = ev.data || {};
  try {
    var py = await ensurePy(msg.pyodideURL, msg.zipURL);
    var glue = msg.glue;                   // bygges i hovedtråden (samme som før)
    var out = await py.runPythonAsync(glue);
    self.postMessage({ ok: true, result: out });
  } catch (e) {
    self.postMessage({ ok: false, error: String(e && e.message ? e.message : e) });
  }
};
```

- [ ] **Step 3: `runStrictLocal` uses the worker**

Refactor `runStrictLocal` so the glue string is built by a helper
`buildStrictGlue(script, loads, opts)` (same content as today), then:

```javascript
    async function runStrictLocal(script, loads, opts, ctx) {
      var glue = buildStrictGlue(script, loads, opts);
      var out;
      var fsLoads = loads.some(function (l) { return l.path; });
      if (window.Worker && !fsLoads) {
        // Worker-isolasjon: kun når alle rammer kan sendes som data (envelope
        // eller bytes) — FS-stier finnes bare i hovedtrådens Pyodide.
        out = await runStrictInWorker(glue);
      } else {
        var py = await loadPyodideAndM2py();
        await ensureSafepyLoaded(py);
        out = JSON.parse(await py.runPythonAsync(glue));
      }
      renderSafeStatResult(out, script, ctx, t('lokal · strict'));
      updateSidebarDatasets(out.datasetInfo || {}, t('kun strict'));
    }

    var __strictWorker = null;
    function runStrictInWorker(glue) {
      return new Promise(function (resolve, reject) {
        if (!__strictWorker) __strictWorker = new Worker('js/strict-worker.js');
        __strictWorker.onmessage = function (ev) {
          var d = ev.data || {};
          if (d.ok) resolve(JSON.parse(d.result));
          else reject(new Error(d.error || 'strict-worker feilet'));
        };
        __strictWorker.postMessage({
          glue: glue,
          pyodideURL: window.__pyodideIndexURL,   // sett denne der loadPyodideAndM2py definerer indexURL
          zipURL: new URL('vendor/safepy.zip', window.location.href).href,
        });
      });
    }
```

To make the worker path cover plain (non-envelope) web loads too, change the
`_pyLoads` mapping for strict runs to carry `bytes` (as plain latin-safe
base64 or a transferable) instead of FS paths — implementer's choice:
simplest is `btoa`-free: pass `Array.from(l.bytes)` is too slow for big
files; use base64 via the FileReader-free chunked encoder already in
`js/enc-crypto.js` (`b64encode` is not exported — export it as
`EncCrypto._b64encode` and decode in glue with `base64.b64decode`). Add to
the glue's frame loop:

```python
    elif _l.get('bytes_b64'):
        import base64 as _b64, io as _io
        _buf = _io.BytesIO(_b64.b64decode(_l['bytes_b64']))
        _frames[_l['alias']] = (_pd.read_parquet(_buf)
            if _l['format'] == 'parquet' else _pd.read_csv(_buf))
```

- [ ] **Step 4: Verify (Playwright)**

Strict run via worker: result renders; in the MAIN thread console,
`window.py` / main Pyodide has no `_frames` and no `_webdata` strict files;
DevTools shows a `strict-worker.js` worker. Run twice — second run reuses
the warm worker (fast).

- [ ] **Step 5: Commit + push V4**

```bash
cd /Users/hom/Documents/GitHub/m2py
git add js/strict-worker.js js/enc-crypto.js index.html
git commit -m "feat(strict): V4b — dedicated worker isolation for strict runs"
git push origin dev
```

---

### Task 10: Full verification + docs + memory

- [ ] Run all three suites (safepy pytest, microdata-api pytest, m2py deno) — all green.
- [ ] Playwright pass: V1 opt-in strict (pandas + R), refusal parity (`df.head()`), V2 grant routing + badge + duckdb/hybrid refusals, V3 authorize round-trip (stubbed), V4 no-plaintext checks.
- [ ] Update the memory file `encrypted-external-sources.md` (or a new `browser-strict` memory) with what shipped and what's deferred.
- [ ] Push all repos to `origin dev`.

## Self-Review Notes

- Spec coverage: V1→Tasks 1-3, V2→4-5, V3→6-7, V4→8-9, threat model/docs→spec itself + Task 10 memory; deferred list untouched (correct).
- Invariant check: every strict-path failure (`zip fetch`, `authorize`, worker error) throws/refuses — no code path falls through to open execution.
- Type consistency: grant fields `local_profile`/`level` consistent across `source_access.py`, loader, tests; `authorize_local_run` returns `(ok, keys, level)` and the endpoint mirrors `{ok, source_keys, level}`; strict load items `{alias, format, strict, level, envelope?, key?, bytes?}` consistent between Tasks 5, 7, 8, 9.
