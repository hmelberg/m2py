# SafeStat output formatting + admin gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give SafeStat formatted analysis output (typed result tables in microdata-mode styling) with a hamburger toggle to fall back to raw stdout, stop always-printing the working dataframe, and gate the "Vis offline Python" menu item to admins only.

**Architecture:** A translator flag `print_results` suppresses the emitted `print(result_N)` so SafeStat can format the result *objects* instead of raw `repr`s. `runSafeStatScript` collects `result_N` objects (like it already collects `fig_N`), formats each by type into HTML carrying microdata's table CSS, and demotes the working `df` to a collapsible section when analysis output exists. A `safeStatFormat` toggle (`'formatted'` default | `'raw'`) in the hamburger menu picks formatted-objects vs raw-stdout. The offline-Python menu wrapper is shown only when `window.mdAuth.user.is_admin`, mirroring the existing `adminMenuSection` sync.

**Tech Stack:** Python 3.13 + pandas (translator, pytest-tested); browser JS + Pyodide (SafeStat UI, `node --check` + manual verification).

## Global Constraints

- **Microdata mode untouched.** All changes are translator-additive (a new defaulted flag) or inside SafeStat-only code (`runSafeStatScript`, a SafeStat menu toggle, the offline-menu gate). The emulator (`m2py.py`) is not touched. Full pytest suite stays green (baseline `529 passed, 1 xfailed`).
- **`print_results` defaults to `True`** so the offline/Anvil path (run the generated script standalone) keeps printing results. Only SafeStat's *formatted* mode passes `False`.
- **Two verification regimes.** Task 1 is **pytest-TDD**. Tasks 2–4 are browser — each ends with a `node --check` of the inline script (objective evidence; the snippet to run is in each task) and a **manual verification** step the human performs. Do not claim a browser task's behavior "passes".
- **Default output mode is Formatted.** Raw stdout is the opt-in.
- **Reuse microdata's table styling** for formatted tables (the `classes="..."` on `to_html`), so they look consistent — but the formatting is SafeStat-specific (it dispatches on the translator's result objects, not the emulator's output).
- Commit after each task. Branch off `dev`.

**Shared interface (Task 1 → Task 2):** `translate(script, backend="pandas", source_path=None, allow_emulated=False, manifest=None, print_results=True)`. With `print_results=False`, analysis steps emit `result_N = ops.…(…)` with **no** `print(result_N)`.

---

### Task 1: `print_results` flag in `translate()` (translator)

**Files:**
- Modify: `m2py_translate.py` — `_emit_analysis` (def at line 566; its final `return` at the line `return f"{res} = {call}\nprint({res})"`), the `translate()` signature, and the loop call to `_emit_analysis` (line 964).
- Test: `tests/test_safestat_print_flag.py` (new).

**Interfaces:**
- Produces: `translate(..., print_results=True)`. When `False`, emitted analysis lines omit `print(result_N)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_safestat_print_flag.py
import m2py_translate as t

SCRIPT = ("create-dataset p\nimport INNTEKT/WLONN as lonn\n"
          "summarize lonn\nregress lonn alder")


def test_default_prints_results():
    code = t.translate(SCRIPT, backend="pandas", source_path=None)
    assert "print(result_1)" in code and "print(result_2)" in code


def test_print_results_false_suppresses_print_but_keeps_result_vars():
    code = t.translate(SCRIPT, backend="pandas", source_path=None,
                       print_results=False)
    assert "print(result_" not in code          # no prints
    assert "result_1 = ops.summarize(" in code  # result objects still created
    assert "result_2 = ops.regress(" in code
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_safestat_print_flag.py -q`
Expected: FAIL — `translate() got an unexpected keyword argument 'print_results'`.

- [ ] **Step 3: Thread the flag**

In `m2py_translate.py`:

1. Change `_emit_analysis`'s signature to accept the flag:

```python
def _emit_analysis(instr, backend, idx, frame=None, print_results=True):
```

2. Change its final return (the line `return f"{res} = {call}\nprint({res})"`) to:

```python
    return f"{res} = {call}" + (f"\nprint({res})" if print_results else "")
```

3. Add `print_results=True` to the `translate()` signature (it currently ends `…, manifest=None):`):

```python
def translate(script, backend="pandas", source_path="df", allow_emulated=False,
              manifest=None, print_results=True):
```

4. Update the loop call at line 964 from `_emit_analysis(instr, backend, idx, frame)` to:

```python
            emitted = _emit_analysis(instr, backend, idx, frame, print_results)
```

(Leave the `run()`-helper call at line 1044 — `_emit_analysis(instr, "polars", 1)` — unchanged; it keeps the default.)

- [ ] **Step 4: Run the test + full suite**

Run: `python -m pytest tests/test_safestat_print_flag.py -q && python -m pytest -q`
Expected: new tests PASS; full suite `531 passed, 1 xfailed` (529 + 2 new).

- [ ] **Step 5: Commit**

```bash
git add m2py_translate.py tests/test_safestat_print_flag.py
git commit -m "feat(translate): print_results flag to suppress print(result_N)"
```

---

### Task 2: SafeStat formatted output + df-demotion (browser)

**Files:**
- Modify: `index.html` — `runSafeStatScript`.

**Interfaces:**
- Consumes: Task 1 (`print_results`), `safeStatFormat` (Task 3; assume the global exists — Task 3 declares it, but this task may run first, so **declare `var safeStatFormat = 'formatted';` here if it is not already declared**, and Task 3 reuses it).
- Produces: in formatted mode, SafeStat shows typed result tables (`result_N`) instead of raw stdout, and the working `df` collapses to a `<details>` when results/plots exist; raw mode keeps today's stdout behavior.

- [ ] **Step 1: Drive translate by format + collect results in Python**

In `runSafeStatScript`, ensure `var safeStatFormat = 'formatted';` exists at module scope (add it just above `var safeStatTarget` if absent). Then pass the print flag and collect results. In the Python block:

- set the print flag from JS before the block: `py.globals.set('_ss_raw', safeStatFormat === 'raw');`
- change the translate call to `_code = _mt.translate(_ss_src, backend="pandas", source_path=None, allow_emulated=True, print_results=_ss_raw)`
- after `_df = _ns.get("df")` and the `_figs` collection, add result collection:

```python
_results = []
for _k in sorted(_ns):
    if _k.startswith("result_"):
        _r = _ns[_k]
        try:
            if hasattr(_r, "to_html"):
                _results.append(_r.to_html(border=0, classes="output-table"))
            elif hasattr(_r, "summary"):
                _results.append("<pre>" + str(_r.summary()) + "</pre>")
            else:
                _results.append("<pre>" + str(_r) + "</pre>")
        except Exception:
            _results.append("<pre>" + str(_r)[:5000] + "</pre>")
```

and add `"results": _results` to the final `_json.dumps({...})`.

- [ ] **Step 2: Render formatted vs raw + demote the df**

In the JS rendering of `runSafeStatScript`, replace the body assembly so it honours the format and demotes `df`:

```js
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
        // working dataframe: inline when it IS the result (no analysis), else collapsible
        if (res.html) {
          bodyHtml += _hasAnalysis
            ? '<details style="margin-top:8px"><summary style="cursor:pointer;opacity:.7">Datasett (df, ' + (res.n||0) + ' rader)</summary>' + res.html + '</details>'
            : res.html;
        }
```

(Keep the existing plot-placeholder loop and the generated-code `<details>` exactly as they are, after this block.)

- [ ] **Step 3: node --check**

Run (must be rc 0 / clean):

```bash
python3 - <<'PYEOF'
import re, pathlib, subprocess, tempfile, os
html = pathlib.Path("index.html").read_text()
b = [x for x in re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', html, re.S) if 'runSafeStatScript' in x][0]
f=tempfile.NamedTemporaryFile('w',suffix='.js',delete=False); f.write(b); f.close()
r=subprocess.run(['node','--check',f.name],capture_output=True,text=True)
print("node --check:", r.returncode, r.stderr[-400:] if r.stderr else "(clean)")
os.unlink(f.name)
PYEOF
```

- [ ] **Step 4: Manual verification**

Reload, SafeStat mode, run `create-dataset p` + `import INNTEKT/WLONN as lonn` + `summarize lonn` + `regress lonn alder`. Expected (Formatted default): a styled summarize table + a regression summary; the working `df` is a collapsible "Datasett (df, N rader)" section, NOT a big table at the top. No raw duplicate of the result objects.

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat(safestat): formatted result tables + demote working df to collapsible"
```

---

### Task 3: Hamburger toggle Formatert/Rå (browser)

**Files:**
- Modify: `index.html` — a new menu button + handler near the existing `menuToggleOutputMode` (HTML line 119; handler near line 2265).

**Interfaces:**
- Consumes/produces: the `safeStatFormat` global (`'formatted'` default). The button flips it and is shown only in SafeStat mode.

- [ ] **Step 1: Add the menu button**

After the `menuToggleOutputMode` button (HTML line ~119), add:

```html
        <button type="button" id="menuToggleSafestatOutput" style="display:none">SafeStat-output: Formatert</button>
