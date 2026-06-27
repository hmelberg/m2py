# DuckDB Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `duckdb` editor mode where SQL runs against the app's in-memory datasets via the existing DuckDB-WASM worker, previewing query results and persisting `CREATE TABLE` outputs back as datasets.

**Architecture:** A new pure-Python module `duckdb_bridge.py` parses the SQL (statements, referenced tables, created tables, trailing SELECT) and is unit-tested with pytest. The `duckdb` mode is registered **inline** in `index.html`'s `modeRegistry` (like the R/Statx modes). At run time, an orchestrator `runDuckdbScript` drives a small stateful JS bridge `window.__duck` (registers datasets as DuckDB views from Parquet buffers, executes the SQL, returns results via the existing `__arrowToColumns`), renders a 400-row preview, materializes created tables into `micro_interpreter.datasets`, and refreshes the dataset sidebar. Six–nine SQL examples ship in the Examples menu.

**Tech Stack:** Python 3 (pandas, pyarrow) for the bridge module + pytest; vanilla JS in `index.html`; DuckDB-WASM (`@duckdb/duckdb-wasm@1.29.0`, already loaded); Pyodide.

**Design spec:** `docs/superpowers/specs/2026-06-28-duckdb-mode-design.md`

## Global Constraints

- **Pandas stays the source of truth.** DuckDB is an execution engine only; datasets live in `micro_interpreter.datasets` (`{name: DataFrame}`). No rewrite of `StatsEngine`/`MicroInterpreter`/`protect.py`.
- **`duckdb_bridge.py` must not import `duckdb`** (browser-only) and must not import `js` (Pyodide-only). It is pure Python + pandas/pyarrow so it runs under plain pytest. `duckdb` is NOT installed in the dev venv.
- **Engine = existing DuckDB-WASM worker.** Reuse `__ensureDuckDB()` and `__arrowToColumns` at `index.html:2806-2855`. Do not add the Python `duckdb` package to Pyodide.
- **Preview cap = 400 rows.** Norwegian UI strings, matching existing menu/status style.
- **Run from a local server** for manual checks (the app cannot `fetch` modules over `file://`): `python -m http.server 8000` from the repo root, open `http://localhost:8000/index.html`.
- **Commit on `dev`** (current branch). End commit messages with the Co-Authored-By trailer used in this repo.

---

### Task 1: Pure SQL-parsing helpers (`duckdb_bridge.py`)

**Files:**
- Create: `duckdb_bridge.py`
- Test: `tests/test_duckdb_bridge.py`

**Interfaces:**
- Produces:
  - `split_sql_statements(sql: str) -> list[str]` — top-level `;` split, respecting `'…'`/`"…"`, `-- …` and `/* … */`; returns non-empty stripped statements.
  - `extract_referenced_tables(statements: list[str], known: list[str]) -> list[str]` — known names appearing as identifier tokens anywhere in the SQL (case-insensitive), order = `known` order, deduped.
  - `extract_created_tables(statements: list[str]) -> list[str]` — targets of `CREATE [OR REPLACE] [TEMP|TEMPORARY] TABLE [IF NOT EXISTS] name`, order-preserving, deduped, unquoted.
  - `build_preview_select(statements: list[str]) -> str | None` — the last statement if it begins with `SELECT` or `WITH`, else `None`.
  - `df_to_parquet_bytes(df) -> bytes` — DataFrame → Parquet bytes (pyarrow engine).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_duckdb_bridge.py`:

```python
"""Unit tests for duckdb_bridge — the pure SQL-parsing + parquet helpers used by
the DuckDB editor mode. No duckdb / no js imports: runs under plain pytest.
See docs/superpowers/specs/2026-06-28-duckdb-mode-design.md.
"""
import io

import pandas as pd

from duckdb_bridge import (
    split_sql_statements,
    extract_referenced_tables,
    extract_created_tables,
    build_preview_select,
    df_to_parquet_bytes,
)


def test_split_basic():
    assert split_sql_statements("SELECT 1; SELECT 2") == ["SELECT 1", "SELECT 2"]


def test_split_trailing_semicolon_and_blanks():
    assert split_sql_statements("SELECT 1;\n\n SELECT 2;\n") == ["SELECT 1", "SELECT 2"]


def test_split_ignores_semicolon_in_string():
    assert split_sql_statements("SELECT ';' AS x; SELECT 2") == ["SELECT ';' AS x", "SELECT 2"]


def test_split_ignores_semicolon_in_line_comment():
    sql = "SELECT 1 -- ; not a split\n; SELECT 2"
    assert split_sql_statements(sql) == ["SELECT 1 -- ; not a split", "SELECT 2"]


