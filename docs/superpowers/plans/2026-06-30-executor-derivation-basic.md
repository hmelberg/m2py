# Executor Derivation (basic) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SafeStat *derive* its executor from the source instead of a manual toggle — public data runs local, non-public data runs remote (login-gated), with a bounded `exec(local|remote)` override.

**Architecture:** Server gains a public `/source_info` lookup (`{public, default_exec, location?}`) and an auth gate on `/run_extended` (any remote run requires login). The registry relabels `hospital` non-public (forced remote + suppression) and adds a small public source. The client adds `deriveSafeStatExecutor(script)` — it inspects each `require` line (+ optional `exec()`), looks up named sources, applies most-restrictive-wins, and dispatches to the existing local (Pyodide) or remote (`/run_extended`) path.

**Tech Stack:** Python on Anvil (`microdata-api`, deploy-verify via `py_compile` + curl); browser JS in `index.html` (`node --check` + browser); pytest only where pure-Python logic is locally testable.

## Global Constraints

- **Executor is derived, not toggled.** `public` data → local default; **non-public → forced remote**; **remote always requires login**; local only when data can reach the client. (spec: Core principle.)
- **`exec()` is bounded:** `exec(remote)` always allowed to request (login-gated); `exec(local)` honored **only** if the source is public and not `strict_remote`, else refused with a clear message. (spec: exec() override.)
- **Most-restrictive-wins** across a script's sources: any remote-resolved source ⇒ the whole script runs remote. (spec: Resolution.)
- **Server never trusts a level/exec from the request** — `/source_info` and `/run_extended` resolve from the registry; `/run_extended` authenticates every call (`auth.authenticate_or_fail`). (spec: Auth; Guardrails.)
- **`public` is derived from the existing `level`** (`level == "public"`); `protected`/`sensitive` ⇒ non-public. `default_exec` is a NEW source field, meaningful only for public sources. (spec: Source-declared policy.)
- **`/source_info` omits `location` for non-public sources** (never leak where protected data lives). (spec: /source_info.)
- Both repos: additive only; do not touch the emulator, the translator, `protect`, `run_remote`, or existing endpoints (`/run`, `/query`, `/task_status`, `/run_extended_status`). Server code is GENERATED — but `source_registry.py` and `api_endpoints.py` are server-authored (edit directly, not via sync).
- Deferred (NOT built): `strict_remote` *enforcement* nuance beyond refuse-exec-local, size **measurement**, autocomplete metadata, encrypted/key sources, upload/credentialed-URL residency, per-user remote permission.

---

## File Structure

- **`microdata-api/server_code/source_registry.py`** (modify) — relabel `hospital`, add `demo_public`, add `default_exec`; `resolve_source` unchanged in shape.
- **`microdata-api/server_code/api_endpoints.py`** (modify) — add `/source_info`; add the auth gate to `http_run_extended`.
- **`index.html`** (modify) — add `deriveSafeStatExecutor`; rewire `runSafeStatScript` to derive + dispatch; demote the manual toggle to a where-it-ran indicator; attach token + handle `401` in `runSafeStatRemote`.

---

## Part A — Server (microdata-api; deploy-verify)

### Task A1: Registry — relabel hospital non-public, add public example, add `default_exec`

**Files:**
- Modify: `microdata-api/server_code/source_registry.py`

**Interfaces:**
- Produces: `resolve_source(id)` entries now include `level` and `default_exec`. Two sources: `hospital_public_csv` (`level:"protected"`, non-public), `demo_public_csv` (`level:"public"`, `default_exec:"local"`).

- [ ] **Step 1: Replace `_SOURCES`** in `source_registry.py` with:

```python
_SOURCES = {
    # Non-public fixture: forced remote + login + suppression. (Bytes happen to
    # sit at a public URL, so this tests the EXECUTION path, not data residency.)
    "hospital_public_csv": {
        "source_id": "hospital_public_csv",
        "kind": "url",
        "location": "https://raw.githubusercontent.com/hmelberg/health-analytics-using-python/refs/heads/master/hospital.csv",
        "level": "protected",
        "default_exec": "remote",   # ignored for non-public (always remote); set for clarity
        "status": "active",
    },
    # Public fixture: small CSV, runs LOCAL by default; exec(remote) opts in.
    "demo_public_csv": {
        "source_id": "demo_public_csv",
        "kind": "url",
        "location": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/penguins.csv",
        "level": "public",
        "default_exec": "local",
        "status": "active",
    },
}
```

