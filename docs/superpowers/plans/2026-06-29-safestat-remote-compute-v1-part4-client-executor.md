# SafeStat Remote Compute — v1 Part 4: Client Executor Seam — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the SafeStat editor's `remote` toggle to the live `/run_extended` endpoint — replacing the placeholder — so a script run in remote mode executes server-side (compute-to-data) and renders the result with the editor's existing renderer. Closes the end-to-end v1 loop.

**Architecture:** Extract the inline result-renderer in `runSafeStatScript` into a shared `renderSafeStatResult(res, script, ctx, sourceLabel)` so both executors feed it the same `{code,out,html,n,err,figs,results}` shape. Add `runSafeStatRemote(script, ctx)` — parse registered source bindings, `POST /run_extended`, poll `/run_extended_status`, render. The `local|remote` toggle is the v1 trigger (deriving the executor from source sensitivity is the deferred admin-layer concern). The local Pyodide path is behavior-preserving.

**Tech Stack:** Browser JS inside `index.html` (one inline `<script>`). No JS test harness — verification is `node --check` on the extracted script + a manual/automated reload against the deployed Anvil endpoint (already curl-verified).

## Global Constraints

- **The local Pyodide path stays behavior-identical.** The render extraction must preserve current output exactly; only the head label is parameterized. (no JS tests exist — characterization is by reading + reload.)
- **Remote uses registered sources, not URLs.** In remote mode `require <source_id> as <alias>` binds a registered source; the client sends `sources:[{alias, source_id}]` and the server resolves level/location. The client never sends a protection level. (spec: decision 6.)
- **Reuse existing infra, do not re-add:** API base `= (localStorage.getItem('md_ai_api_base') || 'https://mdataapi.anvil.app').replace(/\/+$/,'')`; auth `= window.mdAuth && window.mdAuth.token` attached as `Authorization: Bearer <token>` **only when present** (public source needs none); `outputArea`, `escapeHtmlOutput`, `safeStatFormat`, `safeStatTarget`, `mdRenderPlotlyFigure` are all in scope. (verified `index.html`.)
- **Endpoints:** `POST <base>/_/api/run_extended` → `{task_id, mode}`; `GET <base>/_/api/run_extended_status?task_id=<id>` → `{status, result?}` (`status` ∈ running/completed/failed/killed). (live-verified Part 3.)
- **Additive/surgical:** only `index.html` changes. The microdata mode and other editor modes are untouched. (spec: front-end reuse.)
- The result shape the renderer consumes: `{code, out, html, n, err, emu_err?, datasets?, figs, results}` (remote omits `emu_err`/`datasets` — the renderer already guards them). (verified `index.html:7605-7641`.)

---

## File Structure

- **Modify `index.html`** (the one inline `<script>`): extract `renderSafeStatResult`, add `runSafeStatRemote`, replace the remote placeholder, and short-circuit the Pyodide load for remote. All within the existing SafeStat scope (near `runSafeStatScript`, ~line 7481).

---

### Task 1: Extract `renderSafeStatResult` (behavior-preserving)

**Files:**
- Modify: `index.html` (render block at ~`7605-7647`)

**Interfaces:**
- Produces: `function renderSafeStatResult(res, script, ctx, sourceLabel)` — renders `res` into `outputArea`, wires the target toggle. Replaces the inline block; the local path calls it.

- [ ] **Step 1: Add the helper** (place it just before `async function runSafeStatScript`, ~line 7481). Body is the current render block with the head label parameterized and `res.n` guarded for `undefined`:

```javascript
    function renderSafeStatResult(res, script, ctx, sourceLabel) {
      var head = '<div style="padding:6px 8px;font-size:12px;opacity:.7">SafeStat &middot; ' + sourceLabel
        + (res.datasets && res.datasets.length ? ' &middot; data: ' + res.datasets.join(', ') : '')
        + (res.n === null || res.n === undefined ? '' : ' &middot; ' + res.n + ' rader')
        + ' &middot; <a href="#" id="safestatTargetToggle" style="opacity:.8">mål: ' + safeStatTarget + '</a></div>';
      var _hasAnalysis = (res.results && res.results.length) || (res.figs && res.figs.length);
      var bodyHtml = '';
      if (res.emu_err) bodyHtml += '<pre class="transl-warn" style="opacity:.75">Data-bygging (emulator): ' + escapeHtmlOutput(res.emu_err) + '</pre>';
      if (res.err) bodyHtml += '<pre class="error">' + escapeHtmlOutput(res.err) + '</pre>';
      if (safeStatFormat === 'raw') {
        if (res.out && res.out.trim()) bodyHtml += '<pre>' + escapeHtmlOutput(res.out) + '</pre>';
      } else {
        (res.results || []).forEach(function(h){ bodyHtml += '<div class="safestat-result">' + h + '</div>'; });
        if (res.out && res.out.trim()) bodyHtml += '<pre style="opacity:.7">' + escapeHtmlOutput(res.out) + '</pre>';
      }
      if (res.html) {
        bodyHtml += _hasAnalysis
          ? '<details style="margin-top:8px"><summary style="cursor:pointer;opacity:.7">Datasett (df, ' + (res.n||0) + ' rader)</summary>' + res.html + '</details>'
          : res.html;
      }
      var _figIds = [];
      (res.figs || []).forEach(function(_fj, _i){
        var _id = 'ssfig_' + _i;
        _figIds.push({ id: _id, json: _fj });
        bodyHtml += '<div class="plotly-container" id="' + _id + '" style="margin-top:8px"></div>';
      });
      if (!bodyHtml) bodyHtml = '<pre style="opacity:.6">(ingen output)</pre>';
      outputArea.innerHTML = head + bodyHtml
        + '<details style="margin-top:8px"><summary style="cursor:pointer;opacity:.7">Generert Python (pandas)</summary><pre class="offline-code"></pre></details>';
      outputArea.querySelector('details pre').textContent = res.code;
      _figIds.forEach(function(_f){
        try {
          var _spec = JSON.parse(_f.json);
          mdRenderPlotlyFigure(document.getElementById(_f.id), _spec);
        } catch (e) { console.warn('safestat plot', e); }
      });
      var _tt = document.getElementById('safestatTargetToggle');
      if (_tt) _tt.addEventListener('click', function(e){
        e.preventDefault();
        safeStatTarget = (safeStatTarget === 'local') ? 'remote' : 'local';
        runSafeStatScript(script, ctx);
      });
    }
```

- [ ] **Step 2: Replace the inline render block** (from `var res = JSON.parse(raw);` through the end of the toggle handler `});` at ~`7647`) with:

```javascript
        var res = JSON.parse(raw);
        renderSafeStatResult(res, script, ctx, 'lokal kjøring');
```

(Leave the surrounding `try { ... } catch (e) { ... }` intact.)

- [ ] **Step 3: Syntax check** — extract the inline script and `node --check` it.

Run (from repo root):
```bash
node -e "const fs=require('fs');const h=fs.readFileSync('index.html','utf8');const m=[...h.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x=>x[1]).join('\n;\n');fs.writeFileSync('/tmp/ss_check.js',m);" && node --check /tmp/ss_check.js && echo "node --check OK"
```
Expected: `node --check OK` (no syntax error).

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "refactor(safestat): extract renderSafeStatResult (shared by local+remote)"
```

---

### Task 2: Add the remote executor + replace the placeholder

**Files:**
- Modify: `index.html` (placeholder at ~`7483-7488`; add `runSafeStatRemote`)

**Interfaces:**
- Consumes: `renderSafeStatResult` (Task 1); the live `/run_extended` + `/run_extended_status` endpoints.
- Produces: `async function runSafeStatRemote(script, ctx)`.

- [ ] **Step 1: Add `runSafeStatRemote`** (place it just before `async function runSafeStatScript`):

```javascript
    async function runSafeStatRemote(script, ctx) {
      var apiBase = (localStorage.getItem('md_ai_api_base') || 'https://mdataapi.anvil.app').replace(/\/+$/, '');
      var token = window.mdAuth && window.mdAuth.token;
      // remote: `require <source_id> as <alias>` binds a REGISTERED source (not a URL).
      var sources = [], _m, _re = /^\s*require\s+(\S+)\s+as\s+(\w+)/gim;
      while ((_m = _re.exec(script)) !== null) sources.push({ alias: _m[2], source_id: _m[1] });
      var headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = 'Bearer ' + token;
      outputArea.innerHTML = '<div style="padding:8px;opacity:.6">SafeStat: sender til server (compute-to-data)…</div>';
      try {
        var sub = await fetch(apiBase + '/_/api/run_extended', {
          method: 'POST', headers: headers,
          body: JSON.stringify({ script: script, sources: sources, backend: 'pandas', raw: safeStatFormat === 'raw' })
        }).then(function(r){ return r.json(); });
        if (!sub || sub.error || !sub.task_id) {
          outputArea.innerHTML = '<pre class="error">SafeStat remote: ' + escapeHtmlOutput((sub && sub.error) || 'uventet svar') + '</pre>';
          return;
        }
        var taskId = sub.task_id;
        for (var i = 0; i < 80; i++) {
          await new Promise(function(r){ setTimeout(r, 1500); });
          var st = await fetch(apiBase + '/_/api/run_extended_status?task_id=' + encodeURIComponent(taskId))
            .then(function(r){ return r.json(); });
          if (st.status === 'completed') { renderSafeStatResult(st.result || {}, script, ctx, 'remote &middot; compute-to-data'); return; }
          if (st.status === 'failed' || st.status === 'killed') {
            outputArea.innerHTML = '<pre class="error">SafeStat remote feilet: ' + escapeHtmlOutput(st.error || st.status) + '</pre>';
            return;
          }
          outputArea.innerHTML = '<div style="padding:8px;opacity:.6">SafeStat: kjører på server… (' + (i + 1) + ')</div>';
        }
        outputArea.innerHTML = '<pre class="error">SafeStat remote: tidsavbrudd (ingen svar fra server)</pre>';
      } catch (e) {
        outputArea.innerHTML = '<pre class="error">SafeStat remote-feil: ' + escapeHtmlOutput(String(e && e.message ? e.message : e)) + '</pre>';
      }
    }