def test_split_ignores_semicolon_in_block_comment():
    sql = "SELECT 1 /* a ; b */ ; SELECT 2"
    assert split_sql_statements(sql) == ["SELECT 1 /* a ; b */", "SELECT 2"]


def test_referenced_tables_token_match_case_insensitive():
    sql = "SELECT * FROM Person p JOIN jobb USING (fnr)"
    known = ["person", "jobb", "kjoretoy"]
    assert extract_referenced_tables([sql], known) == ["person", "jobb"]


def test_referenced_tables_word_boundary():
    # 'person_year' must not be matched by the shorter 'person'
    sql = "SELECT * FROM person_year"
    assert extract_referenced_tables([sql], ["person", "person_year"]) == ["person_year"]


def test_referenced_tables_ignores_names_inside_strings_and_comments():
    sql = "SELECT 'person' AS lbl /* jobb */ FROM kjoretoy -- person\n"
    assert extract_referenced_tables([sql], ["person", "jobb", "kjoretoy"]) == ["kjoretoy"]


def test_created_tables_plain():
    assert extract_created_tables(["CREATE TABLE foo AS SELECT 1"]) == ["foo"]


def test_created_tables_or_replace_temp_ifnotexists_quoted():
    stmts = [
        "CREATE OR REPLACE TABLE bar AS SELECT 1",
        'CREATE TEMP TABLE IF NOT EXISTS "baz" AS SELECT 2',
        "create temporary table Qux as select 3",
    ]
    assert extract_created_tables(stmts) == ["bar", "baz", "Qux"]


def test_created_tables_dedup_preserves_order():
    stmts = ["CREATE TABLE a AS SELECT 1", "CREATE OR REPLACE TABLE a AS SELECT 2"]
    assert extract_created_tables(stmts) == ["a"]


def test_preview_select_plain():
    assert build_preview_select(["CREATE TABLE a AS SELECT 1", "SELECT * FROM a"]) == "SELECT * FROM a"


def test_preview_with_cte():
    stmts = ["WITH t AS (SELECT 1 AS n) SELECT n FROM t"]
    assert build_preview_select(stmts) == stmts[0]


def test_preview_none_when_last_is_ddl():
    assert build_preview_select(["SELECT 1", "CREATE TABLE a AS SELECT 1"]) is None


def test_preview_none_when_empty():
    assert build_preview_select([]) is None


def test_parquet_roundtrip_preserves_dtypes_and_nulls():
    df = pd.DataFrame({
        "i": pd.array([1, 2, None], dtype="Int64"),
        "f": [1.5, 2.5, 3.0],
        "s": ["a", None, "c"],
    })
    out = df_to_parquet_bytes(df)
    assert isinstance(out, (bytes, bytearray))
    back = pd.read_parquet(io.BytesIO(out))
    assert list(back.columns) == ["i", "f", "s"]
    assert back["s"].tolist() == ["a", None, "c"]
    assert back["f"].tolist() == [1.5, 2.5, 3.0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_duckdb_bridge.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'duckdb_bridge'`.

- [ ] **Step 3: Implement `duckdb_bridge.py`**

Create `duckdb_bridge.py`:

```python
"""Pure, browser-independent helpers for the DuckDB editor mode.

These parse a SQL script so the run orchestration in index.html knows which
datasets to register as DuckDB views, which tables the script creates (to
materialize back into micro_interpreter.datasets), and which trailing SELECT to
preview. The actual DuckDB execution happens in the browser via window.__duck.

Constraints: no `duckdb` import (browser-only), no `js` import (Pyodide-only).
This module must run under plain pytest.
"""
import io
import re

__all__ = [
    "split_sql_statements",
    "extract_referenced_tables",
    "extract_created_tables",
    "build_preview_select",
    "df_to_parquet_bytes",
]


def split_sql_statements(sql):
    """Split a SQL script on top-level semicolons, ignoring those inside string
    literals ('…'/"…"), -- line comments and /* … */ block comments. Returns a
    list of non-empty, stripped statements (their own comments preserved)."""
    stmts, buf = [], []
    i, n = 0, len(sql)
    in_single = in_double = in_line = in_block = False
    while i < n:
        c = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if in_line:
            buf.append(c)
            if c == "\n":
                in_line = False
            i += 1
        elif in_block:
            buf.append(c)
            if c == "*" and nxt == "/":
                buf.append(nxt)
                i += 2
                in_block = False
            else:
                i += 1
        elif in_single:
            buf.append(c)
            if c == "'":
                in_single = False
            i += 1
        elif in_double:
            buf.append(c)
            if c == '"':
                in_double = False
            i += 1
        elif c == "-" and nxt == "-":
            in_line = True
            buf.append(c)
            i += 1
        elif c == "/" and nxt == "*":
            in_block = True
            buf.append(c)
            i += 1
        elif c == "'":
            in_single = True
            buf.append(c)
            i += 1
        elif c == '"':
            in_double = True
            buf.append(c)
            i += 1
        elif c == ";":
            s = "".join(buf).strip()
            if s:
                stmts.append(s)
            buf = []
            i += 1
        else:
            buf.append(c)
            i += 1
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


def _scrub(sql):
    """Return sql with -- and /* */ comments removed, single-quoted string
    contents replaced by a space, and double-quote characters dropped (so quoted
    identifiers survive as bare tokens). Used for identifier scanning."""
    out = []
    i, n = 0, len(sql)
    in_single = in_line = in_block = False
    while i < n:
        c = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if in_line:
            if c == "\n":
                in_line = False
                out.append(c)
            i += 1
        elif in_block:
            if c == "*" and nxt == "/":
                in_block = False
                i += 2
                out.append(" ")
            else:
                i += 1
        elif in_single:
            if c == "'":
                in_single = False
                out.append(" ")
            i += 1
        elif c == "-" and nxt == "-":
            in_line = True
            i += 2
        elif c == "/" and nxt == "*":
            in_block = True
            i += 2
        elif c == "'":
            in_single = True
            i += 1
        elif c == '"':
            i += 1  # drop the quote char, keep inner identifier text
        else:
            out.append(c)
            i += 1
    return "".join(out)


def extract_referenced_tables(statements, known):
    """Known dataset names that appear as identifier tokens anywhere in the SQL
    (case-insensitive). Order follows `known`; deduped."""
    scrubbed = _scrub(" ; ".join(statements))
    found = []
    for name in known:
        if name in found:
            continue
        if re.search(r"(?<![\w])" + re.escape(name) + r"(?![\w])", scrubbed, re.IGNORECASE):
            found.append(name)
    return found


_CREATE_RE = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)?\s+)?TABLE\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?\"?([A-Za-z_]\w*)\"?",
    re.IGNORECASE,
)