- [ ] **Step 2: Syntax + behavior check**

Run:
```bash
cd /Users/hom/Documents/GitHub/microdata-api/server_code
python -m py_compile source_registry.py && \
python -c "import source_registry as r; \
print(r.resolve_source('hospital_public_csv')['level'], r.resolve_source('demo_public_csv')['default_exec'])"
```
Expected: `protected local`

- [ ] **Step 3: Commit** (in microdata-api, NO push)

```bash
cd /Users/hom/Documents/GitHub/microdata-api
git add server_code/source_registry.py
git commit -m "feat(safestat): hospital non-public + public demo source + default_exec"
```

### Task A2: `/source_info` lookup endpoint

**Files:**
- Modify: `microdata-api/server_code/api_endpoints.py`

**Interfaces:**
- Consumes: `source_registry.resolve_source`; existing `_json`, `anvil.server.http_endpoint`.
- Produces: `GET /source_info?id=<source_id>` (public) → `{public, default_exec, location?}` or `{error}` (404).

- [ ] **Step 1: Add the endpoint** (place near `http_run_extended_status` in `api_endpoints.py`):

```python
# ---------------------------------------------------------------------------
# /source_info  (PUBLIC lookup: lets the client derive local-vs-remote)


@anvil.server.http_endpoint("/source_info", methods=["GET"],
                            cross_site_session=False, enable_cors=True)
def http_source_info(**kwargs):
    import source_registry
    sid = (kwargs.get("id") or "").strip()
    if not sid:
        return _json({"error": "missing 'id'"}, status=400)
    try:
        src = source_registry.resolve_source(sid)
    except KeyError:
        return _json({"error": f"unknown source: {sid}"}, status=404)
    is_public = src.get("level") == "public"
    out = {"public": is_public,
           "default_exec": src.get("default_exec", "local" if is_public else "remote")}
    # location is returned ONLY for public sources (never leak protected origins)
    if is_public:
        out["location"] = src.get("location")
    return _json(out)
```

- [ ] **Step 2: Syntax check**

Run: `python -m py_compile /Users/hom/Documents/GitHub/microdata-api/server_code/api_endpoints.py`
Expected: no output (exit 0).

- [ ] **Step 3: Commit** (NO push)

```bash
cd /Users/hom/Documents/GitHub/microdata-api
git add server_code/api_endpoints.py
git commit -m "feat(safestat): public /source_info lookup for executor derivation"
```

### Task A3: Auth gate on `/run_extended` (remote requires login)

**Files:**
- Modify: `microdata-api/server_code/api_endpoints.py` (function `http_run_extended`)

**Interfaces:**
- Consumes: the existing `_authenticate_or_fail` (returns `(principal, err)`; `err` is a ready `HttpResponse` on failure — see other endpoints, e.g. `http_query` at line ~80).

- [ ] **Step 1: Add the gate** as the FIRST statements inside `http_run_extended` (before `_load_body()`):

```python
def http_run_extended():
    # Remote execution always requires login (it uses Anvil compute, and
    # non-public sources are forced remote). The server re-resolves each
    # source's level from the registry; it never trusts the request.
    principal, err = _authenticate_or_fail()
    if err:
        return err
    body = _load_body()
    # ... existing body parsing + launch_background_task unchanged ...
```

(Leave the rest of the function — body parsing, `launch_background_task`, the `{task_id, mode}` return — exactly as-is.)

- [ ] **Step 2: Syntax check**

Run: `python -m py_compile /Users/hom/Documents/GitHub/microdata-api/server_code/api_endpoints.py`
Expected: no output (exit 0).

- [ ] **Step 3: Commit** (NO push)

```bash
cd /Users/hom/Documents/GitHub/microdata-api
git add server_code/api_endpoints.py
git commit -m "feat(safestat): /run_extended requires login (remote is gated)"
```

