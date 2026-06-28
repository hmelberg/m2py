# SafeStat completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take SafeStat mode from "runs on emulator-mock data" to a usable analysis mode: real external data via `require <url|path>`, an explicit local/remote execution-target seam, rendered plots, on-demand packages for advanced verbs, and polish.

**Architecture:** SafeStat already translates the microdata script to pandas and runs the generated code locally in Pyodide (`runSafeStatScript` in `index.html`), with data currently replayed from the emulator's data-acquisition lines. This plan adds: (1) a translator change so `require <url|path> as d` registers an on-the-fly source that emits `ops.read_source`; (2) browser data resolution that fetches those URLs (Pyodide can't `pd.read_csv(url)`) and feeds them as `datasets`, falling back to emulator-mock; (3) a local/remote execution-target seam; (4) plot rendering; (5) lazy `micropip` for advanced verbs; (6) polish.

**Tech Stack:** Python 3.13 + pandas (translator, pytest-tested); browser JS + Pyodide + Plotly (SafeStat UI, manually/Playwright verified).

## Global Constraints

- **Microdata mode must stay untouched.** SafeStat is additive; the emulator and `manifest=None`/non-SafeStat translation paths must behave exactly as before. The full pytest suite must stay green (baseline `525 passed, 1 xfailed`).
- **Two verification regimes.** Translator changes (Task 1) are **pytest-TDD**. Browser changes (Tasks 2–6) have **no CI harness** here — each browser task ends with a concrete **manual verification** step (load via `python -m http.server`, switch to SafeStat, run a named script, observe). Do not claim a browser task "passes tests"; report the manual observation.
- **Keep the source-kind discipline** (`docs/extended-mode-architecture.md`): all SafeStat-specific behavior lives in the translator's source/require handling or in `runSafeStatScript`; never branch the emulator on mode, never change how existing scripts parse.
- **No new hard dependencies.** DuckDB-backed reading stays a follow-on (`read_source` supports csv/parquet only). Advanced-verb packages load lazily via `micropip` at runtime, not as bundled deps.
- Commit after each task. Branch off `dev`.

**Shared interface introduced in Task 1, used by Task 2:**
`require <url|path> as d [, keys(...)]` where the source ends in `.csv`/`.parquet` makes the emitted program load `d` via `ops.read_source("<url|path>", "<csv|parquet>")`. In the browser, Task 2 rewrites such URL locations to a local Pyodide-FS path it has pre-fetched.

---

### Task 1: `require <url|path>` registers an on-the-fly source (translator)

**Files:**
- Modify: `m2py_translate.py` — `KeyTracker` (class at line 144), `_load_dataset` (line 337), `_load_other` (line 439), the `require` branch (line 869), and the `_emit_merge` `_load_other` calls.
- Test: `tests/test_safestat_sources.py` (new).

**Interfaces:**
- Consumes: `m2py_runtime.manifest._format_from` (existing — infers format from extension).
- Produces: `KeyTracker.source: dict[str,(location,format)]` and `KeyTracker.load_spec(name) -> (location, format) | None` (require-declared source first, then manifest). A bare `require data/p.csv as p` (no manifest) makes `translate()` emit `p_var = ops.read_source("data/p.csv", "csv")`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_safestat_sources.py
import m2py_translate as t


def test_require_url_emits_read_source():
    code = t.translate(
        "require https://h/income.csv as inc\nuse inc\nsummarize wage",
        backend="pandas", source_path=None)
    assert 'ops.read_source(\'https://h/income.csv\', \'csv\')' in code


def test_require_parquet_path_emits_read_source_with_format():
    code = t.translate(
        "require data/persons.parquet as p\nuse p\nkeep if alder > 18",
        backend="pandas", source_path=None)
    assert 'ops.read_source(\'data/persons.parquet\', \'parquet\')' in code


def test_require_registry_name_is_not_a_source():
    # a registry id (no file extension) must NOT become a read_source load
    code = t.translate(
        "require no.ssb.fdb:43 as db\ncreate-dataset persons\ngenerate x = 1\nuse persons",
        backend="pandas", source_path=None)
    assert "read_source(" not in code


