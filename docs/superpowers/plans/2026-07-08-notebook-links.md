# Notebook Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a URL load/run a GitHub script as a self-contained notebook — fragment-driven open/autorun, output-only display, always-on prose rendering, and hostname-driven startup mode with repositioned welcome copy.

**Architecture:** Two new pure, unit-tested cores — `js/notebook-links.js` (hash/hostname/welcome resolvers, browser + Node dual-mode) and `notebook_prose.py` (Python AST → markdown-embed transform) — plus wiring into the existing `openFromFragment` (fragment routing), the boot sequence (hostname mode), the welcome module (variants), and the segment run path (prose). Everything reuses machinery that already exists: `setEditor`/`btnRun`, `mdSetInputHidden`, the `__micro_transform_start_markdown__` embed renderer, and the S2 confirmation pattern.

**Tech Stack:** Vanilla browser JS (IIFE modules on `window.*`), Node 26 `node --test` for pure JS, Python 3 + `ast` (pytest), Pyodide/webR run paths. No new runtime dependencies.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-07-08-notebook-links-design.md` — every task traces to it.
- **Two apps:** build in **SafeStat** (`/Users/hom/Documents/GitHub/safestat`, source of truth), then port to **OpenStat** (`/Users/hom/Documents/GitHub/openstat`). App identity via `window.M2PY_APP` (`'safestat'` / `'openstat'`).
- **Embed markers (verbatim):** start line `__micro_transform_start_markdown__`, end line `__micro_transform_end__`; emitted block is `"\n" + START + "\n" + payload + "\n" + END + "\n"` (matches `m2py.py:6527-6529` and the renderer at `index.html:2816`).
- **Template-literal rule:** every backtick inside a JS template literal is escaped `\``; verify each `index.html` edit with `node --check` on the extracted inline `<script>` (the largest block).
- **Autorun trust:** SafeStat always gates; OpenStat autoruns directly UNLESS a stored secret is present (`md_anthropic_key`, `m2py_github_pat`, or a `"pat"` in `m2py_github_profiles`), then it gates too. Output-only suppresses the welcome.
- **Dotted branch resolution:** fetch `main`, on HTTP 404 retry `master`.
- **Prose scope:** Python = top-level bare `str` `Constant` expression statements only (not assigned, not function/class docstrings); R = contiguous `#'` line blocks. Microdata mode unchanged.
- **i18n:** all user-facing strings go through the `t()`/`T()` catalog with EN entries in `js/i18n/en.js`.
- **Engine sync:** `notebook_prose.py` is engine code — after it lands, `sync_to_api.py --apply` propagates it (a later, separate op; not part of a task's commit).

---

## Phase 1 — Pure JS resolvers (`js/notebook-links.js`)

New file is a browser IIFE that also exports under Node for testing:

```js
// js/notebook-links.js  (created incrementally across Tasks 1–4)
(function (global) {
  'use strict';
  var NL = {};
  // ... functions attached to NL ...
  if (typeof module !== 'undefined' && module.exports) module.exports = NL;
  else global.NotebookLinks = NL;
})(typeof window !== 'undefined' ? window : globalThis);
```

Tests run with `node --test tests/js/notebook-links.test.js` (Node 26, built-in runner; `tests/js/` is new).

### Task 1: `hostnameMode(hostname)` — hostname → default editor mode

**Files:**
- Create: `js/notebook-links.js`
- Test: `tests/js/notebook-links.test.js`

**Interfaces:**
- Produces: `NotebookLinks.hostnameMode(hostname: string) -> 'python'|'r'|'duckdb'|'microdata'`

- [ ] **Step 1: Write the failing test**

```js
// tests/js/notebook-links.test.js
const test = require('node:test');
const assert = require('node:assert');
const NL = require('../../js/notebook-links.js');

test('hostnameMode: exact first-label prefixes', () => {
  assert.equal(NL.hostnameMode('py.openstat.app'), 'python');
  assert.equal(NL.hostnameMode('r.safestat.app'), 'r');
  assert.equal(NL.hostnameMode('duck.openstat.app'), 'duckdb');
});
test('hostnameMode: micro substring', () => {
  assert.equal(NL.hostnameMode('micro.safestat.app'), 'microdata');
  assert.equal(NL.hostnameMode('microdata.run'), 'microdata');
});
test('hostnameMode: bare/dev hosts default to python', () => {
  assert.equal(NL.hostnameMode('openstat.app'), 'python');
  assert.equal(NL.hostnameMode('safestat.app'), 'python');
  assert.equal(NL.hostnameMode('localhost'), 'python');
  assert.equal(NL.hostnameMode('deploy-preview-1--safestat.netlify.app'), 'python');
});
test('hostnameMode: no false prefix hit (spy != py)', () => {
  assert.equal(NL.hostnameMode('spy.openstat.app'), 'python'); // falls through to default, still python
  assert.equal(NL.hostnameMode('rstudio.example.com'), 'python'); // 'rstudio' != 'r'
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/js/notebook-links.test.js`
Expected: FAIL — `Cannot find module '../../js/notebook-links.js'`.

- [ ] **Step 3: Write minimal implementation**

```js
// js/notebook-links.js
(function (global) {
  'use strict';
  var NL = {};
  var LABEL_MODE = { py: 'python', r: 'r', duck: 'duckdb' }; // extensible: statx, jamovi

  NL.hostnameMode = function (hostname) {
    var host = String(hostname || '').toLowerCase();
    var firstLabel = host.split('.')[0];
    if (Object.prototype.hasOwnProperty.call(LABEL_MODE, firstLabel)) return LABEL_MODE[firstLabel];
    if (host.indexOf('micro') !== -1) return 'microdata';
    return 'python';
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = NL;
  else global.NotebookLinks = NL;
})(typeof window !== 'undefined' ? window : globalThis);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tests/js/notebook-links.test.js`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add js/notebook-links.js tests/js/notebook-links.test.js
git commit -m "feat(notebook-links): hostnameMode resolver"
```

### Task 2: `classifyHash(hash)` + dotted→URL resolution

**Files:**
- Modify: `js/notebook-links.js`
- Test: `tests/js/notebook-links.test.js`

**Interfaces:**
- Consumes: nothing.
- Produces: `NotebookLinks.classifyHash(hash: string) -> null | { action: 'open'|'output', kind: 'dotted'|'raw'|'share', urls?: string[], raw?: string }`
  - `urls` for `kind:'dotted'` is the candidate list `[mainUrl, masterUrl]` (try in order).
  - `kind:'share'` (existing `#s=`) returns `{ action:'open', kind:'share' }` so the caller defers to the legacy handler.
  - Returns `null` when the hash matches no known shape.

- [ ] **Step 1: Write the failing test**

```js
test('classifyHash: dotted open → main+master candidates', () => {
  const r = NL.classifyHash('#hans.demo.analyses.income.py');
  assert.equal(r.action, 'open');
  assert.equal(r.kind, 'dotted');
  assert.deepEqual(r.urls, [
    'https://raw.githubusercontent.com/hans/demo/main/analyses/income.py',
    'https://raw.githubusercontent.com/hans/demo/master/analyses/income.py',
  ]);
});
test('classifyHash: dotted output prefix', () => {
  const r = NL.classifyHash('#output.hans.demo.income.py');
  assert.equal(r.action, 'output');
  assert.deepEqual(r.urls, [
    'https://raw.githubusercontent.com/hans/demo/main/income.py',
    'https://raw.githubusercontent.com/hans/demo/master/income.py',
  ]);
});
test('classifyHash: raw url fallback', () => {
  const r = NL.classifyHash('#url=https://gist.githubusercontent.com/u/abc/raw/x.py');
  assert.equal(r.action, 'open');
  assert.equal(r.kind, 'raw');
  assert.equal(r.raw, 'https://gist.githubusercontent.com/u/abc/raw/x.py');
});
test('classifyHash: output raw url', () => {
  const r = NL.classifyHash('#output=https://raw.githubusercontent.com/u/rr/main/a.r');
  assert.equal(r.action, 'output');
  assert.equal(r.kind, 'raw');
});
test('classifyHash: legacy share defers', () => {
  assert.deepEqual(NL.classifyHash('#s=H4sIAAA'), { action: 'open', kind: 'share' });
});
test('classifyHash: non-matching returns null', () => {
  assert.equal(NL.classifyHash(''), null);
  assert.equal(NL.classifyHash('#'), null);
  assert.equal(NL.classifyHash('#section-heading'), null);  // no extension / too few tokens
  assert.equal(NL.classifyHash('#only.two'), null);         // needs user.repo.path.ext
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/js/notebook-links.test.js`
Expected: FAIL — `NL.classifyHash is not a function`.

- [ ] **Step 3: Write minimal implementation**

Add inside the IIFE, before the export line:

```js
  var RAW_BASE = 'https://raw.githubusercontent.com/';

  // "user.repo.a.b.file.ext" -> [main url, master url]; null if it can't be a dotted ref.
  NL.resolveDotted = function (dotted) {
    var tokens = String(dotted || '').split('.');
    // need user, repo, >=1 path token, and an extension token => >=4 tokens,
    // last token is the extension, second-to-last+ form the file stem/path.
    if (tokens.length < 4) return null;
    var user = tokens[0], repo = tokens[1];
    var rest = tokens.slice(2);                 // [...path segs..., stem, ext]
    var ext = rest.pop();
    if (!user || !repo || !ext || rest.length < 1) return null;
    var path = rest.join('/') + '.' + ext;      // dots between path segs -> slashes
    return ['main', 'master'].map(function (br) {
      return RAW_BASE + user + '/' + repo + '/' + br + '/' + path;
    });
  };

  NL.classifyHash = function (hash) {
    var h = String(hash || '');
    if (h.charAt(0) === '#') h = h.slice(1);
    if (!h) return null;
    if (/^s=/.test(h)) return { action: 'open', kind: 'share' };

    // raw-url fallback: url=... or output=...
    var mRaw = h.match(/^(output|url)=(.+)$/);
    if (mRaw) {
      return { action: mRaw[1] === 'output' ? 'output' : 'open', kind: 'raw', raw: decodeURIComponent(mRaw[2]) };
    }

    // dotted shorthand, optional "output." prefix
    var action = 'open', dotted = h;
    if (/^output\./.test(h)) { action = 'output'; dotted = h.slice('output.'.length); }
    var urls = NL.resolveDotted(dotted);
    if (!urls) return null;
    return { action: action, kind: 'dotted', urls: urls };
  };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tests/js/notebook-links.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add js/notebook-links.js tests/js/notebook-links.test.js
git commit -m "feat(notebook-links): classifyHash + dotted URL resolution"
```

### Task 3: `welcomeVariant(hostname, app, isOutputOnly)`

**Files:**
- Modify: `js/notebook-links.js`
- Test: `tests/js/notebook-links.test.js`

**Interfaces:**
- Consumes: `NotebookLinks.hostnameMode`.
- Produces: `NotebookLinks.welcomeVariant(hostname, app, isOutputOnly) -> null | 'microdata' | 'openstat_general' | 'safestat_general'`
  - `null` means show no welcome (output-only).

- [ ] **Step 1: Write the failing test**

```js
test('welcomeVariant: output-only shows nothing', () => {
  assert.equal(NL.welcomeVariant('micro.safestat.app', 'safestat', true), null);
});
test('welcomeVariant: micro host → microdata framing (either app)', () => {
  assert.equal(NL.welcomeVariant('microdata.run', 'openstat', false), 'microdata');
  assert.equal(NL.welcomeVariant('micro.safestat.app', 'safestat', false), 'microdata');
});
test('welcomeVariant: general framing per app', () => {
  assert.equal(NL.welcomeVariant('py.openstat.app', 'openstat', false), 'openstat_general');
  assert.equal(NL.welcomeVariant('safestat.app', 'safestat', false), 'safestat_general');
  assert.equal(NL.welcomeVariant('r.safestat.app', 'safestat', false), 'safestat_general');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/js/notebook-links.test.js`
Expected: FAIL — `NL.welcomeVariant is not a function`.

- [ ] **Step 3: Write minimal implementation**

```js
  NL.welcomeVariant = function (hostname, app, isOutputOnly) {
    if (isOutputOnly) return null;
    if (NL.hostnameMode(hostname) === 'microdata') return 'microdata';
    return app === 'safestat' ? 'safestat_general' : 'openstat_general';
  };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tests/js/notebook-links.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add js/notebook-links.js tests/js/notebook-links.test.js
git commit -m "feat(notebook-links): welcomeVariant selector"
```

### Task 4: `rProsePrep(src)` — R `#'` blocks → markdown embed

**Files:**
- Modify: `js/notebook-links.js`
- Test: `tests/js/notebook-links.test.js`

**Interfaces:**
- Produces: `NotebookLinks.rProsePrep(src: string) -> string` — replaces each contiguous run of `#'` lines with a single R `cat(...)` that prints the markdown embed block; all other lines unchanged.

- [ ] **Step 1: Write the failing test**

```js
test('rProsePrep: contiguous #' block becomes one markdown cat', () => {
  const src = "#' # Title\n#' body text\nx <- 1\nprint(x)";
  const out = NL.rProsePrep(src);
  assert.match(out, /cat\(/);
  assert.match(out, /__micro_transform_start_markdown__/);
  assert.match(out, /# Title\\nbody text/);       // joined, prefix stripped
  assert.match(out, /x <- 1\nprint\(x\)/);          // code untouched
});
test('rProsePrep: ordinary # comments untouched', () => {
  const src = "# not prose\ny <- 2";
  assert.equal(NL.rProsePrep(src), src);
});
test('rProsePrep: END marker in content is neutralized', () => {
  const src = "#' hi __micro_transform_end__ there\nz<-3";
  const out = NL.rProsePrep(src);
  assert.doesNotMatch(out.replace(/__micro_transform_end__\\n"\)/,''), /__micro_transform_end__ there/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/js/notebook-links.test.js`
Expected: FAIL — `NL.rProsePrep is not a function`.

- [ ] **Step 3: Write minimal implementation**

```js
  var MD_START = '__micro_transform_start_markdown__';
  var MD_END = '__micro_transform_end__';

  function emitMarkdownR(text) {
    var safe = String(text).split(MD_END).join('');          // neutralize injected end marker
    var block = '\n' + MD_START + '\n' + safe + '\n' + MD_END + '\n';
    return 'cat(' + JSON.stringify(block) + ')';             // JSON string ≈ R double-quoted literal
  }

  NL.rProsePrep = function (src) {
    var lines = String(src == null ? '' : src).split('\n');
    var out = [], buf = null;
    function flush() {
      if (buf && buf.length) out.push(emitMarkdownR(buf.join('\n')));
      buf = null;
    }
    for (var i = 0; i < lines.length; i++) {
      var m = lines[i].match(/^\s*#'\s?(.*)$/);
      if (m) { if (!buf) buf = []; buf.push(m[1]); }
      else { flush(); out.push(lines[i]); }
    }
    flush();
    return out.join('\n');
  };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tests/js/notebook-links.test.js`
Expected: PASS. Also run `node --check js/notebook-links.js` → no output (valid).

- [ ] **Step 5: Commit**

```bash
git add js/notebook-links.js tests/js/notebook-links.test.js
git commit -m "feat(notebook-links): R roxygen prose -> markdown embed"
```

---

## Phase 2 — Python prose transform

### Task 5: `notebook_prose.prep_python_prose(src)`

**Files:**
- Create: `notebook_prose.py`
- Test: `tests/test_notebook_prose.py`

**Interfaces:**
- Produces: `notebook_prose.prep_python_prose(src: str) -> str` — replaces each **top-level** bare-string statement with a `print(...)` that emits the markdown embed block; all other source lines are byte-identical; on `SyntaxError`, returns `src` unchanged (the normal runner surfaces the error).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_notebook_prose.py
import notebook_prose as NP

START = "__micro_transform_start_markdown__"
END = "__micro_transform_end__"

def _run(src):
    """Exec the transformed source, capturing stdout."""
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(NP.prep_python_prose(src), "<t>", "exec"), {})
    return out.getvalue()