def extract_created_tables(statements):
    """Targets of CREATE [OR REPLACE] [TEMP] TABLE [IF NOT EXISTS] name.
    Order-preserving, deduped, unquoted."""
    names = []
    for stmt in statements:
        for m in _CREATE_RE.finditer(_scrub(stmt)):
            nm = m.group(1)
            if nm not in names:
                names.append(nm)
    return names


def build_preview_select(statements):
    """The last statement if it begins with SELECT or WITH (a previewable result
    set), else None."""
    if not statements:
        return None
    last = statements[-1]
    head = _scrub(last).lstrip().upper()
    if head.startswith("SELECT") or head.startswith("WITH"):
        return last
    return None


def df_to_parquet_bytes(df):
    """Serialize a DataFrame to Parquet bytes (pyarrow engine)."""
    buf = io.BytesIO()
    df.to_parquet(buf, engine="pyarrow", index=False)
    return buf.getvalue()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_duckdb_bridge.py -q`
Expected: PASS (all tests green).

- [ ] **Step 5: Confirm no regressions in the suite**

Run: `.venv/bin/python -m pytest -q`
Expected: no NEW failures vs. baseline (the repo baseline has ~6 PARTIALs/known items; `test_duckdb_bridge.py` is all green).

- [ ] **Step 6: Commit**

```bash
git add duckdb_bridge.py tests/test_duckdb_bridge.py
git commit -m "feat(duckdb): pure SQL-parsing + parquet helpers for DuckDB mode

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: JS DuckDB bridge (`window.__duck`)

**Files:**
- Modify: `index.html` (immediately after `window.runStaticSchemas`, ~`index.html:2855`)

**Interfaces:**
- Produces (browser global): `window.__duck` with async methods `begin()`, `registerTable(name, parquetBytes)`, `exec(sql)`, `query(sql) -> {col: [values]}`, `end()`. Reuses `__ensureDuckDB()` and `__arrowToColumns` already defined just above.

- [ ] **Step 1: Add the bridge object**

In `index.html`, immediately after the `window.runStaticSchemas = async function …};` block (ends ~line 2855), insert:

