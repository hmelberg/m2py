# DuckDB Hybrid Segments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make DuckDB a first-class hybrid segment kind (`#duckdb`/`#duck`/`#sql`) so `#micro`/`#py` preambles work in DuckDB mode and `#duckdb` blocks work in microdata/Python modes, via one shared executor.

**Architecture:** Replace the bespoke `runDuckdbScript`/`__DUCK_RUN_PY` path with a shared Python `_run_duck_sql(sql)` defined in the interpreter core. The normal hybrid segment loop runs DuckDB segments through it; DuckDB mode becomes `runDefault:'duckdb'` so it rides the same loop. Output flows through the normal stdout→renderer path.

**Tech Stack:** Vanilla JS in `index.html`; Python in the Pyodide interpreter core; DuckDB-WASM worker (`window.__duck`); `duckdb_bridge.py` (unchanged).

**Spec:** `docs/superpowers/specs/2026-06-28-duckdb-hybrid-segments-design.md`

## Global Constraints

- **One DuckDB execution path.** All DuckDB SQL runs through the shared `_run_duck_sql(sql)`; the bespoke `runDuckdbScript`/`__DUCK_RUN_PY` are removed. Keep `window.__duck`, `__ensureDuckDB`, `__arrowToColumns`, `__decimalToNumber`, `__ensureDuckBridge`.
- **Markers:** `#duckdb`, `#duck`, `#sql` (also `//`/`##` spellings), matching the existing marker style.
- **Preserve all v1 behavior/fixes** inside `_run_duck_sql`: pyarrow `patch_pyarrow` shim, per-run catalog clean (in `__duck.begin`), exclude created names from view registration, Decimal/HUGEINT handling (in `__arrowToColumns`), 400-row preview, "Opprettet datasett …" confirmation, concise error message.
- **Behavior-preserving for non-DuckDB modes:** the new marker and loop branch must not change microdata/Python/R behavior when no `#duckdb` segment is present.
- **Norwegian UI strings**, matching existing copy. Use literal Unicode characters (—, ø, å, ×) in the Python source.
- **Run from a local server** for manual checks: `python3 -m http.server 8765` from the repo root, open `http://localhost:8765/index.html`. (Visible Run control is `#btnRunFooter`.)
- **R-host `#duckdb` is out of scope for this plan** (see Deferred section) — `runHybridR` uses a separate `_e_r` interpreter.
- **Commit on `dev`.** End commit messages with the Co-Authored-By trailer.

---

### Task 1: Unify DuckDB execution as a hybrid segment kind

**Files:**
- Modify: `index.html` — `matchHybridMarker` (~5596), `parseHybridScript` (~5605), `getInterpreterCorePython` core string (define `_run_duck_sql`, ~after 6347), the segment loop (~7600-7625), the run-setup before `runPythonAsync(runCode)` (~7576), `modeRegistry.duckdb` (~3284), and removal of `runDuckdbScript`+`__DUCK_RUN_PY` (~6965-7090).

**Interfaces:**
- Consumes: `window.__duck` (begin/registerTable/exec/query/end), `__ensureDuckBridge(py)`, `duckdb_bridge` (split_sql_statements/extract_referenced_tables/extract_created_tables/build_preview_select/df_to_parquet_bytes), the core globals `e` (= `micro_interpreter`), `_g`, `catalog`, `show`, `to_microdata`, `_apply_labels_to_globals`.
- Produces: Python `async def _run_duck_sql(_sql) -> str` (returns text to print; raises a concise message on SQL error); a `duckdb` segment kind handled by the shared loop; `modeRegistry.duckdb.runDefault === 'duckdb'`.

- [ ] **Step 1: Add the `duckdb` marker**

In `matchHybridMarker` (`index.html:5596`), after the `stata` line add:

```javascript
      if (/^(\/\/|##?)\s*(duckdb|duck|sql)\s*$/i.test(trimmed)) return 'duckdb';
```

- [ ] **Step 2: Teach `parseHybridScript` the `duckdb` default**

In `parseHybridScript` (`index.html:5607`), change the `mode` initializer to recognize `'duckdb'`:

```javascript
      var mode = defaultMode === 'pyodide' ? 'pyodide' : defaultMode === 'r' ? 'r' : defaultMode === 'stata' ? 'stata' : defaultMode === 'duckdb' ? 'duckdb' : 'microdata';
```

- [ ] **Step 3: Define the shared `_run_duck_sql` executor in the interpreter core**

In `getInterpreterCorePython`'s returned Python string, immediately after the `_exec_pyodide_block` definition (~`index.html:6347`+), insert this Python (it lives inside the JS backtick template — it contains no `$`, so no interpolation concerns):