```

- [ ] **Step 2: Wire the toggle + label**

Near the `menuToggleOutputMode` click handler (~line 2265), add:

```js
      (function(){
        var b = document.getElementById('menuToggleSafestatOutput');
        if (!b) return;
        function lbl(){ b.textContent = 'SafeStat-output: ' + (safeStatFormat === 'raw' ? 'Rå' : 'Formatert'); }
        lbl();
        b.addEventListener('click', function(){
          safeStatFormat = (safeStatFormat === 'raw') ? 'formatted' : 'raw';
          lbl();
        });
        window.mdUpdateSafestatToggle = function(){
          b.style.display = (activeEditorMode === 'safestat') ? '' : 'none';
          lbl();
        };
      })();
```

- [ ] **Step 3: Show it only in SafeStat mode**

In `updateModeButtonsUi` (line ~3334), add at the end (before its closing brace):

```js
      if (window.mdUpdateSafestatToggle) window.mdUpdateSafestatToggle();
```

- [ ] **Step 4: node --check** (same snippet as Task 2 Step 3, but the relevant inline block is the one containing `menuToggleSafestatOutput` — adapt the filter to `'menuToggleSafestatOutput' in x or 'updateModeButtonsUi' in x` and check each).

- [ ] **Step 5: Manual verification**

Reload. The toggle appears in the hamburger menu ONLY when SafeStat mode is active, reads "SafeStat-output: Formatert" by default, flips to "Rå" on click; re-running shows raw stdout in Rå and formatted tables in Formatert.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "feat(safestat): hamburger toggle for formatted vs raw output (SafeStat-only)"
```

---

### Task 4: Admin-gate the offline-Python menu (browser)

**Files:**
- Modify: `index.html` — the offline-menu wrapper (HTML ~line 96) + `updateAdminMenuVisibility` (line ~1873); `js/ai-chat.js` — the admin sync (line ~1096).

**Interfaces:**
- Produces: the "Vis offline Python" menu wrapper is `display:none` unless `window.mdAuth.user.is_admin`.

- [ ] **Step 1: Give the wrapper an id + default-hide it**

The `menuOfflineBtn` (HTML ~line 96) sits in a `<div class="topbar-examples-wrap" style="position:relative">`. Add an id and default-hide:

```html
        <div class="topbar-examples-wrap" id="offlineMenuWrap" style="position:relative;display:none">
```

- [ ] **Step 2: Show it for admins in `updateAdminMenuVisibility`**

In `updateAdminMenuVisibility` (index.html ~line 1873), after the `adminSec` block, add:

```js
        const offlineWrap = document.getElementById('offlineMenuWrap');
        if (offlineWrap) {
          offlineWrap.style.display = (window.mdAuth && window.mdAuth.user && window.mdAuth.user.is_admin) ? '' : 'none';
        }
```

- [ ] **Step 3: Mirror in the ai-chat admin sync**

In `js/ai-chat.js` (~line 1096), after the `adminSec` block, add:

```js
        const offlineWrap = document.getElementById('offlineMenuWrap');
        if (offlineWrap) {
          offlineWrap.style.display = (user && user.is_admin) ? '' : 'none';
        }
```

- [ ] **Step 4: node --check** (run the Task 2 snippet but filter the block containing `updateAdminMenuVisibility`; also confirm `js/ai-chat.js` parses: `node --check js/ai-chat.js`).

- [ ] **Step 5: Manual verification**

Reload logged out (or as a non-admin): the "Vis offline Python" item is hidden. Log in as the admin (Hans Olav Melberg): the item appears. SafeStat mode and Kjør are unaffected (only the offline-translate menu item is gated).

- [ ] **Step 6: Commit**

```bash
git add index.html js/ai-chat.js
git commit -m "feat(ui): gate 'Vis offline Python' menu to admins (is_admin)"
```

---

### Task 5: SafeStat plots match microdata styling (browser)