def test_require_keys_option_sets_join_key(tmp_path):
    code = t.translate(
        "require a.csv as a, keys(id)\nrequire b.csv as b, keys(id)\n"
        "use b\nmerge v into a",
        backend="pandas", source_path=None)
    assert "left_on='id', right_on='id'" in code
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_safestat_sources.py -q`
Expected: FAIL — no `read_source` emitted (require URL currently only binds from a manifest).

- [ ] **Step 3: Add source tracking + load_spec to KeyTracker**

In `m2py_translate.py`, add the import near the top (after the existing `from m2py_runtime.keys import ...`):

```python
from m2py_runtime.manifest import _format_from
```

Add module-level helper above `class KeyTracker`:

```python
# Extensions that mark a `require` source as a concrete file/URL dataset (vs a
# registry id like "no.ssb.fdb:43"). DuckDB/SQL sources are a follow-on.
_SOURCE_EXTS = (".csv", ".parquet")


def _looks_like_source(s):
    return isinstance(s, str) and s.lower().endswith(_SOURCE_EXTS)
```

In `KeyTracker.__init__`, add the source map (alongside `self.declared_key = {}`):

```python
        self.source = {}          # name -> (location, format): require URL/path or manifest
```

Add two methods to `KeyTracker`:

```python
    def add_source(self, name, location, keys=()):
        self.source[name] = (location, _format_from(location))
        self.cols[name] = set(keys)
        if keys:
            self.declared_key[name] = keys[0]

    def load_spec(self, name):
        """(location, format) for a dataset's data, or None. require-declared
        file/URL sources take precedence, then the manifest."""
        if name in self.source:
            return self.source[name]
        m = self.manifest
        if m is not None and m.has(name):
            return (m.location(name), m.format(name))
        return None
```

- [ ] **Step 4: Register the source in the `require` branch**

In the translate loop's `require` branch (line 869), after computing `src`/`alias`/`bound`, add the file-source case. Replace the branch body with:

```python
        if cmd == "require":
            src = a.get("source") if isinstance(a, dict) else None
            alias = a.get("alias") if isinstance(a, dict) else None
            bound = bool(src and alias and tracker.manifest is not None
                         and tracker.manifest.has(src))
            file_src = bool(src and alias and not bound and _looks_like_source(src))
            if bound:
                tracker.declared_key[alias] = (tracker.manifest.keys(src)[:1] or [None])[0]
                tracker.cols[alias] = set(tracker.manifest.variables(src)) | set(tracker.manifest.keys(src))
            elif file_src:
                _ks = (instr.get("options") or {}).get("keys")
                _keys = _ks.split() if isinstance(_ks, str) else []
                tracker.add_source(alias, src, _keys)
            suffix = (" (bound from manifest)" if bound
                      else " (source)" if file_src else "")
            body.append(f"# {line.strip()}{suffix}")
            continue
```

- [ ] **Step 5: Emit read_source from load_spec in `_load_dataset` / `_load_other`**

Change `_load_dataset` (line 337) to take the tracker and consult `load_spec`:

```python
def _load_dataset(backend, name, source_path, tracker=None):
    """Materialise dataset ``name``: a require/manifest source (read_source) if
    known, else parquet (file mode), else the in-memory ``_load`` helper."""
    var = _dsvar(backend, name)
    spec = tracker.load_spec(name) if tracker is not None else None
    if spec is not None:
        src = f"ops.read_source({spec[0]!r}, {spec[1]!r})"
    elif source_path is not None:
        src = (f'pl.scan_parquet("{name}.parquet")' if backend == "polars"
               else f'pd.read_parquet("{name}.parquet")')
    else:
        src = f"_load({name!r})"
    return f"{var} = {src}"
```

Change `_load_other` (line 439) the same way:

```python
def _load_other(name, backend, known, source_path, tracker=None):
    if name in known:
        return [], _dsvar(backend, name)
    other = _dsvar(backend, name)
    spec = tracker.load_spec(name) if tracker is not None else None
    if spec is not None:
        rhs = f"ops.read_source({spec[0]!r}, {spec[1]!r})"
    elif source_path is not None:
        rhs = (f'pl.scan_parquet("{name}.parquet")' if backend == "polars"
               else f'pd.read_parquet("{name}.parquet")')
    else:
        rhs = f"_load({name!r})"
    return [f"{other} = {rhs}"], other
