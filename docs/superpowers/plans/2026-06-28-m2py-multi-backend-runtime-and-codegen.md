# m2py Multi-Backend: Runtime Library + pandas/polars Code Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **STATUS (2026-06-28):** Implemented on branch `feature/polars-offline-backend` as a **purely additive** path (no `m2py.py` surgery — the emulator-delegation refactor of Tasks 1-3 was deliberately deferred as internal-cleanup-only risk; instead the emulator is used as a correctness *oracle*). Delivered: `m2py_runtime/{pandas_ops,polars_ops,exprcompile}.py`, `m2py_translate.py` (both backends + `run()` helper), `tests/test_polars_backend.py` (cross-engine suite). Supported verbs now cover shaping, aggregation, merge, and analysis (summarize/tabulate/correlate/regress) — **99% (186/187)** of those verbs across the repo's real `manual_scripts/`+`examples/`. See `docs/polars-offline-backend.md`. The task-by-task TDD steps below are retained as the reference design; actual implementation followed the same shape with the emulator as the test oracle.

**Goal:** Lift the emulator's per-command logic into a pure, callable runtime library so the same tested code paths back (a) the in-browser pandas emulator, (b) a thin pandas *translator* that exports a standalone runnable script, and (c) an offline *polars* backend that emits a lazy/streaming script for large data outside the browser.

**Architecture:** The microdata `MicroParser` already turns each line into an instruction dict (`{command, args, options, condition}`) — that dict is the IR. We add a pure functional core `m2py_runtime` whose ops take `(frame, parsed-args) -> frame` with no logging, no `self`, no disclosure-control side effects. The emulator becomes a thin driver that calls those ops (proving equivalence against the existing `tests/test_equivalence.py`). A new `m2py_translate.translate(script, backend)` walks the IR and emits a script of thin op-calls — `backend="pandas"` against the pandas ops, `backend="polars"` against a parallel polars ops module that operates on `pl.LazyFrame`. This plan delivers a **vertical slice** (3 verbs: `generate`, `keep`, `collapse`) end-to-end across all three deliverables to validate the architecture before rolling out the remaining verbs (Phase 2).

**Tech Stack:** Python 3.11+, pandas, polars (offline only — NOT loaded in Pyodide), pytest. No new browser/Pyodide dependency: polars is a dev/offline dependency only.

**Local validation environment (confirmed 2026-06-28):** `/Users/hom/miniforge3/bin/python` = CPython 3.13, pandas 3.0.3, polars 1.42.0 (installed for this work). A real parity smoke test on 100k rows passed bit-for-bit across `generate`/`keep`/`merge`/`collapse`+stats (mean/median/std/count) with the streaming engine — so every task below is locally runnable and the cross-engine claim is already evidenced, not assumed.

**Scope emphasis (per user):** prioritise **analysis, statistics, data shaping, and merging**. Variable `import` is explicitly low priority — treat the offline data source as a parquet/CSV the user already has. `merge` is therefore in the vertical slice (Task 3b), and the statistics verbs are the lead item of Phase 2.

## Global Constraints

- Pure runtime ops MUST NOT import `js`, call `self._log`, or read `M2PY_DISCLOSURE_CONTROL`. Disclosure control, logging, and T6 reverts stay in the emulator wrapper. Verbatim seam rule: ops are deterministic `frame -> frame`.
- polars MUST NOT be imported at module top level of any file reachable from `m2py.py` / `index.html` — it is not available in Pyodide. Import polars lazily inside `polars_ops` / the polars emitter only.
- The existing `tests/test_equivalence.py` suite is the equivalence gate for the refactor: it MUST stay green after every refactor task (no regressions). Baseline before starting: run `pytest tests/test_equivalence.py -q` and record pass count.
- Norwegian user-facing log strings stay exactly as they are today (they live in the emulator, not the ops) — do not translate or alter them.
- Frame-type discipline: pandas ops take/return `pd.DataFrame`; polars ops take/return `pl.LazyFrame`. Never mix.

---

## File Structure