```javascript
    // ── DuckDB editor mode: per-run connection over the same worker ──────────
    // Datasets are registered as views from Parquet buffers; results come back
    // through the existing __arrowToColumns helper. A fresh connection per run
    // keeps pandas (micro_interpreter.datasets) the single source of truth.
    window.__duck = {
      conn: null,
      async begin() {
        const db = await __ensureDuckDB();
        this.conn = await db.connect();
      },
      async registerTable(name, parquetBytes) {
        const db = await __ensureDuckDB();
        await db.registerFileBuffer(name + '.parquet', new Uint8Array(parquetBytes));
        await this.conn.query('CREATE OR REPLACE VIEW "' + name +
          '" AS SELECT * FROM read_parquet(\'' + name + '.parquet\')');
      },
      async exec(sql) { await this.conn.query(sql); },
      async query(sql) { return __arrowToColumns(await this.conn.query(sql)); },
      async end() {
        try { if (this.conn) await this.conn.close(); }
        finally { this.conn = null; }
      }
    };
```

- [ ] **Step 2: Manually verify the bridge in the browser console**

Start a server (`python -m http.server 8000`), open `http://localhost:8000/index.html`, open DevTools console, run:

```javascript
await __duck.begin();
await __duck.exec("CREATE TABLE t AS SELECT * FROM (VALUES (1,'a'),(2,'b')) AS v(id,name)");
const cols = await __duck.query("SELECT * FROM t ORDER BY id");
console.log(cols);            // expect { id:[1,2], name:['a','b'] }
await __duck.end();
console.log('conn after end:', __duck.conn);  // expect null
```
Expected: the logged object is `{ id: [1, 2], name: ['a', 'b'] }` and `conn after end` is `null`. No errors.

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat(duckdb): window.__duck bridge (per-run DuckDB-WASM connection)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: SQL highlighting + inline mode registration (with stub runner)

**Files:**
- Modify: `index.html` highlighter (`~2687`, `~2709`), HL configs (`~2657`), `modeRegistry` (`~3185`), `editorContent`/`editorBP` (`3463-3464`), mode dropdown (`~382`)

**Interfaces:**
- Consumes: `microdataHandleTab` (in scope), the highlight dispatch at `index.html:1697-1698`.
- Produces: `SQL_HL_CFG`; a registered `duckdb` mode whose `runSelf` calls `runDuckdbScript` (stubbed in this task, real in Task 4); a global `function runDuckdbScript(script, ctx)` so Task 4 only swaps its body.

- [ ] **Step 1: Extend the highlighter for `--` comments and case-insensitive keywords**

In `highlightCodeLine` (`index.html`), replace the comment line (line ~2687):

```javascript
        if (c === cfg.commentChar) { out += '<span class="md-out-comment">' + escHl(line.slice(i)) + '</span>'; return { html: out, openTriple: null }; }
```

with:

```javascript
        if (cfg.commentPrefix ? line.startsWith(cfg.commentPrefix, i) : c === cfg.commentChar) {
          out += '<span class="md-out-comment">' + escHl(line.slice(i)) + '</span>'; return { html: out, openTriple: null };
        }
```

And replace the keyword/function classification line (line ~2709):

```javascript
          var cls = cfg.kw.has(word) ? 'md-out-cmd' : (cfg.fn.has(word) || isCall) ? 'md-out-func' : null;
```

with:

```javascript
          var _kwKey = cfg.caseInsensitive ? word.toUpperCase() : word;
          var _fnKey = cfg.caseInsensitive ? word.toLowerCase() : word;
          var cls = cfg.kw.has(_kwKey) ? 'md-out-cmd' : (cfg.fn.has(_fnKey) || isCall) ? 'md-out-func' : null;
```

- [ ] **Step 2: Add the SQL highlight config**

After the `STATA_HL_CFG` definition (`index.html:2657`), add:

```javascript
    const SQL_HL_KW = new Set(['SELECT','FROM','WHERE','GROUP','BY','ORDER','HAVING','LIMIT','OFFSET',
      'JOIN','LEFT','RIGHT','INNER','OUTER','FULL','CROSS','NATURAL','ON','USING','AS','WITH',
      'CREATE','OR','REPLACE','TABLE','TEMP','TEMPORARY','VIEW','IF','NOT','EXISTS','DROP','ALTER',
      'INSERT','INTO','VALUES','UPDATE','SET','DELETE','DISTINCT','UNION','ALL','EXCEPT','INTERSECT',
      'CASE','WHEN','THEN','ELSE','END','AND','IN','IS','NULL','LIKE','ILIKE','BETWEEN','ASC','DESC',
      'OVER','PARTITION','WINDOW','QUALIFY','FILTER','PIVOT','UNPIVOT','SUMMARIZE','DESCRIBE','EXPLAIN',
      'CAST','TRY_CAST']);
    const SQL_HL_FN = new Set(['count','sum','avg','min','max','round','abs','coalesce','nullif','length',
      'lower','upper','trim','substr','substring','concat','replace','strftime','date_trunc','date_part',
      'row_number','rank','dense_rank','ntile','lag','lead','first_value','last_value',
      'median','quantile','mode','stddev','stddev_pop','var_pop','variance','corr','regr_slope',
      'greatest','least','floor','ceil','exp','ln','log','sqrt','pow','regexp_matches','regexp_replace']);
    const SQL_HL_CFG = { commentChar: '#', commentPrefix: '--', triple: false, caseInsensitive: true,
      identStart: /[A-Za-z_]/, identPart: /[A-Za-z0-9_]/, kw: SQL_HL_KW, fn: SQL_HL_FN };
```