```python
import js as _duck_js
import duckdb_bridge as _duck_db
from pyodide.ffi import to_js as _duck_to_js

# Pyodide shim: pandas' to_parquet lazily runs patch_pyarrow(), which calls
# pyarrow.unregister_extension_type('arrow.py_extension_type') and raises
# ArrowKeyError in the Pyodide pyarrow build. Make unregister lenient, then
# pre-import the module so df.to_parquet(engine='pyarrow') works.
import pyarrow as _duck_pa
if not getattr(_duck_pa, "_m2py_unreg_patched", False):
    _duck_oru = _duck_pa.unregister_extension_type
    def _duck_safe_unreg(name, _o=_duck_oru):
        try:
            return _o(name)
        except Exception:
            return None
    _duck_pa.unregister_extension_type = _duck_safe_unreg
    _duck_pa._m2py_unreg_patched = True
    try:
        import pandas.core.arrays.arrow.extension_types as _duck_pet
    except Exception:
        pass

def _duck_concise(_msg):
    for _l in str(_msg).split("\n"):
        if "Error:" in _l:
            return _l.strip()
    _parts = [p for p in str(_msg).strip().split("\n") if p.strip()]
    return _parts[-1] if _parts else str(_msg)

async def _run_duck_sql(_sql):
    _datasets = e.datasets
    _stmts = _duck_db.split_sql_statements(_sql)
    _known = list(_datasets.keys())
    _refs = _duck_db.extract_referenced_tables(_stmts, _known)
    _created = _duck_db.extract_created_tables(_stmts)
    _preview = _duck_db.build_preview_select(_stmts)
    # Created tables win over a same-named existing dataset: don't register the
    # old dataset as a view, or the CREATE TABLE collides with that view.
    _created_lower = {c.lower() for c in _created}
    _refs = [r for r in _refs if r.lower() not in _created_lower]
    _out = []
    try:
        await _duck_js.__duck.begin()
        try:
            for _name in _refs:
                _buf = _duck_db.df_to_parquet_bytes(_datasets[_name])
                await _duck_js.__duck.registerTable(_name, _duck_to_js(_buf))
            if _sql.strip():
                await _duck_js.__duck.exec(_sql)
            if _preview:
                _cnt = (await _duck_js.__duck.query("SELECT count(*) AS n FROM (" + _preview + ") _q")).to_py()
                _nlist = _cnt.get("n") or [0]
                _total = int(_nlist[0]) if _nlist else 0
                _cols = (await _duck_js.__duck.query("SELECT * FROM (" + _preview + ") _q LIMIT 400")).to_py()
                _pv = pd.DataFrame(_cols)
                _out.append(_pv.to_string(index=False) if len(_pv) else "(0 rader)")
                if _total > 400:
                    _out.append(str(_total) + " rader — viser de første 400. Bruk CREATE TABLE navn AS … for å lagre som datasett.")
            for _name in _created:
                _cc = (await _duck_js.__duck.query('SELECT * FROM "' + _name + '"')).to_py()
                _df = pd.DataFrame(_cc)
                _datasets[_name] = _df
                if not _preview:
                    _out.append("Opprettet datasett " + _name + " (" + str(len(_df)) + " rader × " + str(_df.shape[1]) + " kolonner)")
        finally:
            await _duck_js.__duck.end()
    except Exception as _ex:
        raise RuntimeError("DuckDB: " + _duck_concise(_ex))
    return "\n\n".join(_out)
```

(`pd` and `e` are already defined in the core; `_run_duck_sql` reuses them.)

- [ ] **Step 4: Handle the `duckdb` segment in the shared loop**

In the segment loop (`index.html:7616`, after the `elif _k == "pyodide":` block), add:

```python
    elif _k == "duckdb":
        e.sync_datasets_to_globals(_g)
        print(await _run_duck_sql(_st))
        e.sync_datasets_to_globals(_g)
        _apply_labels_to_globals(_g, catalog)
        _g["show"] = show
        _g["to_microdata"] = to_microdata
```

- [ ] **Step 5: Ensure the bridge + pyarrow when any segment is `duckdb`**

In the main run function, right after `let segments = parseHybridScript(effectiveScript, runDefault);` and the empty-segments fallback (`index.html:7576-7580`), add:

```javascript
        if (segments.some(function (s) { return s.kind === 'duckdb'; })) {
          setStatus(rightStatus, 'Laster DuckDB-bro…');
          await __ensureDuckBridge(py);
          try {
            var _needPa = await py.runPythonAsync('import importlib.util as _iu\n_iu.find_spec("pyarrow") is None');
            if (_needPa) {
              setStatus(rightStatus, 'Installerer pyarrow…');
              await py.runPythonAsync('import micropip as _mp\nawait _mp.install("pyarrow")');
            }
          } catch (e) { console.warn('pyarrow ensure:', e); }
        }
```

- [ ] **Step 6: Switch DuckDB mode to `runDefault` (drop `runSelf`)**