- Create: `m2py_runtime/__init__.py` — package marker + re-exports (`pandas_ops`).
- Create: `m2py_runtime/pandas_ops.py` — pure pandas ops: `generate`, `keep`, `drop`, `collapse`, `aggregate`. Extracted from `m2py.py`.
- Create: `m2py_runtime/exprcompile.py` — minimal microdata-expression → `pl.Expr` compiler (polars only).
- Create: `m2py_runtime/polars_ops.py` — pure polars ops mirroring `pandas_ops`, lazy (`pl.LazyFrame`). Imports polars lazily.
- Create: `m2py_translate.py` — `translate(script, backend) -> str`: IR-walk emitter for both backends.
- Modify: `m2py.py` — emulator delegates `generate`/`keep`/`collapse` to `m2py_runtime.pandas_ops` (the `stats_engine.execute` path at `m2py.py:8765/8803/4411` and the keep/drop block near `m2py.py:8481`).
- Create: `tests/test_runtime_ops.py` — direct unit tests on pure ops (pandas + polars parity).
- Create: `tests/test_translate_pandas.py` — translate→exec the pandas script, compare to emulator.
- Create: `tests/test_translate_polars_equiv.py` — translate→run polars LazyFrame, compare to pandas emulator over the existing `CASES`.

---

## Task 1: Scaffold runtime package + extract `pandas_ops.collapse`

`collapse` first because its body is self-contained (`m2py.py:4411-4451`) and the hardest behavioral shape (reshape+aggregate), so it most strongly validates the seam.

**Files:**
- Create: `m2py_runtime/__init__.py`
- Create: `m2py_runtime/pandas_ops.py`
- Create: `tests/test_runtime_ops.py`
- Modify: `m2py.py` (collapse path in `stats_engine.execute`, around `m2py.py:4411-4451`)

**Interfaces:**
- Produces: `m2py_runtime.pandas_ops.collapse(df: pd.DataFrame, targets: list[dict], by: str | None) -> pd.DataFrame` where each target is `{"stat": str, "src": str, "target": str | None}`. Returns a new aggregated frame (grouped: `groupby(by).agg(**{...}).reset_index()`; global: single-row frame). Raises `ValueError` for rejected stats / multi-key `by` / missing columns, matching today's messages.
- Consumes (Task 3,5,6): the same signature.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_runtime_ops.py
import pandas as pd
import pytest
from m2py_runtime import pandas_ops as ops


def test_collapse_grouped_mean():
    df = pd.DataFrame({"g": [1, 1, 2, 2, 3], "x": [10.0, 20.0, 5.0, 15.0, 100.0]})
    out = ops.collapse(df, targets=[{"stat": "mean", "src": "x", "target": "x"}], by="g")
    out = out.sort_values("g").reset_index(drop=True)
    assert out["x"].tolist() == [15.0, 10.0, 100.0]
    assert out["g"].tolist() == [1, 2, 3]


def test_collapse_global_two_stats():
    df = pd.DataFrame({"x": [10.0, 20.0, 5.0, 15.0]})
    out = ops.collapse(
        df,
        targets=[{"stat": "mean", "src": "x", "target": "m"},
                 {"stat": "sum", "src": "x", "target": "s"}],
        by=None,
    )
    assert len(out) == 1
    assert out["m"].iloc[0] == 12.5
    assert out["s"].iloc[0] == 50.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_runtime_ops.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'm2py_runtime'`.

- [ ] **Step 3: Create the package and extract the collapse body**

Create `m2py_runtime/__init__.py`:

```python
"""Pure, side-effect-free runtime ops shared by the emulator and the translators.

Ops are deterministic `frame -> frame`. No logging, no disclosure control, no
`self`. The emulator wraps these with logging/disclosure; the translators emit
calls to them. polars ops live in `polars_ops` and import polars lazily so this
package stays importable under Pyodide.
"""
from . import pandas_ops  # noqa: F401
```

Create `m2py_runtime/pandas_ops.py` — move the collapse logic from `m2py.py:4411-4451` into a free function. Copy the constant tables it uses (`AGG_STAT_ALIAS`, `_REJECTED_COLLAPSE_STATS`, `_SUPPORTED_COLLAPSE_STATS_DISPLAY`) by importing them from `m2py` to avoid duplication:

```python
import pandas as pd
from m2py import (
    AGG_STAT_ALIAS,
    _REJECTED_COLLAPSE_STATS,
    _SUPPORTED_COLLAPSE_STATS_DISPLAY,
)