---

## Part B — Client (index.html; node --check + browser)

### Task B1: `deriveSafeStatExecutor(script)`

**Files:**
- Modify: `index.html` (add the function just before `runSafeStatScript`, ~line 7481)

**Interfaces:**
- Consumes: `/source_info`; `localStorage 'md_ai_api_base'`.
- Produces: `async function deriveSafeStatExecutor(script)` → `{ executor:'local'|'remote', cleanScript, localScript, sources:[{alias, source_id|null}], reason, error }`. `cleanScript` strips `, exec(...)` options (so the translator never sees them). `localScript` additionally rewrites public **named** refs to their `location` URL so the local path can fetch them. `error` (string) is set when an `exec(local)` is refused.

- [ ] **Step 1: Add the function**

```javascript
    // Inspect a SafeStat script's `require` lines and decide where it runs.
    // require <X> as <alias> [, exec(local|remote)]
    async function deriveSafeStatExecutor(script) {
      var apiBase = (localStorage.getItem('md_ai_api_base') || 'https://mdataapi.anvil.app').replace(/\/+$/, '');
      var re = /^\s*require\s+(\S+)\s+as\s+(\w+)(?:\s*,\s*exec\(\s*(local|remote)\s*\))?/gim;
      // strip every `, exec(...)` so the translator never sees the option
      var cleanScript = script.replace(/(\brequire\b[^\n]*?)\s*,\s*exec\(\s*(?:local|remote)\s*\)/gi, '$1');
      var localScript = cleanScript;
      var executor = 'local', reason = 'lokal', sources = [], m;
      var refs = [];
      while ((m = re.exec(script)) !== null) refs.push({ raw: m[1], alias: m[2], exec: m[3] || null });
      for (var i = 0; i < refs.length; i++) {
        var ref = refs[i], info, isUrl = /^https?:\/\//i.test(ref.raw);
        if (isUrl) {
          info = { public: true, default_exec: 'local', location: ref.raw };
        } else {
          try {
            info = await fetch(apiBase + '/_/api/source_info?id=' + encodeURIComponent(ref.raw)).then(function(r){ return r.json(); });
          } catch (e) { return { error: 'source_info feilet for «' + ref.raw + '»: ' + (e.message || e) }; }
          if (!info || info.error) return { error: 'ukjent kilde: «' + ref.raw + '»' };
        }
        var refExec;
        if (!info.public) {
          refExec = 'remote';
          if (ref.exec === 'local') return { error: '«' + ref.raw + '» er ikke offentlig — kan ikke kjøres lokalt (kjøres på server).' };
        } else if (info.default_exec === 'strict_remote') {
          refExec = 'remote';
          if (ref.exec === 'local') return { error: '«' + ref.raw + '» er for stor — kun server-kjøring.' };
        } else {
          refExec = ref.exec || (info.default_exec === 'remote' ? 'remote' : 'local');
        }
        if (refExec === 'remote') { executor = 'remote'; reason = info.public ? 'server-kjøring (valgt)' : 'ikke-offentlig kilde'; }
        if (refExec === 'local' && !isUrl && info.location) {
          // substitute the registered name with its public URL so the local path fetches it
          var pat = new RegExp('require\\s+' + ref.raw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s+as\\s+' + ref.alias, 'i');
          localScript = localScript.replace(pat, 'require ' + info.location + ' as ' + ref.alias);
        }
        sources.push({ alias: ref.alias, source_id: isUrl ? null : ref.raw });
      }
      return { executor: executor, cleanScript: cleanScript, localScript: localScript, sources: sources, reason: reason, error: null };
    }
```

- [ ] **Step 2: Syntax check**