```

Update the callers to pass `tracker` instead of `tracker.manifest`:
- In `translate()`'s SESSION branch, the two `_load_dataset(backend, a[0], source_path, manifest)` calls become `_load_dataset(backend, a[0], source_path, tracker)`.
- In `_emit_merge`, `_load_other(into, backend, known, source_path, tracker.manifest)` becomes `_load_other(into, backend, known, source_path, tracker)`, and the old-syntax `_load_other(name, backend, known, source_path, tracker.manifest)` becomes `_load_other(name, backend, known, source_path, tracker)`.

- [ ] **Step 6: Run the test + full suite**

Run: `python -m pytest tests/test_safestat_sources.py -q && python -m pytest -q`
Expected: new tests PASS; full suite `529 passed, 1 xfailed` (525 + 4 new). If any prior test regressed, the `_load_dataset`/`_load_other` signature change is the cause — check every call site passes `tracker` (or `None`).

- [ ] **Step 7: Commit**

```bash
git add m2py_translate.py tests/test_safestat_sources.py
git commit -m "feat(translate): require <url|path> registers an on-the-fly read_source"
```

---

### Task 2: SafeStat loads require-declared URL CSVs (browser)

**Files:**
- Modify: `index.html` — `runSafeStatScript` (around line 7453).

**Interfaces:**
- Consumes: Task 1 (the emitted `ops.read_source("<url>", "csv")`).
- Produces: SafeStat run that, before executing, fetches each `require <http(s)-url> as d` CSV/parquet in **JS** (Pyodide can't `pd.read_csv(url)`), writes it to the Pyodide FS at `/home/pyodide/_safestat/<d>.<ext>`, and rewrites the source location to that local path so `read_source` reads it. Sources not declared via a URL `require` keep the emulator-mock data (Task 1a, already done).

**Out of scope for this task (smaller follow-on):** wiring the session's uploaded/sidebar datasets in as `datasets`. The emulator-mock fallback already supplies data for non-URL datasets, so this is a refinement, not a blocker; it would be a one-step addition that reads the shared dataset store into the `_ns["datasets"]` dict.

- [ ] **Step 1: Add URL pre-fetch + local rewrite to `runSafeStatScript`**

In `runSafeStatScript`, before the `py.runPythonAsync` that translates+runs, scan the script for `require <url> as <alias>` lines, fetch each URL via JS, and write to the FS. Insert after `py.globals.set('_ss_src', script);`:

```js
        // Pyodide can't pd.read_csv(url); fetch require'd URLs in JS, write to the
        // FS, and rewrite the script's require lines to the local path so the
        // emitted read_source() reads a local file.
        var _reqRe = /^\s*require\s+(https?:\/\/\S+\.(?:csv|parquet))\s+as\s+(\w+)/gim;
        var _m, _fetches = [];
        var _localScript = script;
        while ((_m = _reqRe.exec(script)) !== null) {
          (function(url, alias){
            _fetches.push(fetch(url).then(function(r){
              if (!r.ok) throw new Error('require ' + url + ' -> HTTP ' + r.status);
              return r.arrayBuffer();
            }).then(function(buf){
              var path = '/home/pyodide/_safestat/' + alias + url.slice(url.lastIndexOf('.'));
              py.FS.mkdirTree('/home/pyodide/_safestat');
              py.FS.writeFile(path, new Uint8Array(buf));
              // rewrite this require's URL to the local path
              _localScript = _localScript.replace(url, path);
            }));
          })(_m[1], _m[2]);
        }
        if (_fetches.length) {
          outputArea.innerHTML = '<div style="padding:8px;opacity:.6">SafeStat: henter ' + _fetches.length + ' datakilde(r)…</div>';
          await Promise.all(_fetches);
        }
        py.globals.set('_ss_src', _localScript);
```

(Move the existing `py.globals.set('_ss_src', script);` to be replaced by the `_localScript` version above — there must be exactly one `_ss_src` set, using `_localScript`.)

- [ ] **Step 2: Manual verification**

Host a small CSV (e.g. `python -m http.server` in a dir with `income.csv` containing `PERSONID_1,wage` rows). Run the app via `python -m http.server` from the repo. Switch to SafeStat. Run:

```
require http://localhost:8000/income.csv as inc
use inc
summarize wage
```

Expected: the output header shows the run; `summarize wage` reflects the **real CSV values** (not mock). Confirm the generated code (the collapsible "Generert Python") contains `ops.read_source('/home/pyodide/_safestat/inc.csv', 'csv')`.

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat(safestat): fetch require'd URL sources to the FS and run on real data"
```

---

### Task 3: Execution-target seam (local now, remote placeholder)

**Files:**
- Modify: `index.html` — `runSafeStatScript` + a small target toggle in the SafeStat run path.