def collapse(df, targets, by):
    # rejected-stat guard (was m2py.py:4414-4420)
    for t in targets:
        stat = (t.get("stat") or "").lower()
        if stat in _REJECTED_COLLAPSE_STATS:
            raise ValueError(
                f"collapse ({stat}) er ikke støttet i microdata.no. "
                f"Støttede statistikker: {_SUPPORTED_COLLAPSE_STATS_DISPLAY}."
            )
    # single-key guard (was m2py.py:4421-4432)
    if isinstance(by, str) and by.strip():
        by_keys = by.strip().split()
        if len(by_keys) > 1:
            raise ValueError(
                "microdata.no støtter bare én nøkkel-variabel i by(). "
                f"Fikk {len(by_keys)} ({', '.join(by_keys)})."
            )
        by = by_keys[0]
    missing = [t["src"] for t in targets if t["src"] not in df.columns]
    if missing:
        raise ValueError(f"Kolonner {missing} finnes ikke i datasettet.")
    agg_dict = {}
    for t in targets:
        stat_fn = AGG_STAT_ALIAS.get(t["stat"], t["stat"])
        target_col = t["target"] or t["src"]
        agg_dict[target_col] = (t["src"], stat_fn)
    if not by:
        row = {}
        for name, (src, fn) in agg_dict.items():
            s = df[src]
            row[name] = fn(s) if callable(fn) else s.agg(fn)
        return pd.DataFrame([row])
    return df.groupby(by, dropna=False).agg(**agg_dict).reset_index()
```

- [ ] **Step 4: Run the runtime unit test to verify it passes**

Run: `pytest tests/test_runtime_ops.py -v`
Expected: PASS (both collapse tests).

- [ ] **Step 5: Make the emulator delegate to the pure op**

In `m2py.py`, replace the collapse body inside `stats_engine.execute` (`m2py.py:4411-4451`) with a delegation, keeping the surrounding `cmd == 'collapse'` guard:

```python
        if cmd == 'collapse':
            from m2py_runtime import pandas_ops as _ops
            return _ops.collapse(df, args['targets'], options.get('by'))
```

(The disclosure/logging around collapse stays where it already is in `_execute_instruction`, `m2py.py:8804-8816`.)

- [ ] **Step 6: Run the equivalence gate to verify no regression**

Run: `pytest tests/test_equivalence.py -q`
Expected: same pass count as the recorded baseline (the `collapse_mean` and `collapse_two_stats` cases still pass).

- [ ] **Step 7: Commit**

```bash
git add m2py_runtime/ tests/test_runtime_ops.py m2py.py
git commit -m "refactor(runtime): extract collapse into pure m2py_runtime.pandas_ops"
```

---

## Task 2: Extract `pandas_ops.keep` / `pandas_ops.drop`

**Files:**
- Modify: `m2py_runtime/pandas_ops.py`
- Modify: `m2py.py` (keep/drop block near `m2py.py:8481`, row/column branches)
- Modify: `tests/test_runtime_ops.py`

**Interfaces:**
- Produces: `keep(df, columns: list[str] | None, cond: str | None) -> pd.DataFrame` and `drop(df, columns: list[str] | None, cond: str | None) -> pd.DataFrame`. Column-form keeps/drops the listed columns; condition-form keeps/drops matching rows. `cond` is a microdata condition string evaluated via the existing `m2py._py_eval_cond`. Returns a new frame; never mutates input.
- Consumes: `m2py._py_eval_cond(df, cond) -> pd.Series[bool]` (existing module-level helper).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_runtime_ops.py
def test_keep_rows_by_condition():
    df = pd.DataFrame({"age": [10, 20, 30, 18, 40, 5], "inc": [1, 2, 3, 4, 5, 6]})
    out = ops.keep(df, columns=None, cond="age > 18")
    assert out["age"].tolist() == [20, 30, 40]


def test_keep_columns():
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6]})
    out = ops.keep(df, columns=["a", "b"], cond=None)
    assert list(out.columns) == ["a", "b"]


def test_drop_columns():
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6]})
    out = ops.drop(df, columns=["c"], cond=None)
    assert list(out.columns) == ["a", "b"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_runtime_ops.py -k "keep or drop" -v`
Expected: FAIL — `AttributeError: module 'm2py_runtime.pandas_ops' has no attribute 'keep'`.

- [ ] **Step 3: Implement keep/drop in pandas_ops**

