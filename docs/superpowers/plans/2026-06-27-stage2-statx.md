# Stage 2 — statx mode (pdexplorer) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 4th editor mode `statx` that runs Stata-style scripts in the browser via pdexplorer on Pyodide, operating on `#micro`-created datasets with a `use NAME` current-dataset model.

**Architecture:** A pytest-testable Python module `statx_runner.py` holds the `use NAME` parser + the run logic (`pdexplorer.use(e.datasets[NAME])` + `do(inline=…)` per chunk, capturing stdout). `index.html` gets a lazy `loadPdexplorer` loader (validated recipe), a `statx` registry plugin with `runSelf`, a `#stata` segment marker, and a minimal Stata highlighter.

**Tech Stack:** Pyodide (Python 3.13, bundled pandas 2.3.3 / statsmodels 0.14.4), pdexplorer 0.0.40 (pure-Python wheel), micropip; static no-build front end; pytest for the Python module.

## Global Constraints

- **Validated loading recipe (do not deviate):** `micropip.install('pdexplorer', deps=False)`; rely on Pyodide's bundled pandas/statsmodels (do NOT install pdexplorer's pinned versions); `micropip.install(['rich','click','requests'])`; stub `pywintypes`, `xlwings`, `pynput` via `MagicMock` in `sys.modules` BEFORE `import pdexplorer`; run via `pdexplorer.do(inline=<str>)`.
- **Engine bridge:** the microdata engine instance is `e`; datasets are `e.datasets` (dict `name -> pandas.DataFrame`); active dataset name is `e.active_name`.
- **No-build, inline JS** in `index.html`; Python logic in `statx_runner.py` (loaded into Pyodide like `m2py.py`). No `type="module"`.
- **Mode id `statx`, label `Statx`.** No translate button in statx v1 (`translate: { showsButton: false }`).
- statx uses the registry `runSelf` path (does NOT go through the microdata segment pipeline).
- **Not service-worker precached** beyond adding `statx_runner.py` to the existing local stale-while-revalidate set; pdexplorer is fetched from PyPI at first use (offline caveat — document in help).
- v1: fresh dataset reload on each `use`; no write-back to the engine; text output only.
- Front-end verification = pytest (for `statx_runner.py`) + manual/in-browser checks.

### Local verification

```bash
cd /Users/hom/Documents/GitHub/m2py
.venv/bin/python -m pytest tests/test_statx_runner.py -v   # Python module
python3 -m http.server 8000                                # http://localhost:8000/ for browser checks
```

---

### Task 1: `parse_statx_chunks` — the `use NAME` splitter (TDD)

**Files:**
- Create: `statx_runner.py`
- Create: `tests/test_statx_runner.py`