**Interfaces:**
- Produces: a module-level `safeStatTarget` (`'local'` | `'remote'`), defaulting to `'local'`. `runSafeStatScript` routes on it: `'local'` does today's behavior; `'remote'` shows a "compute-to-data (remote) er ikke implementert ennå" message. A single toggle in the output header lets the user switch (so the placeholder is visible and wired).

- [ ] **Step 1: Add the target variable + routing**

Above `runSafeStatScript`, add:

```js
    var safeStatTarget = 'local';   // 'local' | 'remote' (remote = compute-to-data, placeholder)
```

At the very top of `runSafeStatScript` (after the `var py = …` line), add the remote short-circuit:

```js
      if (safeStatTarget === 'remote') {
        outputArea.innerHTML = '<pre class="transl-warn">SafeStat (remote / compute-to-data): '
          + 'ikke implementert ennå — scriptet ville blitt sendt til en server som '
          + 'kjører på data du ikke ser, og bare resultatet returneres. Bruk «local» foreløpig.</pre>';
        return;
      }
```

- [ ] **Step 2: Add a visible toggle in the result header**

Change the `head` string in `runSafeStatScript` to include a toggle link, and wire it. After `outputArea.innerHTML = head + bodyHtml + …;`, add:

```js
        var _tt = document.getElementById('safestatTargetToggle');
        if (_tt) _tt.addEventListener('click', function(e){
          e.preventDefault();
          safeStatTarget = (safeStatTarget === 'local') ? 'remote' : 'local';
          runSafeStatScript(script, ctx);
        });
```

And in the `head` template, replace the `mock-data (emulator) · remote kommer` span with:

```js
          + ' &middot; <a href="#" id="safestatTargetToggle" style="opacity:.8">mål: ' + safeStatTarget + '</a>';
```

- [ ] **Step 3: Manual verification**

In SafeStat, run any script. The header shows `mål: local`. Click it → output switches to the "remote ikke implementert" message and the link would now read `remote`; click again → back to a local run. Confirm no console errors.

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat(safestat): local/remote execution-target seam (remote is a placeholder)"
```

---

### Task 4: Render plots in SafeStat output

**Files:**
- Modify: `index.html` — `runSafeStatScript` (capture figures) + the result rendering.

**Interfaces:**
- Consumes: the translated code leaves plotly `Figure` objects in the exec namespace as `fig_1`, `fig_2`, … (the translator's plot ops return figures).
- Produces: SafeStat collects each `fig_N.to_json()`, returns them in the JSON result as `figs: [json,…]`, and the JS renders each with `Plotly.newPlot` into a `.plotly-container` div.

- [ ] **Step 1: Capture figures in the Python block**

In `runSafeStatScript`'s Python, after `_df = _ns.get("df")`, add figure collection:

```python
_figs = []
for _k in sorted(_ns):
    if _k.startswith("fig_"):
        _f = _ns[_k]
        try:
            _figs.append(_f.to_json())
        except Exception:
            pass
```

and add `"figs": _figs` to the final `_json.dumps({...})`.

- [ ] **Step 2: Render the figures in JS**

In the rendering section of `runSafeStatScript`, after `if (res.html) bodyHtml += res.html;`, add figure placeholders, then render them after `outputArea.innerHTML = …`:

```js
        var _figIds = [];
        (res.figs || []).forEach(function(_fj, _i){
          var _id = 'ssfig_' + _i;
          _figIds.push({ id: _id, json: _fj });
          bodyHtml += '<div class="plotly-container" id="' + _id + '" style="margin-top:8px"></div>';
        });
```

(Place this **before** the `outputArea.innerHTML = head + bodyHtml + …` assignment.) Then after that assignment and the `details pre` line:

```js
        _figIds.forEach(function(_f){
          try {
            var _spec = JSON.parse(_f.json);
            Plotly.newPlot(document.getElementById(_f.id), _spec.data, _spec.layout, {responsive:true});
          } catch (e) { console.warn('safestat plot', e); }
        });
```

- [ ] **Step 3: Manual verification**

In SafeStat run a script that ends with a plot, e.g.:

```
create-dataset persons
import INNTEKT/WLONN as lonn
histogram lonn
```

Expected: a Plotly histogram renders in the output (below any text). Confirm no console errors and the collapsible generated code contains the plot op.

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat(safestat): render plotly figures (fig_N) from the translated run"
```

---