- [ ] **Step 3: Add the stub orchestrator (replaced in Task 4)**

Immediately before `function runStatxScript` (search for `function runStatxScript` in `index.html`, ~line 6842), add:

```javascript
    // ── DuckDB mode orchestration (real implementation lands in Task 4) ──
    async function runDuckdbScript(script, ctx) {
      const py = (ctx && ctx.py) || await loadPyodideAndM2py();
      renderOutput('DuckDB-modus lastet (stub).', false, false);
      setStatus(rightStatus, '');
    }
```

- [ ] **Step 4: Register the mode inline**

In `modeRegistry`, after the `statx: { … }` entry (ends `index.html:3184`), add a `duckdb` entry:

```javascript
      duckdb: { id: 'duckdb', label: 'DuckDB', hlConfig: SQL_HL_CFG, handleTab: microdataHandleTab,
        translate: { showsButton: false },
        runSelf: async function (script, ctx) { await runDuckdbScript(script, ctx); } },
```

- [ ] **Step 5: Give the mode an editor-content slot**

Change `index.html:3463-3464` from:

```javascript
    const editorContent   = { microdata: '', python: '', r: '', statx: '', jamovi: '' };
    const editorBP        = { microdata: new Set(), python: new Set(), r: new Set(), statx: new Set(), jamovi: new Set() };
```

to:

```javascript
    const editorContent   = { microdata: '', python: '', r: '', statx: '', jamovi: '', duckdb: '' };
    const editorBP        = { microdata: new Set(), python: new Set(), r: new Set(), statx: new Set(), jamovi: new Set(), duckdb: new Set() };
```

- [ ] **Step 6: Add the dropdown menu entry**

In the mode menu (`index.html:377-383`), after the `statx` button add:

```html
          <button type="button" data-mode="duckdb">DuckDB</button>
```

- [ ] **Step 7: Manually verify mode switch, highlighting, and stub run**

Reload `http://localhost:8000/index.html`. From the mode dropdown choose **DuckDB**. Confirm:
- The mode label reads `DuckDB`.
- Typing `-- comment\nSELECT id FROM person WHERE id > 10 -- x` highlights `SELECT/FROM/WHERE` as keywords and both `--` comments as comments (and lowercase `select` highlights too).
- Clicking Run renders `DuckDB-modus lastet (stub).` with no console errors.

- [ ] **Step 8: Commit**