```python
# in m2py_runtime/pandas_ops.py
def keep(df, columns, cond):
    if columns:
        return df[[c for c in columns if c in df.columns]].copy()
    from m2py import _py_eval_cond
    mask = _py_eval_cond(df, cond)
    return df.loc[mask].reset_index(drop=True)


def drop(df, columns, cond):
    if columns:
        return df.drop(columns=[c for c in columns if c in df.columns]).copy()
    from m2py import _py_eval_cond
    mask = _py_eval_cond(df, cond)
    return df.loc[~mask].reset_index(drop=True)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_runtime_ops.py -k "keep or drop" -v`
Expected: PASS.

- [ ] **Step 5: Delegate from the emulator**

In `m2py.py` near `m2py.py:8481`, replace the inline row/column keep/drop computation with calls to `pandas_ops.keep`/`drop`, preserving the surrounding observation-count log lines (`m2py.py:8482-8489`). Use the parsed column list / `cond` already available in that block.

- [ ] **Step 6: Run the equivalence gate**

Run: `pytest tests/test_equivalence.py -q`
Expected: baseline pass count (cases `keep_filter`, `keep_query`, `keep_columns`, `drop_columns` green).

- [ ] **Step 7: Commit**

```bash
git add m2py_runtime/pandas_ops.py m2py.py tests/test_runtime_ops.py
git commit -m "refactor(runtime): extract keep/drop into pandas_ops"
```

---

## Task 3: Extract `pandas_ops.generate`

`generate` routes through `stats_engine.execute` today (`m2py.py:8765`). Extract the column-assignment core; leave T6/disclosure/logging in the emulator wrapper (`m2py.py:8757-8801`).

**Files:**
- Modify: `m2py_runtime/pandas_ops.py`
- Modify: `m2py.py` (`stats_engine.execute` generate branch)
- Modify: `tests/test_runtime_ops.py`

**Interfaces:**
- Produces: `generate(df, target: str, expr: str, cond: str | None) -> pd.DataFrame`. Evaluates `expr` via existing `m2py._py_eval_expr`; when `cond` is given, assigns only where the condition mask is true (leaving other rows unchanged / NaN for a new column). Returns a new frame.
- Consumes: `m2py._py_eval_expr(df, expr) -> pd.Series`, `m2py._py_eval_cond`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_runtime_ops.py
def test_generate_arith():
    df = pd.DataFrame({"a": [0, 1, 2, 3], "b": [4, 3, 2, 1]})
    out = ops.generate(df, target="x", expr="a + b * 2", cond=None)
    assert out["x"].tolist() == [8, 7, 6, 5]


def test_generate_if_condition():
    df = pd.DataFrame({"a": [-2, -1, 0, 1, 2]})
    out = ops.generate(df, target="pos", expr="1", cond="a > 0")
    assert out.loc[out["a"] > 0, "pos"].tolist() == [1, 1]
    assert out.loc[out["a"] <= 0, "pos"].isna().all()
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_runtime_ops.py -k generate -v`
Expected: FAIL — no attribute `generate`.

- [ ] **Step 3: Implement generate**

```python
# in m2py_runtime/pandas_ops.py
import numpy as np

def generate(df, target, expr, cond):
    from m2py import _py_eval_expr, _py_eval_cond
    out = df.copy()
    values = _py_eval_expr(out, expr)
    if cond:
        mask = _py_eval_cond(out, cond)
        if target in out.columns:
            out.loc[mask, target] = values[mask] if hasattr(values, "__getitem__") else values
        else:
            col = pd.Series(np.nan, index=out.index)
            col[mask] = values[mask] if hasattr(values, "__getitem__") else values
            out[target] = col
    else:
        out[target] = values
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_runtime_ops.py -k generate -v`
Expected: PASS.

- [ ] **Step 5: Delegate from the emulator**

In the generate branch of `stats_engine.execute` (`m2py.py:8765` calls `self.stats_engine.execute(cmd, df_target, args, run_opts)`), have the underlying handler call `pandas_ops.generate(df, args['target'], args['expr'], condition)` and write the result back to `self.datasets[self.active_name]`. Keep the T6 check / log block at `m2py.py:8768-8800` unchanged.

- [ ] **Step 6: Run the equivalence gate**

Run: `pytest tests/test_equivalence.py -q`
Expected: baseline pass count (generate_* cases green).

- [ ] **Step 7: Commit**

```bash
git add m2py_runtime/pandas_ops.py m2py.py tests/test_runtime_ops.py
git commit -m "refactor(runtime): extract generate into pandas_ops"
```

---

## Task 4: Thin pandas translator (`backend="pandas"`)

**Files:**
- Create: `m2py_translate.py`
- Create: `tests/test_translate_pandas.py`

**Interfaces:**
- Produces: `m2py_translate.translate(script: str, backend: str = "pandas", source_path: str = "df") -> str`. Returns a runnable Python program string. For `backend="pandas"` it emits `import pandas as pd` + `from m2py_runtime import pandas_ops as ops`, loads `df = pd.read_parquet(f"{source_path}.parquet")` (or accepts an in-memory `df` when `source_path` is None), then one `df = ops.<verb>(df, ...)` line per supported instruction, and `df.to_parquet("result.parquet")`. Unsupported verbs emit a `# UNTRANSLATED: <line>` comment.
- Consumes: `m2py.MicroParser().parse_line(line)` for the IR; the `pandas_ops` signatures from Tasks 1-3.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_translate_pandas.py
import pandas as pd
import m2py_translate