### Task 5: Lazy-install packages for advanced verbs

**Files:**
- Modify: `index.html` — `runSafeStatScript`.

**Interfaces:**
- Produces: before executing, SafeStat detects whether the script uses survival/panel/rdd verbs and `micropip.install`s the needed package (lifelines / linearmodels / rdrobust) with a status message; if install fails, it reports a clear message instead of an opaque ModuleNotFoundError.

- [ ] **Step 1: Detect + install needed packages**

In `runSafeStatScript`, before the translate+run Python block, add a JS map and install pass:

```js
        var _pkgFor = [
          { re: /^\s*(cox|kaplan-meier|kaplan_meier|weibull)\b/im, pkg: 'lifelines' },
          { re: /^\s*(regress-panel|ivregress)\b/im,              pkg: 'linearmodels' },
          { re: /^\s*rdd\b/im,                                     pkg: 'rdrobust' },
        ];
        var _need = _pkgFor.filter(function(p){ return p.re.test(script); }).map(function(p){ return p.pkg; });
        for (var _pi = 0; _pi < _need.length; _pi++) {
          var _pkg = _need[_pi];
          outputArea.innerHTML = '<div style="padding:8px;opacity:.6">SafeStat: installerer ' + _pkg + '…</div>';
          try {
            py.globals.set('_ss_pkg', _pkg);
            await py.runPythonAsync('import micropip as _mp\nawait _mp.install(_ss_pkg)');
          } catch (e) {
            outputArea.innerHTML = '<pre class="error">SafeStat: kunne ikke installere «' + _pkg
              + '» (kreves for dette scriptet) i nettleseren: ' + escapeHtmlOutput(String(e && e.message ? e.message : e)) + '</pre>';
            return;
          }
        }
```

- [ ] **Step 2: Manual verification**

In SafeStat run a `kaplan-meier` script. Expected: a "installerer lifelines…" status, then either the result or a clear install-failure message (NOT a raw `ModuleNotFoundError`). For a basic `regress` script (statsmodels, already present) confirm no install is attempted.

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat(safestat): lazy micropip install for survival/panel/rdd verbs"
```

---

### Task 6: Polish — example, tooltip, accent

**Files:**
- Create: `examples/safestat01_url_csv.txt`.
- Modify: `index.html` — examples menu, mode tooltip; `app.css` — a SafeStat accent (optional).

**Interfaces:** none (UX only).

- [ ] **Step 1: Add a SafeStat example file**

```
# examples/safestat01_url_csv.txt
// SafeStat: analyser en CSV fra en URL uten å laste den ned til deg.
// Bytt URL-en med din egen .csv (kolonner inkl. en nøkkel, f.eks. PERSONID_1).
require https://raw.githubusercontent.com/your/repo/main/income.csv as inc, keys(PERSONID_1)
use inc
summarize wage
histogram wage
```

- [ ] **Step 2: Add the example to the menu + a SafeStat examples section**

In `index.html`, add a `data-section-mode="safestat"` examples block (mirror the existing `data-section-mode="duckdb"` block) containing:

```html
            <div class="examples-section" data-section-mode="safestat">
              <button type="button" data-example="safestat01_url_csv.txt" data-mode="safestat">SafeStat &mdash; CSV fra URL</button>
            </div>
```

- [ ] **Step 3: Update the mode tooltip**

Change the `editorModeBtn` title (line ~394) to include SafeStat:

```html
        <button type="button" class="mode-dropdown-btn" id="editorModeBtn" title="Velg modus (Microdata, Python, R, Statx, jamovi, DuckDB, SafeStat)">
```

- [ ] **Step 4: Manual verification**

Reload, open Examples → SafeStat example loads into SafeStat mode and runs; the mode tooltip lists SafeStat.

- [ ] **Step 5: Commit**

```bash
git add examples/safestat01_url_csv.txt index.html
git commit -m "polish(safestat): URL-CSV example + mode tooltip"
```

---

## Notes for the implementer

- Only Task 1 is pytest-verifiable; run `python -m pytest -q` after it and keep it green. Tasks 2–6 are browser-verified — perform the manual step and report what you observed; do not fabricate a passing test.
- If a browser task can be exercised with the repo's Playwright setup, prefer that and capture the observation; otherwise `python -m http.server` + manual.
- Search by the quoted code, not line numbers, if they have drifted.
- Do **not** add a DuckDB or any bundled dependency; advanced packages load lazily (Task 5).