def test_toplevel_triple_quoted_becomes_markdown():
    src = '"""# Heading\n\nsome text"""\nprint("code ran")'
    out = _run(src)
    assert START in out and END in out
    assert "# Heading" in out
    assert "code ran" in out
    # markdown appears before the code output (source order preserved)
    assert out.index(START) < out.index("code ran")

def test_single_quoted_bare_string_also_renders():
    src = "'just a note'\nx = 1"
    assert START in NP.prep_python_prose(src)

def test_assigned_string_not_rendered():
    src = 'note = "not prose"\nprint(note)'
    assert START not in NP.prep_python_prose(src)

def test_function_docstring_not_rendered():
    src = 'def f():\n    """docstring"""\n    return 1\nprint(f())'
    assert START not in NP.prep_python_prose(src)

def test_variables_persist_and_order_kept():
    src = 'a = 2\n"""middle"""\nprint(a * 3)'
    out = _run(src)
    assert out.index("middle") < out.index("6")
    assert "6" in out

def test_end_marker_in_text_is_neutralized():
    src = '"""danger __micro_transform_end__ zone"""'
    prepped = NP.prep_python_prose(src)
    # the raw literal END must not survive verbatim inside the payload text
    assert "danger __micro_transform_end__ zone" not in prepped

def test_syntax_error_returns_source_unchanged():
    src = "def broken(:\n"
    assert NP.prep_python_prose(src) == src