**Files:**
- Modify: `index.html` — extract the figure-render block from `renderOutput` (the `p.embedType === 'figure'` branch, ~line 5491) into a shared helper; call it from both `renderOutput` and `runSafeStatScript`.

**Interfaces:**
- Produces: `function mdRenderPlotlyFigure(div, spec)` that applies microdata's themed `baseLayout` (size, theme bg/font/gridcolors, optional seaborn-style + colorway), the `{responsive, autosizable, staticPlot}` config, and the `plotly-container`(+`seaborn-style`) class, then `Plotly.newPlot`. Both microdata and SafeStat render through it, so plots look identical.

- [ ] **Step 1: Extract the helper (behavior-preserving for microdata)**

Add near `renderOutput` (top-level function scope):

```js
    function mdRenderPlotlyFigure(div, spec) {
      if (typeof Plotly === 'undefined') return;
      var staticEl = document.getElementById('plotStatic');
      var seabornEl = document.getElementById('plotSeaborn');
      var staticPlot = !!(staticEl && staticEl.checked);
      var seabornStyle = !!(seabornEl && seabornEl.checked);
      div.className = 'plotly-container' + (seabornStyle ? ' seaborn-style' : '');
      var data = spec.data || [];
      var styles = getComputedStyle(document.body);
      var bgCode = (styles.getPropertyValue('--bg-code') || '#faf8f5').trim();
      var textColor = (styles.getPropertyValue('--text') || '#1a1b26').trim();
      var borderColor = (styles.getPropertyValue('--border') || '#e4e2dd').trim();
      var baseLayout = {
        autosize: false, width: 480, height: 300,
        margin: { t: 40, r: 40, b: 50, l: 50 },
        paper_bgcolor: bgCode, plot_bgcolor: bgCode,
        font: { color: textColor, family: 'DejaVu Sans, Arial, sans-serif', size: 12 },
        xaxis: { gridcolor: borderColor, zerolinecolor: borderColor, linecolor: borderColor, tickfont: { color: textColor } },
        yaxis: { gridcolor: borderColor, zerolinecolor: borderColor, linecolor: borderColor, tickfont: { color: textColor } }
      };
      if (seabornStyle) {
        Object.assign(baseLayout, {
          template: 'plotly_white',
          colorway: ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        });
      }
      var layout = Object.assign(baseLayout, spec.layout || {});
      Plotly.newPlot(div, data, layout, { responsive: true, autosizable: true, staticPlot: staticPlot }).catch(function(){});
    }
```

- [ ] **Step 2: Use it in microdata's `renderOutput`**

In the `p.embedType === 'figure'` branch (~line 5491), replace the inline body (from `const data = spec.data || [];` through the `Plotly.newPlot(div, data, layout, config).catch(...)` line) with a single call — note `div` is already created and appended there:

```js
                mdRenderPlotlyFigure(div, spec);
```

Keep the `const spec = JSON.parse(p.payload);` and the `div` creation/`frag.appendChild(div)` exactly as they are (the helper sets `div.className`, which harmlessly re-sets it). Remove the now-duplicated `div.className = 'plotly-container' …` line above it to avoid setting it twice (optional but tidy).

- [ ] **Step 3: Use it in SafeStat's fig loop**

In `runSafeStatScript`, replace the bare `Plotly.newPlot(document.getElementById(_f.id), _spec.data, _spec.layout, {responsive:true});` with:

```js
            mdRenderPlotlyFigure(document.getElementById(_f.id), _spec);
```

- [ ] **Step 4: node --check** (run the Task 2 Step 3 snippet, but check the block containing `mdRenderPlotlyFigure` / `renderOutput` and the one containing `runSafeStatScript`).

- [ ] **Step 5: Manual verification**

Reload. Run a `histogram` in BOTH microdata mode and SafeStat mode (Formatted). The two plots should look the same — themed background, fonts, gridlines, size — and toggling the seaborn/static plot options affects both identically.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "feat(safestat): render plots via shared mdRenderPlotlyFigure (match microdata styling)"
```

---

## Notes for the implementer
- Only Task 1 is pytest-verifiable; keep the suite green. Tasks 2–5 report `node --check` results + the manual step; do not fabricate browser passes.
- `safeStatFormat` is declared once (Task 2 if absent, else Task 3) — do not double-declare.
- Task 5's extraction must be behavior-preserving for microdata-mode plots — same layout/config/class, just relocated into a shared helper.
- Search by quoted code, not line numbers, if they have drifted.