def test_translate_pandas_runs_and_matches_emulator(tmp_path):
    script = (
        "generate x = a + b * 2\n"
        "keep if a > 0\n"
        "collapse (mean) x -> mx, by(g)\n"
    )
    df = pd.DataFrame({"a": [0, 1, 2, 3], "b": [4, 3, 2, 1], "g": [1, 1, 2, 2]})

    code = m2py_translate.translate(script, backend="pandas", source_path=None)
    ns = {"df": df.copy(), "pd": pd}
    exec(code, ns)
    out = ns["df"].sort_values("g").reset_index(drop=True)

    assert "UNTRANSLATED" not in code
    assert "mx" in out.columns
    # a>0 keeps rows 1,2,3 -> x=[7,6,5]; group g: 1->{7}, 2->{6,5}
    assert out.loc[out["g"] == 1, "mx"].iloc[0] == 7.0
    assert out.loc[out["g"] == 2, "mx"].iloc[0] == 5.5
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_translate_pandas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'm2py_translate'`.

- [ ] **Step 3: Implement the translator**

```python
# m2py_translate.py
"""Walk the microdata IR and emit a runnable script of thin runtime-op calls.

backend="pandas" -> calls m2py_runtime.pandas_ops (eager pd.DataFrame).
backend="polars" -> calls m2py_runtime.polars_ops (lazy pl.LazyFrame).  [Task 6]
"""
import m2py


def _emit_pandas(instr):
    cmd, args, opts, cond = (
        instr["command"], instr["args"], instr["options"], instr["condition"])
    if cmd == "generate":
        return (f"df = ops.generate(df, target={args['target']!r}, "
                f"expr={args['expr']!r}, cond={cond!r})")
    if cmd in ("keep", "drop"):
        cols = args.get("columns") if isinstance(args, dict) else None
        return f"df = ops.{cmd}(df, columns={cols!r}, cond={cond!r})"
    if cmd == "collapse":
        return (f"df = ops.collapse(df, targets={args['targets']!r}, "
                f"by={opts.get('by')!r})")
    return None


def translate(script, backend="pandas", source_path="df"):
    parser = m2py.MicroParser()
    header = ["import pandas as pd", "from m2py_runtime import pandas_ops as ops"]
    if source_path is not None:
        header.append(f'df = pd.read_parquet("{source_path}.parquet")')
    body = []
    for line in script.splitlines():
        if not line.strip():
            continue
        instr = parser.parse_line(line)
        if not instr:
            continue
        emitted = _emit_pandas(instr)
        body.append(emitted if emitted else f"# UNTRANSLATED: {line.strip()}")
    footer = ['df.to_parquet("result.parquet")'] if source_path is not None else []
    return "\n".join(header + [""] + body + [""] + footer) + "\n"
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_translate_pandas.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add m2py_translate.py tests/test_translate_pandas.py
git commit -m "feat(translate): thin pandas exporter over runtime ops (generate/keep/collapse)"
```

---

## Task 5: polars ops + minimal expression compiler

**Files:**
- Create: `m2py_runtime/exprcompile.py`
- Create: `m2py_runtime/polars_ops.py`
- Modify: `tests/test_runtime_ops.py`

**Interfaces:**
- Produces: `m2py_runtime.exprcompile.to_polars_expr(expr: str) -> pl.Expr` supporting column names, int/float/string literals, `+ - * /`, comparisons `> >= < <= == !=`, boolean `& |`, and parentheses. Raises `ValueError` on unsupported syntax (callers catch → UNTRANSLATED).
- Produces: `m2py_runtime.polars_ops.generate/keep/drop/collapse` mirroring `pandas_ops` but on `pl.LazyFrame`. `generate(lf, target, expr, cond)`, `keep(lf, columns, cond)`, `collapse(lf, targets, by)`. polars imported lazily inside the module.

- [ ] **Step 1: Write the failing test (polars parity vs pandas)**

```python
# add to tests/test_runtime_ops.py
import polars as pl
from m2py_runtime import polars_ops as pops