def test_no_bare_strings_is_noop():
    src = "x = 1\nprint(x)"
    assert NP.prep_python_prose(src) == src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_notebook_prose.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'notebook_prose'`.

- [ ] **Step 3: Write minimal implementation**

```python
# notebook_prose.py
"""Render top-level bare-string statements as markdown embeds.

A Python script written notebook-style can carry prose as top-level string
literals sitting alone as statements (triple- or single-quoted). This module
rewrites each such statement into a print() that emits the markdown embed
markers the front-end already renders. Strings assigned to names, and
docstrings inside functions/classes, are left as normal code.
"""
import ast

_START = "__micro_transform_start_markdown__"
_END = "__micro_transform_end__"


def _emit_line(text):
    safe = str(text).replace(_END, "")           # neutralize an injected end marker
    payload = "\n" + _START + "\n" + safe + "\n" + _END + "\n"
    return "print(%r)" % (payload,)               # repr escapes everything, reproduces exactly


def prep_python_prose(src):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    spans = []  # (start_line_1based, end_line_1based, text)
    for node in tree.body:
        if (isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            spans.append((node.lineno, node.end_lineno, node.value.value))
    if not spans:
        return src

    lines = src.split("\n")
    start_map = {s[0]: s for s in spans}          # 1-based start line -> span
    covered = set()
    for s in spans:
        for ln in range(s[0], s[1] + 1):
            covered.add(ln)

    out = []
    for i, line in enumerate(lines, start=1):
        if i in start_map:
            out.append(_emit_line(start_map[i][2]))
        elif i in covered:
            continue                              # inside a multi-line prose span already emitted
        else:
            out.append(line)
    return "\n".join(out)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_notebook_prose.py -q`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add notebook_prose.py tests/test_notebook_prose.py
git commit -m "feat(prose): python top-level bare strings -> markdown embed"
```

---

## Phase 3 — SafeStat wiring (`index.html`, `js/github-storage.js`, `js/i18n/en.js`)

Load the new script and set app identity, then wire each surface. After every `index.html` edit: `node --check` the extracted largest inline `<script>` (use this helper, referenced by later tasks):

```bash
# scripts/check_inline.py  (create once; not committed unless useful)
python3 - <<'PY'
import re, subprocess, sys
html = open('index.html').read()
big = max(re.findall(r'<script>(.*?)</script>', html, re.S), key=len)
open('/tmp/_inline.js','w').write(big)
r = subprocess.run(['node','--check','/tmp/_inline.js'], capture_output=True, text=True)
print('OK' if r.returncode==0 else r.stderr); sys.exit(r.returncode)
PY
```

### Task 6: Load `notebook-links.js` + set `window.M2PY_APP`; add hostname startup mode

**Files:**
- Modify: `index.html` — add `<script src>` next to the other `js/*.js` includes; set `window.M2PY_APP`; call the startup-mode resolver in the boot path (near the `md_editor_mode` restore added earlier, before `openFromFragment`).

**Interfaces:**
- Consumes: `NotebookLinks.hostnameMode`, existing `switchEditorMode`, `modeRegistry`.
- Produces: `window.M2PY_APP` (`'safestat'`); initial `activeEditorMode` set from hostname when no persisted mode.

- [ ] **Step 1: Add the script include and app id.** After the existing `<script src="js/github-storage.js">` include, add:

```html
  <script>window.M2PY_APP = 'safestat';</script>
  <script src="js/notebook-links.js"></script>
```

- [ ] **Step 2: Add hostname startup mode.** Find the persisted-mode restore IIFE added after the `editorContent`/`editorBP` declarations (search `md_editor_mode`). Replace its mode-selection so a saved mode still wins, but a fresh session uses the hostname:

```js
      (function restoreEditorMode() {
        try {
          var saved = localStorage.getItem('md_editor_mode');
          var mode = (saved && Object.prototype.hasOwnProperty.call(modeRegistry, saved))
            ? saved
            : (window.NotebookLinks ? window.NotebookLinks.hostnameMode(location.hostname) : 'microdata');
          if (mode && mode !== activeEditorMode && Object.prototype.hasOwnProperty.call(modeRegistry, mode)) {
            switchEditorMode(mode);
          }
        } catch (_) {}
      })();
```

- [ ] **Step 3: Verify inline script parses.**

Run: `python3 scripts/check_inline.py` (the helper above)
Expected: `OK`.

- [ ] **Step 4: Manual smoke.** Serve locally (`python3 -m http.server 8080`), open `http://localhost:8080` → editor boots in **python** mode (bulleted mode label shows Python). Open with a fake host via devtools is not possible; instead confirm the default branch: with no `md_editor_mode` set and `localhost`, mode is python (was microdata before). Note result.

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat(notebook-links): load module, set M2PY_APP, hostname startup mode"
```

### Task 7: Fragment router — open-in-editor for dotted + raw

**Files:**
- Modify: `js/github-storage.js` — extend `openFromFragment` (`js/github-storage.js:125`) to consult `NotebookLinks.classifyHash`; extend `langFromPath` (`:32`) and `setEditor` (`:20`) to accept `duckdb`; add a `fetchFirstOk(urls)` helper (main→master).

**Interfaces:**
- Consumes: `NotebookLinks.classifyHash`, existing `fetchUrl`, `setEditor`, `langFromPath`.
- Produces: `window.mdNotebookAutorun` = `{ url, mode } | null` set when the fragment requests output/autorun (Task 8 consumes it). For `action:'open'`, loads into the editor and leaves autorun null.

- [ ] **Step 1: Extend `langFromPath` for duckdb.** Replace the body:

```js
      function langFromPath(p) {
        const s = (p || '').toLowerCase().split('?')[0];
        if (s.endsWith('.py')) return 'python';
        if (s.endsWith('.r')) return 'r';
        if (s.endsWith('.sql')) return 'duckdb';
        return 'microdata';
      }
```

- [ ] **Step 2: Allow duckdb in `setEditor`.** Change the clamp line in `setEditor`:

```js
        lang = (lang === 'python' || lang === 'r' || lang === 'duckdb') ? lang : 'microdata';
```

- [ ] **Step 3: Add the main→master fetch helper and route new shapes.** Rewrite `openFromFragment`:

```js
      async function fetchFirstOk(urls) {
        for (var i = 0; i < urls.length; i++) {
          try { const r = await fetch(urls[i]); if (r.ok) return await r.text(); } catch (_) {}
        }
        throw new Error('not found (tried main, master)');
      }

      async function loadNotebookScript(urls, primaryUrl) {
        const text = await fetchFirstOk(urls);
        setEditor(text, langFromPath(primaryUrl));
        setCurrent(null);
        const nameEl = $('scriptName');
        if (nameEl) {
          const fn = decodeURIComponent(primaryUrl.split('?')[0].split('/').pop() || '');
          if (fn) nameEl.value = fn.replace(/\.(txt|py|r|sql)$/i, '');
        }
      }

      async function openFromFragment() {
        // Legacy #s= inline share (unchanged), stripped after handling.
        const share = location.hash.match(/[#&]s=([^&]+)/);
        if (share) {
          try {
            const data = JSON.parse(await gunzip(share[1]));
            if (data && typeof data.script === 'string') {
              setEditor(data.script, data.lang);
              setCurrent(null);
              if (data.name && $('scriptName')) $('scriptName').value = data.name;
              toast(T('Delt script åpnet'));
            }
          } catch (e) { console.warn('Kunne ikke åpne delt script fra lenke:', e); }
          finally { history.replaceState(null, document.title, location.pathname + location.search); }
          return;
        }

        // New notebook fragments (dotted / raw). Kept in the URL (durable link).
        const cls = window.NotebookLinks && window.NotebookLinks.classifyHash(location.hash);
        if (!cls || cls.kind === 'share') return;
        const urls = cls.kind === 'raw' ? [cls.raw] : cls.urls;
        const primary = urls[0];
        try {
          await loadNotebookScript(urls, primary);
        } catch (e) {
          if ($('openUrlError')) $('openUrlError').textContent =
            T('Kunne ikke hente notebook-lenken: {msg}', { msg: e.message || e });
          console.warn('notebook fragment load:', e);
          window.mdNotebookAutorun = null;
          return;
        }
        window.mdNotebookAutorun = (cls.action === 'output')
          ? { url: primary, mode: langFromPath(primary) }
          : null;
        if (window.mdNotebookMaybeAutorun) window.mdNotebookMaybeAutorun();
      }
```

- [ ] **Step 4: Verify.** Run `node --check js/github-storage.js` → no output.

- [ ] **Step 5: Manual smoke.** Serve locally; open `http://localhost:8080/#url=https://raw.githubusercontent.com/hmelberg/openstat/main/README.md` → the README text loads into the editor (microdata mode, since `.md`→microdata). Confirm the hash stays in the address bar.

- [ ] **Step 6: Commit**

```bash
git add js/github-storage.js
git commit -m "feat(notebook-links): fragment router loads dotted/raw scripts into editor"
```

### Task 8: Output-only presentation + per-app autorun gate

**Files:**
- Modify: `index.html` — add `window.mdConfirmRun(sourceLabel)`, `mdHasStoredSecret()`, `mdNotebookMaybeAutorun()`, and a "show code" affordance; hook `mdSetInputHidden(true)` for output mode.

**Interfaces:**
- Consumes: `window.mdNotebookAutorun` (Task 7), `window.M2PY_APP` (Task 6), `scriptRunInProgress`, `mdSetInputHidden`, `btnRun`.
- Produces: `window.mdNotebookMaybeAutorun()` — resolves the trust rule and runs; `window.mdConfirmRun(label) -> Promise<boolean>`.

- [ ] **Step 1: Write a Node assertion for the pure trust rule.** The DOM-free part is the trust decision; extract it into `NotebookLinks.autorunNeedsGate(app, hasSecret)` and test it.

```js
// tests/js/notebook-links.test.js  (append)
test('autorunNeedsGate: safestat always gates', () => {
  assert.equal(NL.autorunNeedsGate('safestat', false), true);
  assert.equal(NL.autorunNeedsGate('safestat', true), true);
});
test('autorunNeedsGate: openstat gates only when a secret is present', () => {
  assert.equal(NL.autorunNeedsGate('openstat', false), false);
  assert.equal(NL.autorunNeedsGate('openstat', true), true);
});
```

- [ ] **Step 2: Run to verify it fails.**

Run: `node --test tests/js/notebook-links.test.js`
Expected: FAIL — `NL.autorunNeedsGate is not a function`.

- [ ] **Step 3: Implement the pure rule in `js/notebook-links.js`.**

```js
  NL.autorunNeedsGate = function (app, hasSecret) {
    return app === 'safestat' || !!hasSecret;
  };
```

Run: `node --test tests/js/notebook-links.test.js` → PASS.

- [ ] **Step 4: Add the DOM wiring in `index.html`** (inside the main inline script, near the other `window.md*` helpers). `mdConfirmRun` reuses the `ai-modal-backdrop` styling:

```js
    window.mdHasStoredSecret = function () {
      try {
        if (localStorage.getItem('md_anthropic_key')) return true;
        if (localStorage.getItem('m2py_github_pat')) return true;
        var p = localStorage.getItem('m2py_github_profiles');
        if (p && /"pat"\s*:\s*"[^"]/.test(p)) return true;
      } catch (_) {}
      return false;
    };

    window.mdConfirmRun = function (sourceLabel) {
      return new Promise(function (resolve) {
        var ok = window.confirm(
          t('Kjøre scriptet fra {src}? Det kjører kode i nettleseren din.', { src: sourceLabel || t('lenken') }));
        resolve(!!ok);
      });
    };

    window.mdNotebookMaybeAutorun = async function () {
      var req = window.mdNotebookAutorun;
      if (!req) return;
      window.mdNotebookAutorun = null;                 // consume once
      if (window.mdSetInputHidden) window.mdSetInputHidden(true);   // output-only
      window.mdShowCodeAffordance && window.mdShowCodeAffordance();
      var app = window.M2PY_APP || 'safestat';
      var needGate = window.NotebookLinks.autorunNeedsGate(app, window.mdHasStoredSecret());
      if (needGate) {
        var ok = await window.mdConfirmRun(req.url);
        if (!ok) { if (window.mdSetInputHidden) window.mdSetInputHidden(false); return; }
      }
      if (scriptRunInProgress) return;
      document.getElementById('btnRun').click();
    };
```

- [ ] **Step 5: Add the "show code" affordance.** Add a hidden button in the output toolbar markup (near `#outputArea`), and its handler:

```html
  <button type="button" id="notebookShowCode" class="ai-modal-btn" style="display:none" data-i18n>‹ Vis kode</button>
```

```js
    window.mdShowCodeAffordance = function () {
      var b = document.getElementById('notebookShowCode');
      if (!b) return;
      b.style.display = '';
      b.onclick = function () { if (window.mdSetInputHidden) window.mdSetInputHidden(false); b.style.display = 'none'; };
    };
```

- [ ] **Step 6: Verify.** `python3 scripts/check_inline.py` → `OK`; `node --test tests/js/notebook-links.test.js` → PASS.

- [ ] **Step 7: Manual smoke.** Local serve; open `#output=<raw url to a tiny .py that prints hello>` → SafeStat shows the confirm; on OK the editor is hidden and only output shows, with a "‹ Vis kode" button that reveals the editor.

- [ ] **Step 8: Commit**

```bash
git add index.html js/notebook-links.js tests/js/notebook-links.test.js
git commit -m "feat(notebook-links): output-only display + per-app autorun gate"
```

### Task 9: Welcome variants + suppress on output-only

**Files:**
- Modify: `index.html` — welcome module (`index.html:1409`, `show()` at `:1445`); the welcome markup (`:437-465`).
- Modify: `js/i18n/en.js` — EN strings for the three variants.

**Interfaces:**
- Consumes: `NotebookLinks.welcomeVariant`, `window.M2PY_APP`, `window.mdNotebookAutorun` (truthy ⇒ output-only).

- [ ] **Step 1: Replace the welcome heading/body markup** (`index.html:439-446`) with three data-holders keyed by variant, all hidden by default:

```html
      <h3 style="font-size:20px;" id="welcomeHeading" data-i18n>Velkommen!</h3>
      <div id="welcomeBodyMicro" class="welcome-body" data-i18n-html>
        Øv på å kjøre analyser i microdata.no-stil. Inneholder ikke ekte tall; et hobbyprosjekt, ikke laget av microdata.no.
      </div>
      <div id="welcomeBodyOpen" class="welcome-body" style="display:none" data-i18n-html>
        OpenStat er en motor for å stille spørsmål som kan besvares med kode og statistikk — og for å se og endre koden som gir svaret. Skriv i Python, R, DuckDB eller microdata-stil; kjør i nettleseren.
      </div>
      <div id="welcomeBodySafe" class="welcome-body" style="display:none" data-i18n-html>
        SafeStat gjør det samme, og kan i tillegg dele og gi tilgang til sensitive data: bare analyser som bruker et begrenset sett kommandoer slipper gjennom, slik at resultatene viser aggregater — aldri opplysninger om enkeltpersoner.
      </div>
```

- [ ] **Step 2: Select the variant in `show()`.** At the top of `show()` (`index.html:1445`), before the dismissal check, add:

```js
      function show() {
        var isOutputOnly = !!window.mdNotebookAutorun;
        var variant = window.NotebookLinks
          ? window.NotebookLinks.welcomeVariant(location.hostname, window.M2PY_APP || 'safestat', isOutputOnly)
          : 'microdata';
        if (variant === null) return;                 // output-only: no welcome
        var bodies = { microdata: 'welcomeBodyMicro', openstat_general: 'welcomeBodyOpen', safestat_general: 'welcomeBodySafe' };
        ['welcomeBodyMicro', 'welcomeBodyOpen', 'welcomeBodySafe'].forEach(function (id) {
          var el = document.getElementById(id); if (el) el.style.display = (id === bodies[variant]) ? '' : 'none';
        });
        var heading = document.getElementById('welcomeHeading');
        if (heading) heading.textContent = (variant === 'microdata')
          ? t('Velkommen!')
          : t('Velkommen til {app}!', { app: (window.M2PY_APP === 'safestat' ? 'SafeStat' : 'OpenStat') });
        if (localStorage.getItem(LS_KEY) === '1') return;
        // ... existing show() body continues (backdrop display, tip, etc.) ...
```

- [ ] **Step 3: Add EN strings.** In `js/i18n/en.js` add entries for each new NO string (headings + the three bodies + `‹ Vis kode` + the confirm-run + the notebook fetch-error). Example (repeat the pattern for every new NO literal introduced in Tasks 6–9):

```js
  "Velkommen til {app}!": "Welcome to {app}!",
  "Øv på å kjøre analyser i microdata.no-stil. Inneholder ikke ekte tall; et hobbyprosjekt, ikke laget av microdata.no.": "Practise running analyses in the microdata.no style. No real figures; a hobby project, not made by microdata.no.",
  "OpenStat er en motor for å stille spørsmål som kan besvares med kode og statistikk — og for å se og endre koden som gir svaret. Skriv i Python, R, DuckDB eller microdata-stil; kjør i nettleseren.": "OpenStat is an engine for asking questions that can be answered with code and statistics — and for seeing and revising the code behind the answer. Write in Python, R, DuckDB or microdata style; run in the browser.",
  "SafeStat gjør det samme, og kan i tillegg dele og gi tilgang til sensitive data: bare analyser som bruker et begrenset sett kommandoer slipper gjennom, slik at resultatene viser aggregater — aldri opplysninger om enkeltpersoner.": "SafeStat does the same, and can additionally distribute and grant access to sensitive data: only analyses using a restricted set of commands are permitted, so results show aggregates — never information about individuals.",
  "‹ Vis kode": "‹ Show code",
  "Kjøre scriptet fra {src}? Det kjører kode i nettleseren din.": "Run the script from {src}? It runs code in your browser.",
  "lenken": "the link",
  "Kunne ikke hente notebook-lenken: {msg}": "Could not fetch the notebook link: {msg}",
```

- [ ] **Step 4: Verify.** `python3 scripts/check_inline.py` → `OK`; `node --check js/i18n/en.js` → no output.

- [ ] **Step 5: Manual smoke.** Local serve, clear `microdata_welcome_dismissed`: bare `localhost` shows the **OpenStat/SafeStat general** welcome (per `M2PY_APP`), not the microdata one; opening an `#output=…` link shows **no** welcome.

- [ ] **Step 6: Commit**

```bash
git add index.html js/i18n/en.js
git commit -m "feat(notebook-links): repositioned welcome variants (micro/open/safe), none on output-only"
```

### Task 10: Wire prose transforms into the run paths

**Files:**
- Modify: `index.html` — register `notebook_prose` as a Pyodide module (follow the existing `spec_from_loader`/`exec(compile(...))` module-registration pattern used for `functions`/`protect`/`mockdata_*`); transform each **pyodide** segment's text through it, and each **r** segment through `NotebookLinks.rProsePrep`, before execution. The segment build is at `index.html:9446-9450`; the module-registration block is where the other `.py` sources are fetched and registered (search `spec_from_loader`).

**Interfaces:**
- Consumes: `notebook_prose.prep_python_prose` (in Pyodide), `NotebookLinks.rProsePrep`, `parseHybridScript` output `segments`.

- [ ] **Step 1: Fetch + register `notebook_prose.py`.** Where the app fetches `functions.py`/`protect.py` for Pyodide registration, add `notebook_prose.py` to the fetch list and register it the same way (a `spec_from_loader("notebook_prose", ...)` + `exec(compile(code, "notebook_prose.py", "exec"), module.__dict__)`). If a `registerPyModule(py, name, code)` helper exists, use it; otherwise copy the existing block for one more module.

- [ ] **Step 2: Transform pyodide + r segments before execution.** Immediately after `segments` is finalized (`index.html:9450`, after the empty-segment fallback), add:

```js
        // Notebook prose: top-level bare strings (python) and #' blocks (R)
        // become markdown embeds, interleaved with output in source order.
        for (var _si = 0; _si < segments.length; _si++) {
          var _seg = segments[_si];
          if (_seg.kind === 'pyodide' && _seg.text) {
            try {
              py.globals.set('_np_src', _seg.text);
              _seg.text = String(await py.runPythonAsync(
                'import notebook_prose as _np; _np.prep_python_prose(_np_src)'));
            } catch (e) { console.warn('prep_python_prose:', e); }
          } else if (_seg.kind === 'r' && _seg.text && window.NotebookLinks) {
            _seg.text = window.NotebookLinks.rProsePrep(_seg.text);
          }
        }
```

- [ ] **Step 3: Verify.** `python3 scripts/check_inline.py` → `OK`.

- [ ] **Step 4: Manual smoke (python).** Local serve, python mode, run:

```python
"""# Report

This is **prose**.
"""
print("value:", 6 * 7)
```

Expected: the output area shows a rendered heading "Report" and bold "prose", then `value: 42` below it (markdown before the print output).

- [ ] **Step 5: Manual smoke (R).** R mode, run:

```r
#' # R report
#' some **prose**
x <- 6 * 7
print(x)
```

Expected: rendered markdown then `42`.

- [ ] **Step 6: Regression gates.** Confirm nothing broke:

Run: `.venv/bin/python -m pytest tests/ -q --ignore=tests/test_polars_backend.py`
Expected: same pass count as baseline + Task 5's tests, only the 4 pre-existing polars/linearmodels failures.
Run: `.venv/bin/python manual_scripts/run_manual_scripts.py`
Expected: `OK: 17 | PARTIAL: 0 | CRASH: 0`.

- [ ] **Step 7: Audit shipped examples.** Grep for scripts that begin with a top-level bare string that would now render unexpectedly:

Run: `grep -rlE '^\s*(\x27\x27\x27|""")' web_examples manual_scripts 2>/dev/null`
For any hit, open it and confirm the leading string is intended as prose (fine) or convert it to a `#` comment. Note findings in the commit body.

- [ ] **Step 8: Commit**

```bash
git add index.html
git commit -m "feat(prose): interleave python/R prose as markdown in the run path"
```

---

## Phase 4 — Port to OpenStat

### Task 11: Port everything to OpenStat with `M2PY_APP='openstat'`

**Files (in `/Users/hom/Documents/GitHub/openstat`):**
- Copy: `js/notebook-links.js`, `notebook_prose.py`, `tests/js/notebook-links.test.js`, `tests/test_notebook_prose.py` from SafeStat (identical).
- Modify: `index.html` (apply Tasks 6, 8, 9, 10 edits), `js/github-storage.js` (Task 7), `js/i18n/en.js` (Task 9) — adapted to OpenStat's structure (re-locate by searching; OpenStat has the same `openFromFragment`, welcome module, mode registry, segment run path). Set `window.M2PY_APP = 'openstat'`.

**Interfaces:** identical to SafeStat; only `M2PY_APP` differs (drives autorun trust + welcome copy).

- [ ] **Step 1: Copy the shared files.**

```bash
S=/Users/hom/Documents/GitHub/safestat; O=/Users/hom/Documents/GitHub/openstat
cp "$S/js/notebook-links.js" "$O/js/notebook-links.js"
cp "$S/notebook_prose.py" "$O/notebook_prose.py"
mkdir -p "$O/tests/js"; cp "$S/tests/js/notebook-links.test.js" "$O/tests/js/notebook-links.test.js"
cp "$S/tests/test_notebook_prose.py" "$O/tests/test_notebook_prose.py"
```

- [ ] **Step 2: Apply the wiring edits to OpenStat** — repeat Tasks 6–10's `index.html`/`github-storage.js`/`en.js` edits, searching for the same anchors in OpenStat, with `window.M2PY_APP = 'openstat'`. OpenStat has no `he`/`safestat` modes; the mode registry differences don't affect these edits (all reference python/r/duckdb/microdata + the shared helpers).

- [ ] **Step 3: Run the pure-unit gates in OpenStat.**

Run: `node --test tests/js/notebook-links.test.js` → PASS.
Run: `.venv/bin/python -m pytest tests/test_notebook_prose.py -q` (or the shared venv) → PASS.

- [ ] **Step 4: Verify inline scripts + full regression.**

Run: `python3 scripts/check_inline.py` (from OpenStat) → `OK`; `node --check js/notebook-links.js js/github-storage.js js/i18n/en.js`.
Run: `.venv/bin/python -m pytest tests/ -q --ignore=tests/test_polars_backend.py` → only pre-existing polars/linearmodels failures.
Run: `.venv/bin/python manual_scripts/run_manual_scripts.py` → `OK: 17`.

- [ ] **Step 5: Manual smoke (OpenStat autorun difference).** Local serve OpenStat with no stored secret: an `#output=<raw .py>` link runs **without** a confirm (zero-click) and shows only output. Then set `localStorage.md_anthropic_key='x'` and reload the same link → it now shows the confirm (safety valve).

- [ ] **Step 6: Commit (OpenStat repo).**

```bash
git add js/notebook-links.js notebook_prose.py tests/js/notebook-links.test.js tests/test_notebook_prose.py index.html js/github-storage.js js/i18n/en.js
git commit -m "feat: notebook links (fragment autorun, prose rendering, hostname startup) ported from SafeStat"
```

---

## Post-plan operational steps (not tasks)

- **Engine sync:** in SafeStat, `.venv/bin/python sync_to_api.py --apply` to propagate `notebook_prose.py` to `microdata-api/server_code/` (the server can then run prose-transformed scripts too). Commit the API repo.
- **DNS/ops:** create the subdomains (`py.openstat.app`, `r.safestat.app`, `duck.…`, `micro.…`) in Netlify + DNS so `hostnameMode` has hosts to read. Until then the bare-domain python default applies.
- **sw.js precache:** add `js/notebook-links.js` to the precache list only if other `js/*.js` are precached (they currently are not — skip unless that changes).

## Self-review notes

- **Spec coverage:** Part 1 fragment loader → Tasks 2, 7; Part 2 output-only+autorun → Tasks 3-note, 8; Part 3 prose (python/R) → Tasks 4, 5, 10; Part 4 hostname+welcome → Tasks 1, 3, 6, 9. Raw-URL fallback → Task 2/7. main→master → Task 7. Per-app trust + OpenStat safety valve → Task 8. No-welcome-on-output → Task 9. Behavior-change audit → Task 10 Step 7. Port → Task 11.
- **Type consistency:** `classifyHash` returns `{action, kind, urls?, raw?}` (Task 2) consumed verbatim in Task 7; `autorunNeedsGate(app, hasSecret)` (Task 8) matches its call; `welcomeVariant` return literals (`'microdata'|'openstat_general'|'safestat_general'|null`) match the `bodies` map in Task 9; `prep_python_prose`/`rProsePrep` signatures match their call sites in Task 10.
- **Marker consistency:** every emitter uses the exact `__micro_transform_start_markdown__` / `__micro_transform_end__` pair from Global Constraints.