Replace the `modeRegistry.duckdb` entry (`index.html:3284`) with:

```javascript
      duckdb: { id: 'duckdb', label: 'DuckDB', hlConfig: SQL_HL_CFG, handleTab: microdataHandleTab,
        translate: { showsButton: false }, runDefault: 'duckdb' },
```

- [ ] **Step 7: Remove the bespoke path**

Delete `const __DUCK_RUN_PY = \`…\`;` (`index.html:6969-7042`) and the entire `async function runDuckdbScript(script, ctx) { … }` (`index.html:7044`-end of that function). Keep `var __duckBridgeP` + `function __ensureDuckBridge(py)` (still used by Step 5). Confirm nothing else references `runDuckdbScript` or `__DUCK_RUN_PY`: `grep -n "runDuckdbScript\|__DUCK_RUN_PY" index.html` returns no matches.

- [ ] **Step 8: Manual verification (browser)**

Start `python3 -m http.server 8765`; open `http://localhost:8765/index.html`. (To script checks, set `#scriptInput.value`, dispatch an `input` event, click `#btnRunFooter`, read `#outputArea.innerText`.)

1. **Regression — DuckDB-only** (DuckDB mode):
   ```sql
   CREATE OR REPLACE TABLE p AS SELECT * FROM (VALUES (1,'a',10),(2,'b',20)) AS t(id,k,v);
   SELECT k, sum(v) AS s FROM p GROUP BY k ORDER BY k;
   ```
   Expect a 2-row table with `s` = 10 and 20 (confirms the moved executor + Decimal sum still work). No error.
2. **`#py` preamble in DuckDB mode:**
   ```
   #py
   import pandas as pd
   folk = pd.DataFrame({"fnr":[1,2,3],"inntekt":[450000,620000,810000]})
   to_microdata(folk, "folk")
   #duckdb
   SELECT count(*) AS n, round(avg(inntekt)) AS snitt FROM folk;
   ```
   Expect `n=3, snitt=626667`. No error.
3. **`#duckdb` block in Python mode** (switch to Python mode):
   ```
   import pandas as pd
   folk = pd.DataFrame({"fnr":[1,2,3,4],"kjonn":["M","K","M","K"],"inntekt":[450000,620000,810000,530000]})
   to_microdata(folk, "folk")
   #duckdb
   CREATE OR REPLACE TABLE oppsum AS SELECT kjonn, count(*) AS antall FROM folk GROUP BY kjonn;
   #py
   print(oppsum.to_string(index=False))
   ```
   Expect the SQL has no error, `oppsum` appears in the sidebar, and the trailing `#py` prints the `oppsum` DataFrame (proves the new table is synced back to globals).
4. **SQL error in a `#duckdb` segment** (DuckDB mode): `SELECT * FROM nope;` → output shows `ERROR:` / `DuckDB: Catalog Error: …` concisely; app recovers on a subsequent valid run.

- [ ] **Step 9: Confirm no Python-suite regressions**

Run: `.venv/bin/python -m pytest -q`
Expected: 264 passed, 1 xfailed (unchanged — no Python files modified).

- [ ] **Step 10: Commit**