def test_polars_generate_keep_collapse_matches_pandas():
    data = {"a": [0, 1, 2, 3], "b": [4, 3, 2, 1], "g": [1, 1, 2, 2]}
    # pandas path
    pdf = pd.DataFrame(data)
    pdf = ops.generate(pdf, "x", "a + b * 2", None)
    pdf = ops.keep(pdf, None, "a > 0")
    pdf = ops.collapse(pdf, [{"stat": "mean", "src": "x", "target": "mx"}], "g")
    pdf = pdf.sort_values("g").reset_index(drop=True)
    # polars path
    lf = pl.LazyFrame(data)
    lf = pops.generate(lf, "x", "a + b * 2", None)
    lf = pops.keep(lf, None, "a > 0")
    out = pops.collapse(lf, [{"stat": "mean", "src": "x", "target": "mx"}], "g")
    pol = out.collect().sort("g").to_pandas()
    assert pol["mx"].tolist() == pdf["mx"].tolist()
    assert pol["g"].tolist() == pdf["g"].tolist()
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_runtime_ops.py -k polars -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'm2py_runtime.polars_ops'`.

- [ ] **Step 3: Implement the expression compiler**

```python
# m2py_runtime/exprcompile.py
"""Tiny microdata-expression -> polars.Expr compiler (vertical-slice subset).

Supports: column refs, int/float/'string' literals, + - * /, comparisons,
& |, parentheses. Anything else raises ValueError so the caller can mark the
line UNTRANSLATED rather than emit wrong polars.
"""
import ast


def to_polars_expr(expr):
    import polars as pl

    def conv(node):
        if isinstance(node, ast.Expression):
            return conv(node.body)
        if isinstance(node, ast.BinOp):
            l, r = conv(node.left), conv(node.right)
            op = node.op
            if isinstance(op, ast.Add):  return l + r
            if isinstance(op, ast.Sub):  return l - r
            if isinstance(op, ast.Mult): return l * r
            if isinstance(op, ast.Div):  return l / r
            raise ValueError(f"unsupported operator {op!r}")
        if isinstance(node, ast.BoolOp):
            vals = [conv(v) for v in node.values]
            acc = vals[0]
            for v in vals[1:]:
                acc = (acc & v) if isinstance(node.op, ast.And) else (acc | v)
            return acc
        if isinstance(node, ast.Compare):
            if len(node.ops) != 1:
                raise ValueError("chained comparison unsupported")
            l, r, op = conv(node.left), conv(node.comparators[0]), node.ops[0]
            if isinstance(op, ast.Gt):    return l > r
            if isinstance(op, ast.GtE):   return l >= r
            if isinstance(op, ast.Lt):    return l < r
            if isinstance(op, ast.LtE):   return l <= r
            if isinstance(op, ast.Eq):    return l == r
            if isinstance(op, ast.NotEq): return l != r
            raise ValueError(f"unsupported comparison {op!r}")
        if isinstance(node, ast.Name):
            return pl.col(node.id)
        if isinstance(node, ast.Constant):
            return pl.lit(node.value)
        raise ValueError(f"unsupported node {type(node).__name__}")

    return conv(ast.parse(expr, mode="eval"))
```

- [ ] **Step 4: Implement polars_ops**

```python
# m2py_runtime/polars_ops.py
"""Pure polars ops (lazy). polars imported lazily — never under Pyodide."""
from .exprcompile import to_polars_expr

# polars stat name mapping (microdata stat -> polars Expr method)
_AGG = {"mean": "mean", "sum": "sum", "min": "min", "max": "max",
        "count": "count", "median": "median", "std": "std"}


def generate(lf, target, expr, cond):
    e = to_polars_expr(expr)
    if cond:
        import polars as pl
        e = pl.when(to_polars_expr(cond)).then(e).otherwise(None)
    return lf.with_columns(e.alias(target))