**Interfaces:**
- Produces: `parse_statx_chunks(script: str, default_name: str | None) -> list[tuple[str | None, str]]` — splits a statx script into `(dataset_name, commands)` chunks at each `use NAME` line. Leading commands before any `use` get `default_name`. `use NAME` lines are consumed (not included in any chunk's commands). `NAME` is the first whitespace-token after `use` (a trailing `, clear`/options are ignored).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_statx_runner.py
from statx_runner import parse_statx_chunks

def test_no_use_returns_single_chunk_with_default():
    assert parse_statx_chunks("summarize x\nregress y x", "folk") == [("folk", "summarize x\nregress y x")]

def test_leading_use_sets_name():
    assert parse_statx_chunks("use folk\nsummarize x", None) == [("folk", "summarize x")]

def test_switch_between_datasets():
    out = parse_statx_chunks("summarize x\nuse hus\ntabulate y", "folk")
    assert out == [("folk", "summarize x"), ("hus", "tabulate y")]

def test_use_with_options_ignored():
    assert parse_statx_chunks("use folk, clear\nsummarize x", None) == [("folk", "summarize x")]

def test_empty_leading_chunk_dropped():
    assert parse_statx_chunks("use folk\nsummarize x", None) == [("folk", "summarize x")]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_statx_runner.py -v`
Expected: FAIL (ModuleNotFoundError: statx_runner / function not defined).

- [ ] **Step 3: Implement `parse_statx_chunks`**

```python
# statx_runner.py
import re

_USE_RE = re.compile(r"^\s*use\s+([^\s,]+)", re.IGNORECASE)

def parse_statx_chunks(script, default_name):
    """Split a statx script into (dataset_name, commands) chunks at `use NAME` lines.
    `use NAME` lines are consumed. Leading commands before any `use` use default_name.
    A chunk with only whitespace commands is dropped."""
    chunks = []
    cur_name = default_name
    cur_lines = []

    def flush():
        text = "\n".join(cur_lines).strip()
        if text:
            chunks.append((cur_name, text))

    for line in script.split("\n"):
        m = _USE_RE.match(line)
        if m:
            flush()
            cur_name = m.group(1)
            cur_lines = []
        else:
            cur_lines.append(line)
    flush()
    return chunks
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_statx_runner.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add statx_runner.py tests/test_statx_runner.py
git commit -m "feat(statx): use-NAME chunk parser for statx scripts (TDD)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `run_statx` — execute chunks via pdexplorer, capture output

**Files:**
- Modify: `statx_runner.py`
- Modify: `tests/test_statx_runner.py`

**Interfaces:**
- Consumes: `parse_statx_chunks` (Task 1); an engine-like object with `.datasets` (dict) and `.active_name`; `pdexplorer` (imported lazily inside the function so the module imports without pdexplorer present — important: tests run WITHOUT pdexplorer).
- Produces: `run_statx(e, script) -> str` — returns the concatenated captured stdout. For each chunk: if `name` not in `e.datasets`, append a Norwegian "ukjent datasett" message listing available names and skip; else `pdexplorer.use(e.datasets[name])` then capture `pdexplorer.do(inline=commands)`'s stdout.

- [ ] **Step 1: Write the failing tests** (using a fake engine + a fake pdexplorer injected via `sys.modules`, so no real pdexplorer needed)

```python
import sys, types
from statx_runner import run_statx

class _FakeEngine:
    def __init__(self, datasets, active):
        self.datasets = datasets
        self.active_name = active

def _install_fake_pdexplorer(calls):
    mod = types.ModuleType("pdexplorer")
    def use(df): calls.append(("use", id(df)))
    def do(inline=None, filename=None): print("DID:" + (inline or ""))
    mod.use = use; mod.do = do
    sys.modules["pdexplorer"] = mod

def test_unknown_dataset_message():
    e = _FakeEngine({"folk": object()}, "folk")
    _install_fake_pdexplorer([])
    out = run_statx(e, "use hus\nsummarize x")
    assert "hus" in out and "folk" in out  # names the missing + available

def test_runs_do_on_resolved_dataset():
    df = object()
    e = _FakeEngine({"folk": df}, "folk")
    calls = []; _install_fake_pdexplorer(calls)
    out = run_statx(e, "summarize x")            # no use -> active 'folk'
    assert ("use", id(df)) in calls
    assert "DID:summarize x" in out
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_statx_runner.py -v`
Expected: FAIL (run_statx not defined).

- [ ] **Step 3: Implement `run_statx`**

```python
# add to statx_runner.py
import io, sys

def run_statx(e, script):
    import pdexplorer  # lazy: only available in the browser Pyodide runtime
    chunks = parse_statx_chunks(script, getattr(e, "active_name", None))
    buf = io.StringIO()
    for name, commands in chunks:
        if not commands.strip():
            continue
        if name is None or name not in e.datasets:
            avail = ", ".join(e.datasets.keys()) or "(ingen)"
            buf.write("use: ukjent datasett '%s'. Tilgjengelige: %s\n" % (name, avail))
            continue
        pdexplorer.use(e.datasets[name])
        _old = sys.stdout
        sys.stdout = buf
        try:
            pdexplorer.do(inline=commands)
        finally:
            sys.stdout = _old
    return buf.getvalue()
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_statx_runner.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add statx_runner.py tests/test_statx_runner.py
git commit -m "feat(statx): run_statx executes chunks via pdexplorer, captures output

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `loadPdexplorer` JS loader (validated recipe) + load `statx_runner.py`

**Files:**
- Modify: `index.html` — add `loadPdexplorer`, `pdexplorerReady`/`pdexplorerLoading` flags (near `loadPy2m` ~line 6921 and the `webRReady`/`py2mReady` declarations ~3365–3366).
- Modify: `sw.js` — add `/statx_runner.py` to `LOCAL_SWR_SUFFIXES`.

**Interfaces:**
- Consumes: `loadPyodideAndM2py()` (returns the Pyodide instance `py`).
- Produces: `pdexplorerReady` (bool); `async function loadPdexplorer(py)` — idempotent; runs the recipe and loads `statx_runner.py` into the Pyodide module namespace (`import statx_runner`).

- [ ] **Step 1: Add the flag declarations.** Next to `let py2mReady = false;` add:

```js
    let pdexplorerReady = false, pdexplorerLoading = false;
```

- [ ] **Step 2: Implement `loadPdexplorer`** (place next to `loadPy2m`):

```js
    async function loadPdexplorer(py) {
      if (pdexplorerReady) return;
      pdexplorerLoading = true;
      try {
        const base = window.location.href.replace(/[^/]+$/, '');
        // 1) stub the one desktop-only blocker BEFORE any pdexplorer import
        // 2) install pdexplorer without its pinned deps; use Pyodide's bundled pandas/statsmodels
        // 3) install its pure-python import deps
        await py.runPythonAsync(
          'import sys, micropip\n' +
          'from unittest.mock import MagicMock\n' +
          'for _m in ("pywintypes","xlwings","pynput"):\n' +
          '    sys.modules.setdefault(_m, MagicMock())\n' +
          'await micropip.install("pdexplorer", deps=False)\n' +
          'await micropip.install(["rich","click","requests"])\n' +
          'import pdexplorer\n'
        );
        // load our runner module into Pyodide via the exec/compile pattern used for
        // functions.py (index.html ~6829) — NOT FS.writeFile.
        const src = await fetch(base + 'statx_runner.py?v=' + (window.M2PY_VERSION || '1')).then(r => r.text());
        await py.runPythonAsync(
          'import sys, importlib.util\n' +
          'src = ' + JSON.stringify(src) + '\n' +
          'spec = importlib.util.spec_from_loader("statx_runner", loader=None)\n' +
          'mod = importlib.util.module_from_spec(spec)\n' +
          'sys.modules["statx_runner"] = mod\n' +
          'exec(compile(src, "statx_runner.py", "exec"), mod.__dict__)\n'
        );
        pdexplorerReady = true;
      } finally {
        pdexplorerLoading = false;
      }
    }
```

- [ ] **Step 3: Add `statx_runner.py` to the SW local set.** In `sw.js`, add `'/statx_runner.py',` to the `LOCAL_SWR_SUFFIXES` array (alongside `/m2py.py`).

- [ ] **Step 4: Browser check** — in the Console after the app loads:

```js
const py = await loadPyodideAndM2py(); await loadPdexplorer(py);
await py.runPythonAsync('import statx_runner; statx_runner.parse_statx_chunks("use folk\\nsummarize x", None)');
```
Expected: resolves without error; `pdexplorerReady === true`; the parse call returns `[('folk','summarize x')]`.

- [ ] **Step 5: Commit**

```bash
git add index.html sw.js
git commit -m "feat(statx): loadPdexplorer lazy loader + statx_runner module load

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Register the `statx` plugin (dropdown, label, onActivate, translate-hidden)

**Files:**
- Modify: `index.html` — add `statx` entry to `modeRegistry`; add a `statx` option to the mode dropdown menu (`editorModeMenu`); add a `STATA_HL_CFG` placeholder reference (full highlighter in Task 6 — for now `hlConfig: null` so it uses plain text).

**Interfaces:**
- Consumes: `modeRegistry`, `currentMode()`, `loadPdexplorer`, `runStatxScript` (Task 5 — declare the plugin's `runSelf` to call it; if Task 5 is not yet done, `runSelf` may reference `runStatxScript` which is hoisted/defined there — order tasks so 5 lands before browser-running statx).

**Produces:** `modeRegistry.statx` with `{ id, label, handleTab, onActivate, runSelf, translate: { showsButton: false } }`.

- [ ] **Step 1: Add the dropdown option.** In the `editorModeMenu` markup (where the `data-mode="microdata|python|r"` buttons are), add:

```html
          <button type="button" data-mode="statx">Statx</button>
```

- [ ] **Step 2: Register the plugin.** Add to `modeRegistry` (keep the others unchanged):

```js
      statx: { id: 'statx', label: 'Statx',
        hlConfig: null,
        handleTab: microdataHandleTab,
        onActivate: function () { if (!pdexplorerReady && !pdexplorerLoading) loadPyodideAndM2py().then(loadPdexplorer); },
        translate: { showsButton: false },
        runSelf: async function (script, ctx) { await runStatxScript(script, ctx); } },
```
(Using `microdataHandleTab` for now keeps Tab functional; a Stata-specific autocomplete is out of scope for v1.)

- [ ] **Step 3: Browser check** — the mode dropdown shows **Statx**; selecting it switches `activeEditorMode` to `statx` and triggers `loadPdexplorer` (watch Console/Network); the translate button stays hidden. No console errors. (Running a script comes in Task 5.)

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat(statx): register statx mode plugin + dropdown entry

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `runStatxScript` — wire runSelf to the engine + render output

**Files:**
- Modify: `index.html` — add `runStatxScript(script, ctx)`; recognize a `#stata` (alias `#statx`) segment so a `#micro` block runs first to build datasets.

**Interfaces:**
- Consumes: `loadPyodideAndM2py`, `loadPdexplorer`, the engine instance available in Pyodide (the same `e` the microdata run path builds), `renderOutput`, `setStatus`, `parseHybridScript`.
- Produces: `async function runStatxScript(script, ctx)` — ensures pdexplorer loaded; runs any leading `#micro` segment(s) through the engine to populate `e.datasets`; then calls `statx_runner.run_statx(e, <statx code>)`; renders the returned text via `renderOutput`.

- [ ] **Step 1: Implement `runStatxScript`** (mirror how the run handler builds `e` and runs microdata segments; read the existing run path / `getInterpreterCorePython` to reuse the engine setup, then):

```js
    async function runStatxScript(script, ctx) {
      const py = await loadPyodideAndM2py();
      await loadPdexplorer(py);
      // Split into #micro (build datasets via engine) and #stata (run via pdexplorer).
      const segments = parseHybridScript(script, 'stata');   // unmarked statx code -> kind 'stata'
      const microCode = segments.filter(s => s.kind === 'microdata').map(s => s.text).join('\n');
      const statxCode = segments.filter(s => s.kind === 'stata' || s.kind === 'statx').map(s => s.text).join('\n');
      // 1) run microdata segments to populate e.datasets (reuse the engine-core helper used by #python)
      if (microCode.trim()) {
        await py.runPythonAsync('import json\n_run_microdata_chunk(json.loads(' + JSON.stringify(JSON.stringify(microCode)) + '))');
      }
      // 2) run statx via the runner
      py.globals.set('_statx_src', statxCode);
      const out = await py.runPythonAsync(
        'import statx_runner\nstatx_runner.run_statx(e, _statx_src)'
      );
      renderOutput(String(out || ''), false, false);
    }
```
NOTE: the exact engine handle (`e`), the `_run_microdata_chunk` helper, and `parseHybridScript`'s marker handling must be confirmed against the current run path (lines ~7280–7345 and `_run_microdata_chunk` ~7529) and matched exactly. `parseHybridScript` must recognize `#stata`/`#statx` markers — extend its marker table (see `matchHybridMarker`/`normalizeBlockMarkers`) to map `stata`/`statx` → kind `stata`.

- [ ] **Step 2: Extend the hybrid marker recognition.** In `matchHybridMarker` / the marker table, add `stata` and `statx` as recognized block markers mapping to kind `stata` (mirror how `python`/`pyodide` and `r` are recognized). Confirm `parseHybridScript(src, 'stata')` then yields `stata` segments for unmarked code in statx mode.

- [ ] **Step 3: Browser check — end-to-end** on `http://localhost:8000/`, set mode to Statx, enter:

```
#micro
require no.ssb.fdb:54 as fd
create-dataset folk
import fd/BEFOLKNING_KJOENN as kjonn
import fd/INNTEKT_WLONN 2022-01-01 as inntekt

#stata
summarize inntekt
regress inntekt kjonn
tabulate kjonn
```
Run → Stata-style output (summary table, OLS results, tabulation) renders. Then test `use`: create a second dataset in `#micro` and a `#stata` block with `use folk` … `use <other>` …. And a bad name → "ukjent datasett" message. No console errors.

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat(statx): runStatxScript wires runSelf to engine datasets + pdexplorer

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Stata highlight + statx examples in the menu (mode-aware) + polish

**Files:**
- Create: `examples/st01_stata_basics.txt`, `examples/st02_stata_regresjon.txt`, `examples/st03_stata_generate.txt`, `examples/st04_stata_use.txt`.
- Modify: `index.html` — `STATA_HL_CFG` + set `modeRegistry.statx.hlConfig`; add a `data-section-mode="statx"` section to `examplesDropdown`; add `'statx'` to the example-click mode guard.

**Interfaces:**
- Consumes: the `hlConfig` shape used by `PY_HL_CFG`/`R_HL_CFG`; the examples-menu pattern (`updateExamplesVisibility` is generic — shows the `.examples-section` whose `data-section-mode === activeEditorMode`).

- [ ] **Step 1: Add a minimal Stata highlight config.** Next to `PY_HL_CFG`/`R_HL_CFG`:

```js
    const STATA_HL_KW = ['use','clear','summarize','sum','regress','reg','tabulate','tab','generate','gen','replace','egen','collapse','keep','drop','sort','by','bysort','merge','append','describe','list','browse','if','in','rename','label'];
    const STATA_HL_FN = ['mean','sd','min','max','count','total','r','e'];
    const STATA_HL_CFG = { commentChar: '*', triple: false, identStart: /[A-Za-z_]/, identPart: /[A-Za-z0-9_]/, kw: STATA_HL_KW, fn: STATA_HL_FN };
```
Then set `modeRegistry.statx.hlConfig = STATA_HL_CFG;` (change the `hlConfig: null` from Task 4).

- [ ] **Step 2: Create 4 statx example files** in `examples/` (each a `#micro` data block + a `#stata` block, with a leading comment):
  - `st01_stata_basics.txt` — `#micro` creates `folk` (kjonn, inntekt); `#stata`: `describe` / `summarize inntekt` / `tabulate kjonn`.
  - `st02_stata_regresjon.txt` — same `#micro`; `#stata`: `regress inntekt kjonn` (+ a comment on reading OLS output).
  - `st03_stata_generate.txt` — `#micro` with inntekt; `#stata`: `generate loginnt = log(inntekt)` / `egen meaninnt = mean(inntekt)` / `summarize loginnt meaninnt`.
  - `st04_stata_use.txt` — `#micro` creates TWO datasets (`folk` and e.g. `hus`); `#stata`: `use folk` … `summarize inntekt` … `use hus` … `tabulate <var>` (demonstrates `use NAME` switching).

- [ ] **Step 3: Add the statx examples-section to the menu.** In `examplesDropdown` (after the `data-section-mode="r"` section), add:

```html
            <div class="examples-section" data-section-mode="statx">
              <button type="button" data-example="st01_stata_basics.txt" data-mode="statx">Stata &mdash; beskrivende</button>
              <button type="button" data-example="st02_stata_regresjon.txt" data-mode="statx">Stata &mdash; regresjon</button>
              <button type="button" data-example="st03_stata_generate.txt" data-mode="statx">Stata &mdash; generate/egen</button>
              <button type="button" data-example="st04_stata_use.txt" data-mode="statx">Stata &mdash; use (flere datasett)</button>
            </div>
```
(`updateExamplesVisibility` already shows this section when `activeEditorMode === 'statx'` — no JS change needed for visibility.)

- [ ] **Step 4: Add `'statx'` to the example-click mode guard.** In the `button[data-example]` click handler (~line 1875), the condition `mode === 'microdata' || mode === 'python' || mode === 'r'` must also allow `'statx'` so clicking a statx example switches the editor into statx mode. Change it to include `|| mode === 'statx'`.

- [ ] **Step 5: Browser check** — in statx mode, Stata keywords are highlighted; open the hamburger → Examples menu while in statx mode → the 4 Stata examples are listed (and python/r ones are hidden); clicking one switches to statx mode and loads it; running it produces Stata output. Switching to python/r still shows their examples. No console errors.

- [ ] **Step 6: Engine sanity + commit**

```bash
.venv/bin/python -m pytest tests/test_statx_runner.py -v   # still green
git add index.html examples/st0*.txt
git commit -m "feat(statx): Stata highlight + 4 mode-aware statx examples in the menu

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Loading recipe (deps=False + bundled pandas + rich/click/requests + pywintypes stub + do(inline)) → Task 3 Global Constraints + Step 2. ✓
- `runSelf` registry plugin, label, dropdown, onActivate lazy-load, translate hidden → Task 4. ✓
- `#micro`+`#stata` hybrid + engine `e.datasets` bridge → Task 5 (Steps 1–2). ✓
- `use NAME` model (parse/split, resolve name→df, default=active, unknown-name error, fresh reload) → Tasks 1–2. ✓
- Output capture/render → Task 2 (`run_statx` captures stdout) + Task 5 (`renderOutput`). ✓
- Not precached beyond SWR for statx_runner.py → Task 3 Step 3. ✓
- Minimal highlight + example + help → Task 6. ✓
- Out-of-scope items (stata2m/translate, plots, write-back, frames) — none built. ✓

**Placeholder scan:** The Python steps carry full code + tests (TDD). The JS integration steps (Tasks 3 Step 2, 5 Steps 1–2) include concrete code but explicitly require matching the existing run-path mechanics (`_run_microdata_chunk`, engine handle `e`, `parseHybridScript` markers, the m2py.py load mechanism) — flagged with exact line anchors to read, not left vague. This is genuine integration uncertainty, not a placeholder; the implementer must read those sites and mirror them.

**Type/name consistency:** `parse_statx_chunks(script, default_name)`, `run_statx(e, script)`, `loadPdexplorer(py)`, `pdexplorerReady`, `runStatxScript(script, ctx)`, `STATA_HL_CFG`, mode id `statx`/label `Statx`, segment kind `stata` — consistent across tasks.

**Note for the executor:** Tasks 1–2 are pure-Python TDD (fast, deterministic). Tasks 3–6 are browser-integration: the engine handle `e`, `_run_microdata_chunk`, and `parseHybridScript` marker handling MUST be read from the live `index.html` run path before coding — the snippets here are the target shape, not a substitute for matching the existing mechanism.