```bash
git add index.html
git commit -m "feat(duckdb): unify DuckDB as a hybrid segment kind (#duckdb/#duck/#sql)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Hybrid examples in the Examples menu

**Files:**
- Create: `examples/sql09_micro_then_sql.txt`, `examples/sql10_py_then_sql.txt`, `examples/py05_duckdb_block.txt`
- Modify: `index.html` — DuckDB examples section (~`index.html:63`) and Python examples section (~`index.html:39-44`).

**Interfaces:**
- Consumes: the hybrid segment support from Task 1; the example loader (whitelist already includes `duckdb` and `python`); `to_microdata(df, name)` core helper.

- [ ] **Step 1: Create the example files**

`examples/sql09_micro_then_sql.txt`:
```sql
-- Hybrid: bygg et datasett med microdata-import, så bruk DuckDB til å lage et mindre.
-- (DuckDB/SQL kommenterer med --, ikke #. #micro/#duckdb er blokk-markører.)
#micro
require no.ssb.fdb:54 as fd
create-dataset folk
import fd/BEFOLKNING_KJOENN as kjonn
import fd/INNTEKT_WLONN 2022-01-01 as inntekt

#duckdb
CREATE OR REPLACE TABLE hoytlonnede AS
SELECT * FROM folk WHERE inntekt > 600000;

SELECT count(*) AS antall, round(avg(inntekt)) AS snitt_inntekt
FROM hoytlonnede;
```

`examples/sql10_py_then_sql.txt`:
```python
# Hybrid: bygg en DataFrame i Python, så lag et mindre datasett med DuckDB.
#py
import pandas as pd
folk = pd.DataFrame({
    "fnr":    [1, 2, 3, 4, 5, 6],
    "kjonn":  ["Mann","Kvinne","Mann","Kvinne","Mann","Kvinne"],
    "inntekt":[450000, 620000, 810000, 530000, 210000, 690000],
})
to_microdata(folk, "folk")

#duckdb
CREATE OR REPLACE TABLE hoytlonnede AS
SELECT * FROM folk WHERE inntekt > 600000;

SELECT kjonn, count(*) AS antall, round(avg(inntekt)) AS snitt
FROM hoytlonnede
GROUP BY kjonn
ORDER BY snitt DESC;
```

`examples/py05_duckdb_block.txt`:
```python
# Python + DuckDB: bygg data i pandas, kjør SQL med #duckdb, fortsett i pandas.
import pandas as pd
folk = pd.DataFrame({
    "fnr":    [1, 2, 3, 4, 5, 6],
    "kjonn":  ["Mann","Kvinne","Mann","Kvinne","Mann","Kvinne"],
    "inntekt":[450000, 620000, 810000, 530000, 210000, 690000],
})
to_microdata(folk, "folk")

#duckdb
CREATE OR REPLACE TABLE oppsummering AS
SELECT kjonn, count(*) AS antall, round(avg(inntekt)) AS snitt
FROM folk
GROUP BY kjonn;

#py
print(oppsummering.to_string(index=False))
```

- [ ] **Step 2: Add the two DuckDB examples to the DuckDB menu section**

In `index.html`, inside the `data-section-mode="duckdb"` section (after the `sql08` button, ~`index.html:71`), add:

```html
              <button type="button" data-example="sql09_micro_then_sql.txt" data-mode="duckdb">SQL &mdash; #micro &rarr; DuckDB (hybrid)</button>
              <button type="button" data-example="sql10_py_then_sql.txt" data-mode="duckdb">SQL &mdash; #py &rarr; DuckDB (hybrid)</button>
```

- [ ] **Step 3: Add the Python-mode example to the Python menu section**

In the `data-section-mode="python"` section (after the `py04` button, ~`index.html:43`), add:

```html
              <button type="button" data-example="py05_duckdb_block.txt" data-mode="python">pandas + #duckdb (SQL-blokk)</button>
```

- [ ] **Step 4: Manual verification (browser)**

Reload. Confirm:
- DuckDB mode → Eksempler shows the two new hybrid entries; loading `sql10` runs clean (a 2-row `kjonn` summary: Mann 810000, Kvinne 655000) and `hoytlonnede` appears in the sidebar.
- Loading `sql09` runs clean (prints `antall` + `snitt_inntekt`); `folk` and `hoytlonnede` appear in the sidebar.
- Python mode → Eksempler shows `pandas + #duckdb`; loading `py05` runs clean: SQL builds `oppsummering`, and the trailing `#py` prints it.

- [ ] **Step 5: Commit**

```bash
git add examples/sql09_micro_then_sql.txt examples/sql10_py_then_sql.txt examples/py05_duckdb_block.txt index.html
git commit -m "feat(duckdb): hybrid examples (#micro/#py -> #duckdb; #duckdb in Python)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Deferred (not in this plan): R-host `#duckdb`

`runHybridR` (`index.html:6776`) builds microdata in a **separate** interpreter
(`_e_r = MicroInterpreter()`) and ships data to webR via base64-CSV — it does not
populate the main `e.datasets` that `_run_duck_sql` reads. Supporting `#duckdb`
inside R mode therefore needs extra plumbing (route R's micro setup through the
main interpreter, or adapt `_run_duck_sql` to accept a target interpreter). It is
the least-common combination, so it is deferred to a small follow-up rather than
bundled here. The spec's R-host item should move to a later iteration.

## Self-Review (completed)

**Spec coverage:** Marker `#duckdb`/`#duck`/`#sql` → Task 1 Step 1. `#micro`/`#py`
preambles in DuckDB mode → Task 1 (Steps 2,4,6) + verified Step 8.2. `#duckdb` in
Python/microdata → Task 1 Steps 4-5 + Step 8.3. Shared executor → Step 3. Output
via stdout → Step 4. Bridge/pyarrow ensure for any host → Step 5. v1 fixes
preserved → Step 3 (shim, created-name exclusion, preview, confirmation, concise
error) + `__arrowToColumns` (Decimal) + `__duck.begin` (catalog clean) untouched.
Examples → Task 2. R-host → explicitly deferred with rationale (spec deviation
noted).

**Placeholder scan:** none — all steps carry concrete code/commands.

**Type consistency:** `_run_duck_sql(_sql)` defined in Step 3 is called in Step 4
and the bridge-ensure references `__ensureDuckBridge` (kept in Step 7). Marker
string `'duckdb'` is consistent across `matchHybridMarker`, `parseHybridScript`,
the loop branch, and `runDefault`.