```bash
git add index.html
git commit -m "feat(duckdb): SQL highlighting + inline mode registration (stub runner)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Run orchestration (`runDuckdbScript` real implementation)

**Files:**
- Modify: `index.html` — replace the Task 3 stub `runDuckdbScript`; add `__duckBridgeP`/`__ensureDuckBridge` and the `__DUCK_RUN_PY` constant alongside it.

**Interfaces:**
- Consumes: `duckdb_bridge.py` (Task 1), `window.__duck` (Task 2), `micro_interpreter.datasets`, `renderOutput`, `refreshDatasetSidebarFromPy`, `purgePlots`, `outputArea`, `rightStatus`, `suppressEmbedded`, `lastOutput`, `lastOutputMode` (all in the run-path IIFE scope), `loadPyodideAndM2py`.
- Produces: a working `runDuckdbScript(script, ctx)`.

- [ ] **Step 1: Replace the stub with the real orchestrator**

Replace the entire stub `async function runDuckdbScript(script, ctx) { … }` (added in Task 3) with the loader, the Python program constant, and the real function:

```javascript
    // ── DuckDB mode: lazy-register the pure Python bridge module once ──
    var __duckBridgeP = null;
    function __ensureDuckBridge(py) {
      if (__duckBridgeP) return __duckBridgeP;
      var base = window.location.href.replace(/[^/]+$/, '');
      __duckBridgeP = fetch(base + 'duckdb_bridge.py?v=' + (window.M2PY_VERSION || '1'))
        .then(function (r) { if (!r.ok) throw new Error('duckdb_bridge.py'); return r.text(); })
        .then(function (code) {
          return py.runPythonAsync(
            'import sys, importlib.util\n' +
            'def _reg_duckdb_bridge(src):\n' +
            '    spec = importlib.util.spec_from_loader("duckdb_bridge", loader=None)\n' +
            '    mod = importlib.util.module_from_spec(spec)\n' +
            '    sys.modules["duckdb_bridge"] = mod\n' +
            '    exec(compile(src, "duckdb_bridge.py", "exec"), mod.__dict__)\n' +
            '_reg_duckdb_bridge(' + JSON.stringify(code) + ')');
        })
        .catch(function (e) { __duckBridgeP = null; throw e; });
      return __duckBridgeP;
    }

    // Python program: parse SQL, register referenced datasets, run, preview the
    // trailing SELECT (cap 400), materialize CREATE TABLE results back into
    // micro_interpreter.datasets. Reads the global `_duck_sql`; returns the
    // output text. js.__duck.end() runs in finally so the connection never leaks.
    const __DUCK_RUN_PY = `
import pandas as _pd
import js as _js
import __main__ as _m
import duckdb_bridge as _db
from pyodide.ffi import to_js as _to_js

_mi = _m.micro_interpreter
_datasets = _mi.datasets
_sql = _duck_sql

_stmts = _db.split_sql_statements(_sql)
_known = list(_datasets.keys())
_refs = _db.extract_referenced_tables(_stmts, _known)
_created = _db.extract_created_tables(_stmts)
_preview = _db.build_preview_select(_stmts)
_out = []

async def _run_duck():
    await _js.__duck.begin()
    try:
        for _name in _refs:
            _buf = _db.df_to_parquet_bytes(_datasets[_name])
            await _js.__duck.registerTable(_name, _to_js(_buf))
        if _sql.strip():
            await _js.__duck.exec(_sql)
        if _preview:
            _cnt = (await _js.__duck.query("SELECT count(*) AS n FROM (" + _preview + ") _q")).to_py()
            _nlist = _cnt.get("n") or [0]
            _total = int(_nlist[0]) if _nlist else 0
            _cols = (await _js.__duck.query("SELECT * FROM (" + _preview + ") _q LIMIT 400")).to_py()
            _pv = _pd.DataFrame(_cols)
            _out.append(_pv.to_string(index=False) if len(_pv) else "(0 rader)")
            if _total > 400:
                _out.append(str(_total) + " rader \\u2014 viser de f\\u00f8rste 400. "
                            "Bruk CREATE TABLE navn AS \\u2026 for \\u00e5 lagre som datasett.")
        for _name in _created:
            _cc = (await _js.__duck.query('SELECT * FROM "' + _name + '"')).to_py()
            _df = _pd.DataFrame(_cc)
            _datasets[_name] = _df
            if not _preview:
                _out.append("Opprettet datasett " + _name + " (" + str(len(_df)) +
                            " rader \\u00d7 " + str(_df.shape[1]) + " kolonner)")
    finally:
        await _js.__duck.end()

await _run_duck()
"\\n\\n".join(_out)
`;

    async function runDuckdbScript(script, ctx) {
      const py = (ctx && ctx.py) || await loadPyodideAndM2py();
      setStatus(rightStatus, 'Laster DuckDB-bro\\u2026');
      await __ensureDuckBridge(py);
      try {
        var _needPa = await py.runPythonAsync('import importlib.util as _iu\\n_iu.find_spec("pyarrow") is None');
        if (_needPa) {
          setStatus(rightStatus, 'Installerer pyarrow\\u2026');
          await py.runPythonAsync('import micropip as _mp\\nawait _mp.install("pyarrow")');
        }
      } catch (e) { console.warn('pyarrow ensure:', e); }
      setStatus(rightStatus, 'Kj\\u00f8rer SQL\\u2026');
      py.globals.set('_duck_sql', script || '');
      var out;
      try {
        out = await py.runPythonAsync(__DUCK_RUN_PY);
      } catch (e) {
        var msg = (e && e.message) ? e.message : String(e);
        purgePlots(outputArea);
        outputArea.innerHTML = '';
        var pre = document.createElement('pre');
        pre.className = 'error';
        pre.textContent = 'DuckDB-feil:\\n' + msg;
        outputArea.appendChild(pre);
        setStatus(rightStatus, 'Kj\\u00f8ring feilet.', true);
        return;
      }
      lastOutput = String(out || '').trim();
      await refreshDatasetSidebarFromPy(py);
      lastOutputMode = 'run';
      var asHtml = document.querySelector('input[name="outputMode"]:checked').value === 'html';
      renderOutput(lastOutput, asHtml, suppressEmbedded.checked);
      setStatus(rightStatus, '');
    }