```

- [ ] **Step 2: Replace the placeholder** at ~`7483-7488`. Change the start of `runSafeStatScript` so remote short-circuits BEFORE loading Pyodide:

Replace:
```javascript
    async function runSafeStatScript(script, ctx) {
      var py = (ctx && ctx.py) || await loadPyodideAndM2py();
      if (safeStatTarget === 'remote') {
        outputArea.innerHTML = '<pre class="transl-warn">SafeStat (remote / compute-to-data): '
          + 'ikke implementert ennå — scriptet ville blitt sendt til en server som '
          + 'kjører på data du ikke ser, og bare resultatet returneres. Bruk «local» foreløpig.</pre>';
        return;
      }
```
with:
```javascript
    async function runSafeStatScript(script, ctx) {
      if (safeStatTarget === 'remote') { await runSafeStatRemote(script, ctx); return; }
      var py = (ctx && ctx.py) || await loadPyodideAndM2py();
```

- [ ] **Step 3: Syntax check** (same command as Task 1 Step 3) → `node --check OK`.

- [ ] **Step 4: Update the comment on the `safeStatTarget` declaration** (~`7479`) from `(remote = compute-to-data, placeholder)` to `(remote = compute-to-data via /run_extended)`.

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat(safestat): remote executor — POST /run_extended, poll, render"
```

---

### Task 3: Live browser verification

**Files:** none.

- [ ] **Step 1: Serve + load the editor.** Run a local static server (`python -m http.server 8765` in the repo root) and open `http://localhost:8765/index.html`, switch the editor to SafeStat mode.

- [ ] **Step 2: Run a remote script.** Enter:
```
require hospital_public_csv as demo
use demo
tabulate kjonn
```
Click the `mål:` toggle to `remote` (or run, then toggle) and run.
Expected: after a few "kjører på server…" ticks, the output shows the `kjonn` frequency table (1 ≈ 47452, 2 ≈ 52548) with the header "SafeStat · remote · compute-to-data", and the "Generert Python (pandas)" disclosure shows `ops.tabulate(... vars=['kjonn'] ...)`. This is the same result the Part-3 `curl` returned — now through the UI.

- [ ] **Step 3: Confirm local still works** (regression): toggle back to `local`, run a local script (e.g. a `require <url>.csv as x` script) — it still translates + runs in Pyodide and renders identically.

---

## Self-Review

**Spec coverage (client half of the Executor seam + the data-flow diagram's top half):**
- "RemoteApiExecutor: POST /run_extended, submit-and-poll" → Task 2 `runSafeStatRemote`. ✓
- "deriveExecutor / toggle trigger" → the existing toggle drives local|remote; v1 trigger is the toggle (derivation deferred). ✓
- "render returns the same shape" → Task 1 shared `renderSafeStatResult`. ✓
- "request references source_id; no level from client" → Task 2 builds `sources:[{alias,source_id}]`. ✓
- "token attached only when present" → Task 2 conditional `Authorization`. ✓
- Deferred and ABSENT: source-sensitivity-derived executor, auth-required UX for non-public, an in-editor source picker (remote sources are referenced by `require <source_id> as <alias>` for v1).

**Placeholder scan:** none — full code for both edits.

**Type consistency:** `renderSafeStatResult(res, script, ctx, sourceLabel)` is defined in Task 1 and called by both the local path (Task 1 Step 2) and `runSafeStatRemote` (Task 2). The `res` shape (`{code,out,html,n,err,figs,results}`) matches what `/run_extended_status`'s `result` carries (Part 1/3). ✓

---

## v1 complete after this

With Part 4, the slice is end-to-end: SafeStat editor (remote toggle) → `/run_extended` → server translator on a registered source → suppressed results → rendered in the editor. The full governance vision (auth/authz, logging, pre-protect profiles, upload/admin, encryption executors, multi-language) remains designed-and-deferred per the spec.