def keep(lf, columns, cond):
    if columns:
        return lf.select(columns)
    return lf.filter(to_polars_expr(cond))


def drop(lf, columns, cond):
    import polars as pl
    if columns:
        return lf.drop(columns)
    return lf.filter(~to_polars_expr(cond))


def collapse(lf, targets, by):
    import polars as pl
    aggs = []
    for t in targets:
        method = _AGG.get(t["stat"], t["stat"])
        col = t["target"] or t["src"]
        aggs.append(getattr(pl.col(t["src"]), method)().alias(col))
    if not by:
        return lf.select(aggs)
    return lf.group_by(by).agg(aggs)
```

- [ ] **Step 5: Run to verify parity passes**

Run: `pytest tests/test_runtime_ops.py -k polars -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add m2py_runtime/exprcompile.py m2py_runtime/polars_ops.py tests/test_runtime_ops.py
git commit -m "feat(runtime): polars ops + minimal expr compiler (vertical slice)"
```

---

## Task 6: polars emitter + offline equivalence harness

**Files:**
- Modify: `m2py_translate.py` (add `backend="polars"` path)
- Create: `tests/test_translate_polars_equiv.py`

**Interfaces:**
- Consumes: `m2py_translate.translate(script, backend="polars")` emits `import polars as pl` + `from m2py_runtime import polars_ops as ops`, `lf = pl.scan_parquet(...)` (or `pl.LazyFrame(data)` when source is in-memory), thin op-calls, ending `df = lf.collect(streaming=True)`.
- Reuses: the `CASES` list and `assert_equivalent` from `tests/test_equivalence.py` as the cross-engine oracle.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_translate_polars_equiv.py
import pandas as pd
import polars as pl
import pytest

import m2py_translate
from py2m import transform
from tests.test_equivalence import CASES, assert_equivalent, _run_microdata


# only the verbs the vertical slice supports
_SLICE = {"generate_arith", "keep_filter", "collapse_mean", "collapse_two_stats"}


@pytest.mark.parametrize("case", [c for c in CASES if c[0] in _SLICE], ids=lambda c: c[0])
def test_polars_matches_emulator(case):
    _id, python, data, result = case
    script = transform(python).script()
    # emulator (pandas) ground truth
    emu = _run_microdata(script, pd.DataFrame(data), result)
    # polars path
    code = m2py_translate.translate(script, backend="polars", source_path=None)
    assert "UNTRANSLATED" not in code, code
    ns = {"data": data, "pl": pl}
    exec(code, ns)
    pol = ns["df"].to_pandas()
    assert_equivalent(emu, pol, code)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_translate_polars_equiv.py -v`
Expected: FAIL — translator has no polars backend yet (emits UNTRANSLATED or wrong header).

- [ ] **Step 3: Add the polars emitter**

```python
# in m2py_translate.py
from m2py_runtime import polars_ops  # noqa: F401  (signature reference)


def _emit_polars(instr):
    cmd, args, opts, cond = (
        instr["command"], instr["args"], instr["options"], instr["condition"])
    if cmd == "generate":
        return (f"lf = ops.generate(lf, target={args['target']!r}, "
                f"expr={args['expr']!r}, cond={cond!r})")
    if cmd in ("keep", "drop"):
        cols = args.get("columns") if isinstance(args, dict) else None
        return f"lf = ops.{cmd}(lf, columns={cols!r}, cond={cond!r})"
    if cmd == "collapse":
        return (f"lf = ops.collapse(lf, targets={args['targets']!r}, "
                f"by={opts.get('by')!r})")
    return None
```

Extend `translate()` to branch on backend:

```python
def translate(script, backend="pandas", source_path="df"):
    parser = m2py.MicroParser()
    if backend == "polars":
        header = ["import polars as pl",
                  "from m2py_runtime import polars_ops as ops"]
        if source_path is not None:
            header.append(f'lf = pl.scan_parquet("{source_path}.parquet")')
        else:
            header.append("lf = pl.LazyFrame(data)")
        emit, footer = _emit_polars, ["df = lf.collect(streaming=True)"]
        if source_path is not None:
            footer.append('df.write_parquet("result.parquet")')
    else:
        header = ["import pandas as pd",
                  "from m2py_runtime import pandas_ops as ops"]
        if source_path is not None:
            header.append(f'df = pd.read_parquet("{source_path}.parquet")')
        emit = _emit_pandas
        footer = ['df.to_parquet("result.parquet")'] if source_path is not None else []
    body = []
    for line in script.splitlines():
        if not line.strip():
            continue
        instr = parser.parse_line(line)
        if not instr:
            continue
        out = emit(instr)
        body.append(out if out else f"# UNTRANSLATED: {line.strip()}")
    return "\n".join(header + [""] + body + [""] + footer) + "\n"
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_translate_polars_equiv.py -v`
Expected: PASS for all slice cases.