Run (from repo root):
```bash
node -e "const fs=require('fs');const h=fs.readFileSync('index.html','utf8');const m=[...h.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x=>x[1]).join('\n;\n');fs.writeFileSync('/tmp/ss_check.js',m);" && node --check /tmp/ss_check.js && echo "node --check OK"
```
Expected: `node --check OK`.

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat(safestat): deriveSafeStatExecutor — infer local/remote from sources"
```

### Task B2: Rewire `runSafeStatScript` to derive + dispatch

**Files:**
- Modify: `index.html` (`runSafeStatScript` start ~line 7561; `runSafeStatRemote` token/401; the local path uses `localScript`)

**Interfaces:**
- Consumes: `deriveSafeStatExecutor` (B1); existing `runSafeStatRemote`, `renderSafeStatResult`, `window.mdAuth`.

- [ ] **Step 1: Replace the toggle short-circuit** at the start of `runSafeStatScript`.

Replace:
```javascript
    async function runSafeStatScript(script, ctx) {
      if (safeStatTarget === 'remote') { await runSafeStatRemote(script, ctx); return; }
      var py = (ctx && ctx.py) || await loadPyodideAndM2py();
```
with:
```javascript
    async function runSafeStatScript(script, ctx) {
      var derived = await deriveSafeStatExecutor(script);
      if (derived.error) { outputArea.innerHTML = '<pre class="error">SafeStat: ' + escapeHtmlOutput(derived.error) + '</pre>'; return; }
      if (derived.executor === 'remote') { await runSafeStatRemote(derived.cleanScript, ctx, derived.sources, derived.reason); return; }
      var script = derived.localScript;   // public-name refs rewritten to their URL; exec() stripped
      var py = (ctx && ctx.py) || await loadPyodideAndM2py();
```
(The local path below continues unchanged — it already fetches `require <url>` refs; `derived.localScript` provides URLs for public named sources. Shadowing `script` with `derived.localScript` is intentional so the existing local code uses the rewritten text.)

- [ ] **Step 2: Update `runSafeStatRemote`'s signature + token + 401**, so it takes the derived sources and surfaces a login prompt. Replace its header and the `sources`/headers/`sub` handling:

```javascript
    async function runSafeStatRemote(script, ctx, sources, reason) {
      var apiBase = (localStorage.getItem('md_ai_api_base') || 'https://mdataapi.anvil.app').replace(/\/+$/, '');
      var token = window.mdAuth && window.mdAuth.token;
      sources = sources || [];
      var headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = 'Bearer ' + token;
      outputArea.innerHTML = '<div style="padding:8px;opacity:.6">SafeStat: sender til server (' + escapeHtmlOutput(reason || 'server-kjøring') + ')…</div>';
      try {
        var resp = await fetch(apiBase + '/_/api/run_extended', {
          method: 'POST', headers: headers,
          body: JSON.stringify({ script: script, sources: sources, backend: 'pandas', raw: safeStatFormat === 'raw' })
        });
        if (resp.status === 401) { outputArea.innerHTML = '<pre class="error">SafeStat: server-kjøring krever innlogging. Logg inn og prøv igjen.</pre>'; return; }
        var sub = await resp.json();
        if (!sub || sub.error || !sub.task_id) { outputArea.innerHTML = '<pre class="error">SafeStat remote: ' + escapeHtmlOutput((sub && sub.error) || 'uventet svar') + '</pre>'; return; }
        var taskId = sub.task_id;
```
(Keep the rest of `runSafeStatRemote` — the poll loop, `renderSafeStatResult(st.result, script, ctx, 'remote · compute-to-data')`, the failed/timeout branches — unchanged. The poll loop already references `taskId`.)

- [ ] **Step 3: Demote the toggle to an indicator.** In `renderSafeStatResult`, the head currently renders a clickable `#safestatTargetToggle`. Change the head's target link to a plain indicator (the executor is now derived, so re-running with the toggle is no longer the mechanism). Replace, in `renderSafeStatResult`:
```javascript
        + ' &middot; <a href="#" id="safestatTargetToggle" style="opacity:.8">mål: ' + safeStatTarget + '</a></div>';
```
with:
```javascript
        + '</div>';
```
and DELETE the toggle-wiring block at the end of `renderSafeStatResult`:
```javascript
      var _tt = document.getElementById('safestatTargetToggle');
      if (_tt) _tt.addEventListener('click', function(e){
        e.preventDefault();
        safeStatTarget = (safeStatTarget === 'local') ? 'remote' : 'local';
        runSafeStatScript(script, ctx);
      });
```
(The `sourceLabel` passed to `renderSafeStatResult` already says "lokal kjøring" or "remote · compute-to-data", so the user still sees where it ran. `safeStatTarget` becomes unused for dispatch — leave the declaration; it's harmless.)

- [ ] **Step 4: Syntax check** (same `node --check` command as B1 Step 2) → `node --check OK`.

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat(safestat): derive executor on run; remote login-gated; toggle -> indicator"
```

---

## Part C — Deploy + verify

### Task C1: Deploy (gated) + live verification

**Files:** none.

- [ ] **Step 1: PAUSE for the operator to push** `microdata-api` master (deploys `/source_info` + the auth gate + the new registry). The controller must NOT push without explicit go (live Anvil). Also push `m2py` `dev`.

- [ ] **Step 2: `/source_info` works (public, no auth)**

```bash
curl -s "https://mdataapi.anvil.app/_/api/source_info?id=demo_public_csv"
# -> {"public":true,"default_exec":"local","location":"https://…/penguins.csv"}
curl -s "https://mdataapi.anvil.app/_/api/source_info?id=hospital_public_csv"
# -> {"public":false,"default_exec":"remote"}   (NO location)
```

- [ ] **Step 3: Remote now requires login (regression of the model)**

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST "https://mdataapi.anvil.app/_/api/run_extended" \
  -H "Content-Type: application/json" \
  -d '{"script":"create-dataset demo\ntabulate kjonn","sources":[{"alias":"demo","source_id":"hospital_public_csv"}]}'
# -> 401   (was 200 before the gate)
```

- [ ] **Step 4: Browser — public source derives LOCAL (no login).** Serve `index.html` locally; in SafeStat run:
```
require demo_public_csv as p
use p
tabulate species
```
Expected: runs **local** (header "SafeStat · lokal kjøring"), shows the species table — Pyodide fetched penguins.csv via the `/source_info` `location`. No login needed.

- [ ] **Step 5: Browser — non-public derives REMOTE + login prompt.** Run:
```
require hospital_public_csv as h
use h
tabulate tilstand_1_1
```
Expected (not logged in): "server-kjøring krever innlogging". After the user logs in (existing app login → `window.mdAuth.token`): runs remote, and the diagnosis table shows **small cells suppressed** (the `protected` level activates `suppress`). This step is the operator's manual verify (needs a real login token).

---

## Self-Review

**Spec coverage:**
- public→local default, non-public→forced remote → B1 derivation + A1 levels. ✓
- remote requires login → A3 gate + B2 token/401. ✓
- `exec()` bounded (remote always, local only public+non-strict) → B1. ✓
- most-restrictive-wins across sources → B1 loop sets `executor='remote'` on any remote ref. ✓
- `/source_info` carries `{public, default_exec, location?}`, omits location for non-public → A2. ✓
- server re-resolves level, never trusts request → A3 (auth) + suppression via existing `run_extended`→`resolve_policy`. ✓
- two fixtures (hospital non-public, demo_public public) → A1. ✓
- toggle demoted to indicator → B2 Step 3. ✓
- Deferred items correctly ABSENT: strict_remote enforcement beyond exec-local-refusal, size measurement, metadata, encryption, upload, per-user permission.

**Placeholder scan:** none — every step has runnable code/commands.

**Type consistency:** `deriveSafeStatExecutor` returns `{executor, cleanScript, localScript, sources, reason, error}` — consumed in B2 Step 1 (`derived.executor/error/cleanScript/localScript/sources/reason`). `runSafeStatRemote(script, ctx, sources, reason)` (B2 Step 2) matches its call in B2 Step 1. `/source_info` shape (`{public, default_exec, location?}`, A2) matches what B1 reads. ✓

---

## Notes for execution
- Parts A and B are independent until deploy (A = microdata-api/Anvil, B = m2py/index.html); B's browser verify needs A deployed. Build A, then B, then Part C deploys both.
- The non-public successful-run + suppression check (C1 Step 5) needs a real login — that's the operator's manual verify; the controller verifies up to the 401.