```

- [ ] **Step 2: Manually verify a bare SELECT preview**

Reload, switch to DuckDB mode, run:

```sql
SELECT * FROM person LIMIT 5;
```
Expected: a small text table of 5 rows in the output area; no errors. (First run may pause to install pyarrow — status shows "Installerer pyarrow…".)

- [ ] **Step 3: Manually verify the 400-row cap note**

Run (against a dataset with >400 rows; `person` in the default mock data, otherwise pick any large table):

```sql
SELECT * FROM person;
```
Expected: 400 rows shown, followed by a note `"<N> rader — viser de første 400. Bruk CREATE TABLE navn AS … for å lagre som datasett."`.

- [ ] **Step 4: Manually verify CREATE TABLE persists as a datafile**

Run:

```sql
CREATE OR REPLACE TABLE hoy_inntekt AS
SELECT * FROM person WHERE 1=1;
```
Expected: output shows `Opprettet datasett hoy_inntekt (… rader × … kolonner)` (not a data dump). Open the dataset overview/picker → `hoy_inntekt` appears and opens in the Tabulator viewer. Switch to microdata/Python mode and confirm `hoy_inntekt` is available there too.

- [ ] **Step 5: Manually verify multi-statement + error handling**

Multi-statement (intermediate table, then summary):

```sql
CREATE OR REPLACE TABLE tmp AS SELECT * FROM person;
SELECT count(*) AS n FROM tmp;
```
Expected: the trailing `SELECT` preview (`n = …`) renders; `tmp` appears in the picker.

Error:

```sql
SELECT * FROM nonexistent_xyz;
```
Expected: a red `DuckDB-feil:` block with DuckDB's message; the app stays responsive; a subsequent valid query still works (connection did not leak).

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "feat(duckdb): run orchestration — SQL exec, 400-row preview, persist tables

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: SQL examples in the Examples menu

**Files:**
- Create: `examples/sql01_select_basics.txt` … `examples/sql08_describe_summary.txt` (8 files)
- Modify: `index.html` examples dropdown (`~62`, after the statx section) and the example-load mode whitelist (`index.html:1903`)

**Interfaces:**
- Consumes: the per-mode examples mechanism (`#examplesDropdown`, `updateExamplesVisibility`, the loader at `index.html:1893-1927`).
- Produces: a `data-section-mode="duckdb"` examples section with 8 buttons; `duckdb` added to the loader's mode whitelist.

- [ ] **Step 1: Create the example files**

Create each file under `examples/`. Use the default mock tables (`person`, `person_year`, `jobb`); keep them runnable and short.

`examples/sql01_select_basics.txt`:
```sql
-- Grunnleggende: velg, filtrer, sorter, begrens
SELECT *
FROM person
WHERE alder >= 18
ORDER BY alder DESC
LIMIT 20;
```

`examples/sql02_aggregate_groupby.txt`:
```sql
-- Aggregering: grupper og tell/gjennomsnitt, filtrer grupper med HAVING
SELECT kjonn,
       count(*)      AS antall,
       avg(alder)    AS snitt_alder
FROM person
GROUP BY kjonn
HAVING count(*) > 0
ORDER BY antall DESC;
```

`examples/sql03_join.txt`:
```sql
-- Join: koble person mot jobb på felles nøkkel (fnr)
SELECT p.fnr, p.alder, j.*
FROM person p
JOIN jobb j USING (fnr)
LIMIT 50;
```

`examples/sql04_create_table.txt`:
```sql
-- Bygg et datasett: resultatet dukker opp i dataoversikten (skrives ikke ut)
CREATE OR REPLACE TABLE voksne AS
SELECT *
FROM person
WHERE alder >= 18;
```

`examples/sql05_cte_window.txt`:
```sql
-- CTE + vindusfunksjon: ranger innen gruppe
WITH ranked AS (
  SELECT fnr, kjonn, alder,
         row_number() OVER (PARTITION BY kjonn ORDER BY alder DESC) AS rn
  FROM person
)
SELECT *
FROM ranked
WHERE rn <= 3
ORDER BY kjonn, rn;
```

`examples/sql06_case_recode.txt`:
```sql
-- Omkoding med CASE WHEN: lag aldersgrupper
SELECT fnr, alder,
       CASE
         WHEN alder < 18 THEN 'barn'
         WHEN alder < 67 THEN 'voksen'
         ELSE 'pensjonist'
       END AS aldersgruppe
FROM person
LIMIT 50;
```

`examples/sql07_multi_statement.txt`:
```sql
-- Flere setninger: lag et mellomdatasett, så et oppsummeringsdatasett
CREATE OR REPLACE TABLE voksne AS
SELECT * FROM person WHERE alder >= 18;

CREATE OR REPLACE TABLE voksne_per_kjonn AS
SELECT kjonn, count(*) AS antall, avg(alder) AS snitt_alder
FROM voksne
GROUP BY kjonn;

SELECT * FROM voksne_per_kjonn ORDER BY antall DESC;
```