- [ ] **Step 5: Run the full suite to confirm no regression**

Run: `pytest tests/test_equivalence.py tests/test_runtime_ops.py tests/test_translate_pandas.py tests/test_translate_polars_equiv.py -q`
Expected: all green; `tests/test_equivalence.py` at baseline pass count.

- [ ] **Step 6: Commit**

```bash
git add m2py_translate.py tests/test_translate_polars_equiv.py
git commit -m "feat(translate): polars lazy/streaming emitter + offline equivalence harness"
```

---

## Phase 2 (outline — separate plan once the slice validates)

Do NOT start these until the vertical slice is green and reviewed. Each repeats the Task-1 shape (failing unit test on the pure op → extract/delegate → keep equivalence green → add emitter cases → cross-engine test):

1. **Remaining data-shaping verbs:** `replace`, `recode`, `aggregate`, `destring`, `merge`, `reshape-to-panel`/`reshape-from-panel`, `tabulate`, `summarize`. Extract each to `pandas_ops`, add `polars_ops` + emitter, extend the cross-engine harness.
2. **Expression-compiler coverage:** widen `exprcompile` to the microdata function library in `functions.py` (`year`, `substr`, `inrange`, `missing`, …), mapping each to a `pl.Expr`. Anything unmapped stays UNTRANSLATED (logged, never silently wrong).
3. **`import` → data source:** map `import VAR date as alias` to `pl.scan_parquet`/`scan_csv` of a user-supplied extract; document the DuckDB→parquet→polars pipeline (DuckDB builds the big extract, polars scans it lazily).
4. **Stats verbs fallback:** `regress`/`logit`/`cox`/… emit `pdf = lf.collect().to_pandas()` then call the existing statsmodels/lifelines code — no polars reimplementation.
5. **Execution/trust + packaging:** decide Uplink/local-runner-next-to-the-data vs hosted endpoint (data-sensitivity fork). Package `m2py_runtime` so a generated script runs standalone; for an HTTP endpoint accept the *microdata script* (constrained DSL) and translate server-side — never accept arbitrary Python over the wire.
6. **UI wiring:** add a "Export → polars/pandas script" action in `index.html` calling `translate(...)`; this is display/download only, no Pyodide polars.

---

## Self-Review

**Spec coverage:**
- "Refactor: lift each command's logic into a runtime library" → Tasks 1-3 (collapse/keep/drop/generate extracted to pure `pandas_ops`; emulator delegates; equivalence gate proves parity). Phase 2.1 rolls out the rest.
- "A translator to python/pandas" → Task 4 (thin pandas exporter).
- "Offline polars support" → Tasks 5-6 (polars ops + lazy/streaming emitter + cross-engine harness).
- "Analyse and make a plan" → this document; architecture + global constraints + phased rollout.

**Placeholder scan:** No "TBD"/"add error handling"/"similar to Task N". Extraction tasks cite exact `m2py.py` line ranges; new code is shown in full. Phase 2 is explicitly an outline to be expanded into its own plan, not executable steps — flagged as such.

**Type consistency:** `collapse(df|lf, targets: list[dict {stat,src,target}], by)`, `keep/drop(frame, columns, cond)`, `generate(frame, target, expr, cond)` used identically in pandas_ops (Tasks 1-3), polars_ops (Task 5), and both emitters (Tasks 4, 6). `translate(script, backend, source_path)` signature stable across Tasks 4 and 6. `to_polars_expr(expr)` consumed only inside polars_ops.

**Known risk to verify during execution:** the exact internal call shape of the `generate` branch inside `stats_engine.execute` (Task 3, Step 5) and the keep/drop block (Task 2, Step 5) must be read in full before editing — the delegation wiring is the one place line numbers may have drifted. The equivalence gate (`pytest tests/test_equivalence.py`) catches any wiring mistake immediately.