`examples/sql08_describe_summary.txt`:
```sql
-- Rask profilering: kvantiler og spredning per variabel (som en tabell)
SELECT 'alder' AS variabel,
       count(*)                AS n,
       min(alder)              AS minimum,
       quantile_cont(alder, 0.5) AS median,
       avg(alder)              AS snitt,
       max(alder)              AS maksimum,
       stddev(alder)           AS standardavvik
FROM person;
```

- [ ] **Step 2: Add the examples dropdown section**

In `index.html`, after the statx `examples-section` (closes ~line 62), add:

```html
            <div class="examples-section" data-section-mode="duckdb">
              <button type="button" data-example="sql01_select_basics.txt" data-mode="duckdb">SQL &mdash; grunnleggende SELECT</button>
              <button type="button" data-example="sql02_aggregate_groupby.txt" data-mode="duckdb">SQL &mdash; GROUP BY og aggregering</button>
              <button type="button" data-example="sql03_join.txt" data-mode="duckdb">SQL &mdash; JOIN</button>
              <button type="button" data-example="sql04_create_table.txt" data-mode="duckdb">SQL &mdash; CREATE TABLE (bygg datasett)</button>
              <button type="button" data-example="sql05_cte_window.txt" data-mode="duckdb">SQL &mdash; CTE + vindusfunksjon</button>
              <button type="button" data-example="sql06_case_recode.txt" data-mode="duckdb">SQL &mdash; CASE WHEN (omkoding)</button>
              <button type="button" data-example="sql07_multi_statement.txt" data-mode="duckdb">SQL &mdash; flere setninger</button>
              <button type="button" data-example="sql08_describe_summary.txt" data-mode="duckdb">SQL &mdash; profilering/oppsummering</button>
            </div>
```

- [ ] **Step 3: Add `duckdb` to the example-load mode whitelist**

In `index.html:1903`, change:

```javascript
            if (mode && (mode === 'microdata' || mode === 'python' || mode === 'r' || mode === 'statx')
```

to:

```javascript
            if (mode && (mode === 'microdata' || mode === 'python' || mode === 'r' || mode === 'statx' || mode === 'duckdb')
```

- [ ] **Step 4: Manually verify examples**

Reload `http://localhost:8000/index.html`. Switch to DuckDB mode, open the **Eksempler** menu — confirm only the DuckDB section shows (8 entries). Load each example: it switches to DuckDB mode (if not already), populates the editor, and runs clean:
- `sql01`–`sql03`, `sql05`, `sql06`, `sql08` → table previews.
- `sql04` → `voksne` appears in the dataset picker.
- `sql07` → `voksne` and `voksne_per_kjonn` appear; trailing SELECT previews.

(If a mock-data column name differs from those used here, adjust the example SQL to match the actual columns — verify with `SELECT * FROM person LIMIT 1`.)

- [ ] **Step 5: Commit**

```bash
git add examples/sql0*.txt index.html
git commit -m "feat(duckdb): ship 8 SQL examples in the Examples menu

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review (completed)

**Spec coverage:**
- Mode registration (inline) → Task 3. Engine = existing worker / `window.__duck` → Task 2. Result model (register views, 400-row preview, explicit persist) → Tasks 1+4. Text-only SQL + highlighting → Task 3. SQL parsing/referenced/created/preview → Task 1. Error handling (finally + error `<pre>`) → Tasks 2+4. Testing split (pytest pure helpers + manual browser) → Tasks 1–5. 6–9 examples → Task 5 (8 files). All spec sections map to a task.

**Placeholder scan:** No TBD/TODO. The Task 3 stub `runDuckdbScript` is intentional and fully replaced in Task 4 (called out explicitly), not a placeholder gap.

**Type consistency:** `window.__duck` methods (`begin/registerTable/exec/query/end`) are defined in Task 2 and called with the same names/signatures in Task 4's `__DUCK_RUN_PY`. `duckdb_bridge` function names match between Task 1's definitions and Task 4's usage (`split_sql_statements`, `extract_referenced_tables`, `extract_created_tables`, `build_preview_select`, `df_to_parquet_bytes`). `runDuckdbScript(script, ctx)` signature is identical in Task 3 (stub) and Task 4 (real). `SQL_HL_CFG` defined in Task 3 Step 2, referenced in the Task 3 Step 4 registry entry.

**Known follow-ups (out of scope, by design):** nicer HTML table rendering for previews (currently `to_string` text); microdata↔SQL translation; native-SQL privacy. All deferred per the spec.
