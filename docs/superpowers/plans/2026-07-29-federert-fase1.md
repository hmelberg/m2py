# Federert fase 1 (node-federering, microdata-modus) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A microdata-mode script against a federated source with node members runs on every node (each node returns only SDC-gated combineable statistics), and the browser combines them into one exact result — raw rows never leave any node.

**Architecture:** Node side: `m2py_runtime/federate.py` extracts per-verb combineable stats from the `result_*` namespace (tabulate cells, summarize moments, regress sufficient statistics captured by `pandas_ops.regress` behind a `set_federated` flag), each gated by the node's own `PandasProtect` policy; `m2py_remote.run_remote[_from_sources]` gains `federated=True` returning `stats`. Combine side: the SAME module's `combine_stats`/`combine_and_render` merges N nodes' stats exactly (sum cells, pool moments, pool XᵀX/Xᵀy) — one Python implementation, pytest-tested, run in Pyodide by the browser. Browser: `Federate.runNodes` (js/federate.js) fans `run_extended` out per node and polls; `maybeRunFederatedMicrodata` (index.html) detects a federated registry entry with node members, fans out, combines in Pyodide, renders via the existing SafeStat renderer. A ~90-line dev node (`scripts/dev_federert_node.py`, plain http.server wrapping `run_remote_from_sources`) makes the whole loop verifiable locally.

**Tech Stack:** pandas/numpy (+scipy t-dist when importable), pytest, ES5 IIFE JS + node:test, Pyodide bridge, Python http.server for dev nodes.

**Spec:** `docs/superpowers/specs/2026-07-29-federated-sources-design.md` §5 (+§3 annotations, §7 testing). Deviations from spec, both deliberate: (1) combine math lives in Python (`m2py_runtime/federate.py`, runs in Pyodide) instead of JS — one implementation, testable with pytest; `js/federate.js` keeps only fan-out/poll orchestration. (2) v1 scope: exactly ONE required source per federated script; logistic regression, percentiles/median and figures are refused with clear messages (per spec's verb table).

## Global Constraints

- Python matches existing style (m2py_runtime modules: no type-annotation ceremony, Norwegian user-facing messages, docstrings in English).
- JS: ES5 IIFE style; user-facing errors Norwegian with «…» around identifiers.
- Per-node SDC before anything leaves a node (spec §5): the node's `post_suppress` spec is applied to emitted stats exactly as to rendered results; sufficient statistics are refused when local `n < min_n` or any design column's at-risk count `< min_n`.
- Combine alignment is positional: same script runs on every node, `result_*` keys are collected in `sorted(ns)` order everywhere.
- Cell semantics in combine: absent category = 0; suppressed (null) anywhere → combined cell suppressed (documented over-suppression, spec §5).
- Tests: `python3 -m pytest tests/ -q` and `node --test tests/js/*.test.js` (Node 26: the dir form fails).
- Commit per task; no pushes.

---

### Task 1: `pandas_ops` federated flag + regress sufficient statistics

**Files:**
- Modify: `m2py_runtime/pandas_ops.py` (`set_release_spec` block at line ~36; `regress` at line ~1021)
- Test: `tests/test_federate_stats.py` (new)

**Interfaces:**
- Produces: `pandas_ops.set_federated(flag)` / `pandas_ops.get_federated()` (thread-local, mirrors `set_release_spec`). When federated, `regress(df, dep, indep, noconstant=False)` returns the usual `[term, coef, se, t, p]` DataFrame with `df.attrs["fedstats"] = {"terms": [str], "xtx": [[float]], "xty": [float], "yty": float, "n": int, "at_risk": [int]}` attached. Task 2 reads `attrs["fedstats"]`; Task 4 consumes the same dict shape.

- [x] **Step 1: Write the failing test**

Create `tests/test_federate_stats.py`:

```python
"""Node-side federated statistics (fase 1, spec 2026-07-29 §5)."""
import numpy as np
import pandas as pd
import pytest
from m2py_runtime import pandas_ops as ops


@pytest.fixture(autouse=True)
def _reset_federated():
    yield
    ops.set_federated(False)


def _df(n=20, seed=1):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    return pd.DataFrame({"y": 2 + 3 * x + rng.normal(scale=0.1, size=n), "x": x})


def test_regress_attaches_fedstats_only_when_federated():
    df = _df()
    plain = ops.regress(df, "y", ["x"])
    assert "fedstats" not in plain.attrs
    ops.set_federated(True)
    fed = ops.regress(df, "y", ["x"])
    fs = fed.attrs["fedstats"]
    assert fs["terms"] == ["const", "x"]
    assert fs["n"] == 20
    X = np.column_stack([np.ones(20), df["x"].to_numpy()])
    assert np.allclose(fs["xtx"], X.T @ X)
    assert np.allclose(fs["xty"], X.T @ df["y"].to_numpy())
    assert fs["yty"] == pytest.approx(float(df["y"] @ df["y"]))
    assert fs["at_risk"][0] == 20
```

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_federate_stats.py -q`
Expected: FAIL — `AttributeError: ... has no attribute 'set_federated'`.

- [x] **Step 3: Implement**

In `m2py_runtime/pandas_ops.py`, right after `get_release_spec()` (line ~41) add:

```python
def set_federated(flag):
    """Fase 1 federert (spec 2026-07-29 §5): når satt, legger regress ved
    sufficient statistics i result.attrs['fedstats'] så en node kan frigi
    kombinerbare aggregater i stedet for bare koeffisienttabellen."""
    _release_ctx.federated = bool(flag)


def get_federated():
    return getattr(_release_ctx, "federated", False)
```

Replace `regress` (line ~1021):

```python
def regress(df, dep, indep, noconstant=False):
    """OLS coefficient table ``[term, coef, se, t, p]``."""
    if get_federated():
        model, X, Y, idx = _fit_model(df, "regress", dep, indep, noconstant,
                                      return_design=True)
        out = _coef_table(model)
        Xa = np.asarray(X, dtype=float)
        Ya = np.asarray(Y, dtype=float)
        out.attrs["fedstats"] = {
            "terms": [str(c) for c in X.columns],
            "xtx": (Xa.T @ Xa).tolist(),
            "xty": (Xa.T @ Ya).tolist(),
            "yty": float(Ya @ Ya),
            "n": int(len(Ya)),
            "at_risk": [int(v) for v in (Xa != 0).sum(axis=0)],
        }
        return out
    return _coef_table(_fit_model(df, "regress", dep, indep, noconstant))
```

(Verify `_fit_model(..., return_design=True)` returns `(model, X, Y, idx)` — it does for `_binary_predict` at line ~1038; if the tuple shape differs for "regress", adapt the unpacking to what `_fit_model` actually returns and keep the attrs dict shape EXACTLY as above.)

- [x] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_federate_stats.py -q` → 1 passed.
Guard: `python3 -m pytest tests/ -q` → all pass.

- [x] **Step 5: Commit**

```bash
git add m2py_runtime/pandas_ops.py tests/test_federate_stats.py
git commit -m "feat(federert): regress emits sufficient statistics behind set_federated flag"
```

---

### Task 2: `extract_stats` — per-verb combineable payloads with per-node SDC

**Files:**
- Create: `m2py_runtime/federate.py`
- Test: `tests/test_federate_stats.py` (extend)

**Interfaces:**
- Consumes: `attrs["fedstats"]` (Task 1), `m2py_protection.PandasProtect.suppress(result, spec)` (existing; returns a str refusal for sparse tables, NaN-masked + rounded frame otherwise).
- Produces: `federate.extract_stats(ns, spec)` → list of dicts in `sorted(ns)` order over `result_*` keys, one of:
  - `{"kind": "tabulate", "keys": [str], "records": [{...}], "dropped": [str]}` (records' `n` may be `None` = suppressed; pct/chi2 columns dropped)
  - `{"kind": "summarize", "keys": [str], "records": [{...}], "dropped": [str]}` (stats kept: count, mean, std, min, max; percentile columns dropped; suppressed stats are `None`)
  - `{"kind": "regress", **fedstats}` (fedstats dict from Task 1)
  - `{"kind": "refused", "reason": str}` (sparse-table refusal, regress below threshold)
  - `{"kind": "unsupported", "reason": str}` (anything else, incl. figures noted once)
  All values JSON-safe (floats/ints/strings/None). Tasks 3–5 consume this list.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_federate_stats.py`:

```python
from m2py_runtime import federate

SPEC = {"min_n": 5, "round": 10, "percentile_sig_figs": 3,
        "max_low_cell_share": 0.5}


def _tab_ns():
    df = pd.DataFrame({"grp": [1] * 6 + [2] * 3})
    return {"result_1": ops.tabulate(df, ["grp"])}


def test_extract_tabulate_public_keeps_exact_counts():
    stats = federate.extract_stats(_tab_ns(), None)
    assert stats[0]["kind"] == "tabulate"
    assert stats[0]["keys"] == ["grp"]
    assert {r["grp"]: r["n"] for r in stats[0]["records"]} == {1: 6, 2: 3}


def test_extract_tabulate_protected_masks_and_rounds():
    stats = federate.extract_stats(_tab_ns(), SPEC)
    by = {r["grp"]: r["n"] for r in stats[0]["records"]}
    assert by[2] is None          # 3 < min_n -> suppressed
    assert by[1] == 10            # 6 rounds to 10


def test_extract_summarize_drops_percentiles():
    df = pd.DataFrame({"inntekt": [10.0, 20, 30, 40, 50, 60],
                       "grp": [1, 1, 1, 2, 2, 2]})
    ns = {"result_1": ops.summarize(df, vars=["inntekt"], by=["grp"])}
    stats = federate.extract_stats(ns, None)
    s = stats[0]
    assert s["kind"] == "summarize"
    assert set(s["keys"]) == {"grp", "variable"}
    r1 = next(r for r in s["records"] if r["grp"] == 1)
    assert r1["count"] == 3 and r1["mean"] == 20.0
    assert not any(c.startswith("p") and c[1:].isdigit() for r in s["records"] for c in r)


def test_extract_regress_public_emits_fedstats():
    ops.set_federated(True)
    ns = {"result_1": ops.regress(_df(), "y", ["x"])}
    stats = federate.extract_stats(ns, None)
    assert stats[0]["kind"] == "regress"
    assert stats[0]["terms"] == ["const", "x"]


def test_extract_regress_below_threshold_refused():
    ops.set_federated(True)
    ns = {"result_1": ops.regress(_df(n=4), "y", ["x"])}
    stats = federate.extract_stats(ns, SPEC)
    assert stats[0]["kind"] == "refused"
    assert "for få" in stats[0]["reason"]


def test_extract_unknown_and_figures_unsupported():
    ns = {"result_1": "just a string", "fig_1": object()}
    stats = federate.extract_stats(ns, None)
    assert stats[0]["kind"] == "unsupported"
```

- [x] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_federate_stats.py -q`
Expected: FAIL — `ImportError: cannot import name 'federate'`.

- [x] **Step 3: Implement**

Create `m2py_runtime/federate.py`:

```python
"""Fase 1 federert (spec 2026-07-29-federated-sources-design §5).

Node side: extract_stats turns the result_* namespace into JSON-safe,
combineable, per-node-SDC-gated statistics. Combine side (Tasks 3-4):
combine_stats/combine_and_render pool N nodes' stats exactly. ONE module for
both so pytest covers the math the browser (via Pyodide) executes.
"""
from __future__ import annotations

import math

_PCT_COLS = ("cellpct", "rowpct", "colpct")
_SUM_STATS = ("count", "mean", "std", "min", "max")


def _jsonsafe(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else (int(f) if f.is_integer() else f)
    except (TypeError, ValueError):
        return str(v)


def _records(frame, cols):
    out = []
    for _, row in frame[cols].iterrows():
        out.append({c: _jsonsafe(row[c]) for c in cols})
    return out


def extract_stats(ns, spec):
    """[{kind, ...}] i sorted(ns)-rekkefølge over result_*-nøklene."""
    import pandas as pd
    from m2py_protection import PandasProtect
    adapter = PandasProtect()
    stats = []
    for k in sorted(ns):
        if not k.startswith("result_"):
            continue
        r = ns[k]
        if isinstance(r, pd.DataFrame) and "fedstats" in r.attrs:
            fs = r.attrs["fedstats"]
            min_n = (spec or {}).get("min_n")
            if min_n and (fs["n"] < min_n or any(a < min_n for a in fs["at_risk"])):
                stats.append({"kind": "refused", "reason":
                              "Personvern: for få enheter hos denne noden til å "
                              f"frigi regresjonsstatistikk (krever minst {min_n})."})
            else:
                stats.append(dict(fs, kind="regress"))
            continue
        if isinstance(r, pd.DataFrame) and "n" in r.columns:
            sup = adapter.suppress(r, spec)
            if isinstance(sup, str):
                stats.append({"kind": "refused", "reason": sup})
                continue
            dropped = [c for c in sup.columns
                       if c in _PCT_COLS or c.startswith("chi2")]
            keys = [c for c in sup.columns if c != "n" and c not in dropped]
            stats.append({"kind": "tabulate", "keys": keys, "dropped": dropped,
                          "records": _records(sup, keys + ["n"])})
            continue
        if isinstance(r, pd.DataFrame) and "count" in r.columns:
            sup = adapter.suppress(r, spec)
            if isinstance(sup, str):
                stats.append({"kind": "refused", "reason": sup})
                continue
            stat_cols = [c for c in sup.columns if c in _SUM_STATS]
            keys = [c for c in sup.columns
                    if c not in _SUM_STATS
                    and not (c.startswith("p") and c[1:].isdigit())
                    and c not in ("gini", "iqr")]
            dropped = [c for c in sup.columns if c not in stat_cols and c not in keys]
            stats.append({"kind": "summarize", "keys": keys, "dropped": dropped,
                          "records": _records(sup, keys + stat_cols)})
            continue
        stats.append({"kind": "unsupported", "reason":
                      "Federert kjøring støtter ikke dette resultatet ennå — "
                      "støttede verb: tabulate, summarize, regress."})
    return stats
```

- [x] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_federate_stats.py -q` → all pass. Full: `python3 -m pytest tests/ -q`.

- [x] **Step 5: Commit**

```bash
git add m2py_runtime/federate.py tests/test_federate_stats.py
git commit -m "feat(federert): node-side stat extraction with per-node SDC gating"
```

---

### Task 3: `combine_stats` — tabulate + summarize (exact pooling, null-poisoning)

**Files:**
- Modify: `m2py_runtime/federate.py`
- Test: `tests/test_federate_combine.py` (new)

**Interfaces:**
- Consumes: Task 2's stat payload shapes.
- Produces: `federate.combine_stats(per_node)` where `per_node = [{"member": str, "stats": [...]}]` → list (positional, same length as each node's stats) of:
  - `{"kind": "tabulate", "frame": DataFrame(keys + n)}`
  - `{"kind": "summarize", "frame": DataFrame(keys + count/mean/std[/min/max])}`
  - `{"kind": "refused"|"unsupported", "reason": str}` (a refusal on ANY node poisons that position, reason names the member)
  Rule: absent category = 0 contribution; `None` (suppressed) anywhere → combined cell None. Task 4 adds regress; Task 5 renders.

- [x] **Step 1: Write the failing tests**

Create `tests/test_federate_combine.py`:

```python
"""Combine-laget (fase 1): eksakt pooling + null-forgiftning."""
import numpy as np
import pandas as pd
import pytest
from m2py_runtime import federate, pandas_ops as ops


def _nodes_tab():
    a = {"kind": "tabulate", "keys": ["grp"], "dropped": [],
         "records": [{"grp": 1, "n": 6}, {"grp": 2, "n": 3}]}
    b = {"kind": "tabulate", "keys": ["grp"], "dropped": [],
         "records": [{"grp": 1, "n": 4}, {"grp": 3, "n": 8}]}
    return [{"member": "nord", "stats": [a]}, {"member": "vest", "stats": [b]}]


def test_combine_tabulate_sums_and_treats_absent_as_zero():
    out = federate.combine_stats(_nodes_tab())
    f = out[0]["frame"].set_index("grp")["n"]
    assert f[1] == 10 and f[2] == 3 and f[3] == 8


def test_combine_tabulate_null_poisons_cell():
    nodes = _nodes_tab()
    nodes[1]["stats"][0]["records"][0]["n"] = None   # vest grp=1 suppressed
    out = federate.combine_stats(nodes)
    f = out[0]["frame"].set_index("grp")["n"]
    assert pd.isna(f[1]) and f[2] == 3


def test_combine_summarize_matches_pooled_run():
    rng = np.random.default_rng(7)
    df = pd.DataFrame({"inntekt": rng.normal(500, 50, 90),
                       "grp": rng.integers(1, 4, 90)})
    parts = [df.iloc[:30], df.iloc[30:55], df.iloc[55:]]
    per_node = []
    for i, part in enumerate(parts):
        ns = {"result_1": ops.summarize(part, vars=["inntekt"], by=["grp"])}
        per_node.append({"member": f"m{i}", "stats": federate.extract_stats(ns, None)})
    combined = federate.combine_stats(per_node)[0]["frame"]
    pooled = ops.summarize(df, vars=["inntekt"], by=["grp"])
    got = combined.sort_values("grp").reset_index(drop=True)
    want = pooled.sort_values("grp").reset_index(drop=True)
    for col in ("count", "mean", "std", "min", "max"):
        assert np.allclose(got[col].to_numpy(dtype=float),
                           want[col].to_numpy(dtype=float)), col


def test_combine_refusal_names_member():
    nodes = _nodes_tab()
    nodes[1]["stats"][0] = {"kind": "refused", "reason": "for spredt"}
    out = federate.combine_stats(nodes)
    assert out[0]["kind"] == "refused"
    assert "vest" in out[0]["reason"]
```

- [x] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_federate_combine.py -q`
Expected: FAIL — `AttributeError: ... 'combine_stats'`.

- [x] **Step 3: Implement**

Append to `m2py_runtime/federate.py`:

```python
def _merge_cells(per_node_frames, keys, on_row):
    """Ytre justering på keys; on_row(list_of_row_or_None) -> dict av verdier.
    Fravær = raden finnes ikke hos noden (0-bidrag); None-verdi = undertrykt."""
    import pandas as pd
    keysets = []
    for f in per_node_frames:
        for rec in f:
            kv = tuple(rec[k] for k in keys)
            if kv not in keysets:
                keysets.append(kv)
    rows = []
    for kv in keysets:
        matches = []
        for f in per_node_frames:
            m = next((rec for rec in f if tuple(rec[k] for k in keys) == kv), None)
            matches.append(m)
        rows.append(dict(zip(keys, kv), **on_row(matches)))
    return pd.DataFrame(rows)


def _sum_or_none(vals):
    """Sum der fravær=0 og None (undertrykt) forgifter (spec §5)."""
    total = 0
    for v in vals:
        if v is None:
            continue
        if v.get("_suppressed"):
            return None
        total += v["v"]
    return total


def _combine_tabulate(stats):
    frames = [s["records"] for s in stats]
    keys = stats[0]["keys"]

    def on_row(matches):
        acc = 0
        for m in matches:
            if m is None:
                continue            # fravær = 0
            if m["n"] is None:
                return {"n": None}  # undertrykt et sted -> undertrykt
            acc += m["n"]
        return {"n": acc}
    return {"kind": "tabulate", "frame": _merge_cells(frames, keys, on_row)}


def _combine_summarize(stats):
    keys = stats[0]["keys"]
    have_minmax = all(("min" in (s["records"][0] if s["records"] else {}))
                      for s in stats)

    def on_row(matches):
        parts = [m for m in matches if m is not None]
        if any(m["count"] is None or m["mean"] is None for m in parts):
            out = {c: None for c in ("count", "mean", "std")}
            if have_minmax:
                out.update({"min": None, "max": None})
            return out
        n = sum(m["count"] for m in parts)
        mean = sum(m["count"] * m["mean"] for m in parts) / n if n else None
        ss = 0.0
        std = None
        if all(m.get("std") is not None for m in parts) and n > 1:
            for m in parts:
                c, mu, s = m["count"], m["mean"], m["std"]
                ss += (c - 1) * s * s + c * mu * mu
            var = (ss - n * mean * mean) / (n - 1)
            std = math.sqrt(max(var, 0.0))
        out = {"count": n, "mean": mean, "std": std}
        if have_minmax:
            mins = [m["min"] for m in parts]
            maxs = [m["max"] for m in parts]
            out["min"] = None if any(v is None for v in mins) else min(mins)
            out["max"] = None if any(v is None for v in maxs) else max(maxs)
        return out
    return {"kind": "summarize",
            "frame": _merge_cells([s["records"] for s in stats], keys, on_row)}


def combine_stats(per_node):
    """per_node: [{member, stats}] -> posisjonsvis kombinerte resultater."""
    n_res = len(per_node[0]["stats"]) if per_node else 0
    out = []
    for i in range(n_res):
        column = [(node["member"], node["stats"][i]) for node in per_node]
        bad = next(((m, s) for m, s in column
                    if s["kind"] in ("refused", "unsupported")), None)
        if bad:
            out.append({"kind": bad[1]["kind"],
                        "reason": "medlem «" + bad[0] + "»: " + bad[1]["reason"]})
            continue
        kinds = {s["kind"] for _, s in column}
        if len(kinds) != 1:
            out.append({"kind": "refused", "reason":
                        "medlemmene returnerte ulike resultattyper (" +
                        ", ".join(sorted(kinds)) + ") for samme setning"})
            continue
        kind = kinds.pop()
        stats = [s for _, s in column]
        if kind == "tabulate":
            out.append(_combine_tabulate(stats))
        elif kind == "summarize":
            out.append(_combine_summarize(stats))
        elif kind == "regress":
            out.append(_combine_regress(stats))   # Task 4
        else:
            out.append({"kind": "unsupported", "reason":
                        "ukjent statistikk-type «" + kind + "»"})
    return out
```

(Remove the `_sum_or_none` helper if unused after wiring — `_combine_tabulate` inlines the rule.) Add a stub so Task 3 tests run before Task 4:

```python
def _combine_regress(stats):
    return {"kind": "unsupported", "reason": "regress-kombinering kommer i Task 4"}
```

- [x] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_federate_combine.py tests/test_federate_stats.py -q` → all pass.

- [x] **Step 5: Commit**

```bash
git add m2py_runtime/federate.py tests/test_federate_combine.py
git commit -m "feat(federert): exact combine for tabulate and summarize with null-poisoning"
```

---

### Task 4: `_combine_regress` + `combine_and_render`

**Files:**
- Modify: `m2py_runtime/federate.py` (replace the `_combine_regress` stub; add rendering)
- Test: `tests/test_federate_combine.py` (extend)

**Interfaces:**
- Consumes: regress payloads `{terms, xtx, xty, yty, n}` (Task 2), combined results (Task 3).
- Produces:
  - `_combine_regress(stats)` → `{"kind": "regress", "frame": DataFrame[term, coef, se, t, p]}` — pooled OLS from summed sufficient statistics; identical to running `ops.regress` on the pooled data (t-dist p via scipy when importable, else normal approx).
  - `combine_and_render(per_node, members=None, overlap=None)` → dict in the exact shape `renderSafeStatResult` (index.html) consumes: `{"code": "", "out": "", "html": "", "n": None, "err": None|str, "figs": [], "results": [html...], "datasetInfo": {}}`. `results[0]` is a note div naming members (+ per-member total n for the first tabulate stat, where visible) and the overlap footnote when `overlap == "possible"`. Refused/unsupported positions render as `<pre class="error">`.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_federate_combine.py`:

```python
def _regress_nodes():
    rng = np.random.default_rng(3)
    x = rng.normal(size=60)
    df = pd.DataFrame({"y": 1 + 2 * x + rng.normal(scale=0.5, size=60), "x": x})
    parts = [df.iloc[:20], df.iloc[20:45], df.iloc[45:]]
    ops.set_federated(True)
    try:
        per_node = []
        for i, part in enumerate(parts):
            ns = {"result_1": ops.regress(part, "y", ["x"])}
            per_node.append({"member": f"m{i}",
                             "stats": federate.extract_stats(ns, None)})
    finally:
        ops.set_federated(False)
    return df, per_node


def test_combine_regress_matches_pooled_ols():
    df, per_node = _regress_nodes()
    combined = federate.combine_stats(per_node)[0]
    assert combined["kind"] == "regress"
    pooled = ops.regress(df, "y", ["x"])
    got = combined["frame"].set_index("term")
    want = pooled.set_index("term")
    for col in ("coef", "se", "t", "p"):
        assert np.allclose(got[col].to_numpy(dtype=float),
                           want[col].to_numpy(dtype=float), atol=1e-6), col


def test_combine_and_render_shape_and_notes():
    _, per_node = _regress_nodes()
    res = federate.combine_and_render(per_node, members=["m0", "m1", "m2"],
                                      overlap="possible")
    assert set(res) >= {"code", "out", "html", "n", "err", "figs", "results",
                        "datasetInfo"}
    assert res["err"] is None
    assert "m0" in res["results"][0] and "overlappe" in res["results"][0]
    assert "<table" in res["results"][1]


def test_combine_and_render_refusal_is_error_block():
    nodes = [{"member": "a", "stats": [{"kind": "refused", "reason": "for spredt"}]}]
    res = federate.combine_and_render(nodes)
    assert "error" in res["results"][1] and "for spredt" in res["results"][1]
```

- [x] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_federate_combine.py -q`
Expected: new tests FAIL (stub returns unsupported / combine_and_render missing).

- [x] **Step 3: Implement**

Replace the `_combine_regress` stub and append rendering in `m2py_runtime/federate.py`:

```python
def _combine_regress(stats):
    import numpy as np
    import pandas as pd
    terms = stats[0]["terms"]
    if any(s["terms"] != terms for s in stats):
        return {"kind": "refused", "reason":
                "medlemmene har ulike regresjonstermer — samme modellspesifikasjon "
                "kreves hos alle"}
    xtx = sum(np.asarray(s["xtx"], dtype=float) for s in stats)
    xty = sum(np.asarray(s["xty"], dtype=float) for s in stats)
    yty = sum(float(s["yty"]) for s in stats)
    n = sum(int(s["n"]) for s in stats)
    p = len(terms)
    try:
        xtx_inv = np.linalg.inv(xtx)
    except np.linalg.LinAlgError:
        return {"kind": "refused", "reason":
                "kombinert designmatrise er singulær — modellen kan ikke poolgjøres"}
    beta = xtx_inv @ xty
    dof = n - p
    sigma2 = max(yty - beta @ xty, 0.0) / dof if dof > 0 else float("nan")
    se = np.sqrt(np.maximum(np.diag(xtx_inv) * sigma2, 0.0))
    with np.errstate(divide="ignore", invalid="ignore"):
        t = beta / se
    try:
        from scipy import stats as _st
        pvals = 2 * _st.t.sf(np.abs(t), dof)
    except Exception:
        pvals = np.array([math.erfc(abs(tv) / math.sqrt(2)) for tv in t])
    return {"kind": "regress", "frame": pd.DataFrame(
        {"term": terms, "coef": beta, "se": se, "t": t, "p": pvals})}


def _render_frame(frame):
    idx = getattr(frame.index, "name", None) is not None
    return frame.round(4).to_html(border=0, classes="output-table", index=idx)


def _member_totals(per_node):
    """Per-medlem total-n fra første tabulate-stat, der synlig ('—' ellers)."""
    out = []
    for node in per_node:
        tab = next((s for s in node["stats"] if s.get("kind") == "tabulate"), None)
        if tab is None:
            out.append((node["member"], None))
            continue
        vals = [r["n"] for r in tab["records"]]
        out.append((node["member"],
                    None if any(v is None for v in vals) else sum(vals)))
    return out


def combine_and_render(per_node, members=None, overlap=None):
    """N noders stats -> renderSafeStatResult-formet dict (index.html)."""
    members = members or [node["member"] for node in per_node]
    combined = combine_stats(per_node)
    totals = _member_totals(per_node)
    note = ("<div class=\"fed-note\" style=\"opacity:.75;margin-bottom:6px\">"
            "Federert: kombinert fra " + str(len(members)) + " medlemmer (" +
            ", ".join(m + (" n=" + str(t) if t is not None else "")
                      for m, t in totals) + ").")
    if overlap == "possible":
        note += (" NB: medlemmer kan overlappe — tellinger er episodenivå.")
    note += "</div>"
    results = [note]
    for c in combined:
        if c["kind"] in ("refused", "unsupported"):
            results.append("<pre class=\"error\">" + c["reason"] + "</pre>")
        else:
            results.append(_render_frame(c["frame"]))
    return {"code": "", "out": "", "html": "", "n": None, "err": None,
            "figs": [], "results": results, "datasetInfo": {}}
```

- [x] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_federate_combine.py -q` → all pass. Full suite green.

- [x] **Step 5: Commit**

```bash
git add m2py_runtime/federate.py tests/test_federate_combine.py
git commit -m "feat(federert): pooled OLS combine and renderer-shaped output"
```

---

### Task 5: `run_remote` / `run_remote_from_sources` federated mode

**Files:**
- Modify: `m2py_remote.py` (`run_remote` signature line ~79; `run_remote_from_sources` line ~170)
- Test: `tests/test_run_remote_from_sources.py` (extend)

**Interfaces:**
- Consumes: `federate.extract_stats` (Task 2), `pandas_ops.set_federated` (Task 1).
- Produces: `run_remote(script, *, datasets, backend="pandas", policy=None, raw=False, federated=False)` and `run_remote_from_sources(script, sources, *, backend="pandas", raw=False, federated=False)` — when `federated=True`, the result dict additionally carries `"stats": [...]` (Task 2 shape). Task 7's dev node and the Anvil server pass `federated` straight through.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_run_remote_from_sources.py`:

```python
def test_federated_returns_stats_and_split_equals_pooled(tmp_path):
    df = pd.DataFrame({"grp": [1] * 6 + [2] * 5 + [3] * 7})
    a, b = df.iloc[:9], df.iloc[9:]
    pa, pb = tmp_path / "a.csv", tmp_path / "b.csv"
    a.to_csv(pa, index=False); b.to_csv(pb, index=False)
    from m2py_runtime import federate
    per_node = []
    for name, path in (("nord", pa), ("vest", pb)):
        res = run_remote_from_sources(
            "create-dataset demo\ntabulate grp",
            [{"alias": "demo", "location": str(path), "level": "public"}],
            federated=True)
        assert res["err"] is None and res["stats"]
        per_node.append({"member": name, "stats": res["stats"]})
    combined = federate.combine_stats(per_node)[0]["frame"].set_index("grp")["n"]
    assert combined[1] == 6 and combined[2] == 5 and combined[3] == 7


def test_federated_protected_stats_are_suppressed(tmp_path):
    p = tmp_path / "demo.csv"
    pd.DataFrame({"grp": [1] * 6 + [9] * 3}).to_csv(p, index=False)
    res = run_remote_from_sources(
        "create-dataset demo\ntabulate grp",
        [{"alias": "demo", "location": str(p), "level": "protected"}],
        federated=True)
    by = {r["grp"]: r["n"] for r in res["stats"][0]["records"]}
    assert by[9] is None and by[1] == 10
```

- [x] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_run_remote_from_sources.py -q`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'federated'`.

- [x] **Step 3: Implement**

In `m2py_remote.py`: change both signatures to accept `federated=False` and pass it through. In `run_remote`, around the exec block (line ~123-136), set the flag alongside the release spec:

```python
    _ops.set_release_spec((policy or {}).get("post_suppress"))
    _ops.set_federated(federated)
```

and in the `finally`:

```python
        _ops.set_release_spec(None)
        _ops.set_federated(False)
```

At the end of `run_remote`, before `return`, add:

```python
    out = {"code": code, "out": buf.getvalue(), "html": html,
           "n": (None if df is None else int(len(df))),
           "err": err, "figs": figs, "results": results,
           "datasetInfo": _dataset_info(ns)}
    if federated:
        from m2py_runtime.federate import extract_stats
        out["stats"] = extract_stats(ns, spec)
    return out
```

(Refactor the existing `return {...}` into this `out` variable.) `run_remote_from_sources` just forwards: `return run_remote(script, datasets=datasets, backend=backend, policy=policy, raw=raw, federated=federated)`.

- [x] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_run_remote_from_sources.py -q` → all pass. Full suite green.

- [x] **Step 5: Commit**

```bash
git add m2py_remote.py tests/test_run_remote_from_sources.py
git commit -m "feat(federert): run_remote federated mode returns combineable stats"
```

---

### Task 6: `Federate.runNodes` — browser fan-out/poll orchestration

**Files:**
- Modify: `js/federate.js`
- Test: `tests/js/federate.test.js` (extend)

**Interfaces:**
- Consumes: nothing new (pure orchestration; injected fetch).
- Produces: `Federate.runNodes(nodes, opts)` → Promise of `[{id, result}]` in input order. `nodes: [{id, api, body, headers?}]`; `opts: {fetchImpl?, pollMs? (default 1500), maxPolls? (default 80)}`. Per node: POST `api + '/_/api/run_extended'` with JSON body → `{task_id}` → poll GET `api + '/_/api/run_extended_status?task_id=...'` until `status === 'completed'` (resolve `st.result`) or `'failed'`/HTTP error/poll exhaustion (reject with Norwegian error naming the member). ANY node failure rejects the whole promise (spec §5 fail-the-run).

- [x] **Step 1: Write the failing tests**

Append to `tests/js/federate.test.js`:

```js
function nodeFetch(behavior) {
  // behavior: {id: {polls: N, result: {...}} | {fail: msg}}
  const polls = {};
  return async (url, init) => {
    const m = url.match(/^https:\/\/(\w+)\.no/);
    const id = m[1];
    const b = behavior[id];
    if (url.indexOf('run_extended_status') >= 0) {
      polls[id] = (polls[id] || 0) + 1;
      if (b.fail) return { ok: true, json: async () => ({ status: 'failed', error: b.fail }) };
      const done = polls[id] >= (b.polls || 1);
      return { ok: true, json: async () => (done ? { status: 'completed', result: b.result } : { status: 'running' }) };
    }
    return { ok: true, json: async () => ({ task_id: 't_' + id }) };
  };
}

test('runNodes: samler resultater i inputrekkefølge', async () => {
  const res = await F.runNodes(
    [{ id: 'nord', api: 'https://nord.no', body: { x: 1 } },
     { id: 'vest', api: 'https://vest.no', body: { x: 2 } }],
    { fetchImpl: nodeFetch({ nord: { polls: 2, result: { stats: ['a'] } },
                             vest: { polls: 1, result: { stats: ['b'] } } }),
      pollMs: 1 });
  assert.deepEqual(res.map(r => r.id), ['nord', 'vest']);
  assert.deepEqual(res[0].result.stats, ['a']);
});

test('runNodes: én node feiler -> hele kjøringen feiler med medlemsnavn', async () => {
  await assert.rejects(
    F.runNodes(
      [{ id: 'nord', api: 'https://nord.no', body: {} },
       { id: 'vest', api: 'https://vest.no', body: {} }],
      { fetchImpl: nodeFetch({ nord: { polls: 1, result: {} },
                               vest: { fail: 'kilde nede' } }),
        pollMs: 1 }),
    /«vest».*kilde nede/);
});
```

- [x] **Step 2: Run to verify failure**

Run: `node --test tests/js/federate.test.js`
Expected: FAIL — `F.runNodes is not a function`.

- [x] **Step 3: Implement**

Append to `js/federate.js` (inside the IIFE, before the export line; extend the export):

```js
  // Fase 1 (spec §5): fan-out av run_extended til N noder + polling. Ren
  // orkestrering — fetch injiseres (tester bruker fake; index.html ekte).
  function runNodes(nodes, opts) {
    opts = opts || {};
    var fetchImpl = opts.fetchImpl || (typeof fetch !== 'undefined' ? fetch.bind(global) : null);
    var pollMs = opts.pollMs || 1500;
    var maxPolls = opts.maxPolls || 80;
    function runOne(node) {
      var headers = Object.assign({ 'Content-Type': 'application/json' }, node.headers || {});
      return fetchImpl(node.api + '/_/api/run_extended', {
        method: 'POST', headers: headers, body: JSON.stringify(node.body)
      }).then(function (r) {
        if (!r.ok) throw new Error('federert medlem «' + node.id + '»: HTTP ' + r.status);
        return r.json();
      }).then(function (sub) {
        if (!sub || !sub.task_id) throw new Error('federert medlem «' + node.id + '»: ' + ((sub && sub.error) || 'uventet svar'));
        var polls = 0;
        function poll() {
          if (polls++ >= maxPolls) throw new Error('federert medlem «' + node.id + '»: tidsavbrudd');
          return new Promise(function (res) { setTimeout(res, pollMs); }).then(function () {
            return fetchImpl(node.api + '/_/api/run_extended_status?task_id=' + encodeURIComponent(sub.task_id),
              { headers: node.headers || {} });
          }).then(function (r) { return r.json(); }).then(function (st) {
            if (st && st.status === 'completed') return st.result;
            if (st && st.status === 'failed') throw new Error('federert medlem «' + node.id + '»: ' + (st.error || 'kjøring feilet'));
            return poll();
          });
        }
        return poll();
      }).then(function (result) { return { id: node.id, result: result }; });
    }
    return Promise.all(nodes.map(runOne));
  }
```

Export: `global.Federate = { planUnion: planUnion, checkSchemas: checkSchemas, runNodes: runNodes };`

- [x] **Step 4: Run tests**

Run: `node --test tests/js/*.test.js` → all pass.

- [x] **Step 5: Commit**

```bash
git add js/federate.js tests/js/federate.test.js
git commit -m "feat(federert): runNodes fan-out and poll orchestration"
```

---

### Task 7: Dev node server + registry entry

**Files:**
- Create: `scripts/dev_federert_node.py`
- Modify: `data/data-sources.json` (append `demo-federert-node`)

**Interfaces:**
- Consumes: `run_remote_from_sources(..., federated=True)` (Task 5).
- Produces: `python3 scripts/dev_federert_node.py --port 9301 --source person=static_data/federert/nord/person.parquet [--level public]` — an HTTP node implementing POST `/_/api/run_extended` (body `{script, sources: [{alias, source_id}], federated}` → `{task_id}`, runs synchronously) and GET `/_/api/run_extended_status?task_id=...` (→ `{status: 'completed', result}`), with permissive CORS (`Access-Control-Allow-Origin: *`, OPTIONS preflight OK). Registry entry members carry `{id, tier: "node", api, source}` — Task 8's browser wiring reads exactly these fields.

- [x] **Step 1: Write the dev node**

Create `scripts/dev_federert_node.py`:

```python
"""Lokal federert node for utvikling/smoke (fase 1, spec 2026-07-29 §5/§7).

Implements just enough of the Anvil run_extended protocol for the browser
fan-out: synchronous run at submit time, one-shot status poll. NOT a
production node — no auth, permissive CORS, meant for localhost only.

  python3 scripts/dev_federert_node.py --port 9301 \
      --source person=static_data/federert/nord/person.parquet [--level public]
"""
import argparse
import json
import pathlib
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from m2py_remote import run_remote_from_sources  # noqa: E402

TASKS = {}
SOURCES = {}
LEVEL = "public"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_POST(self):
        if not self.path.startswith("/_/api/run_extended"):
            return self._send(404, {"error": "ukjent endepunkt"})
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        sources = []
        for s in req.get("sources", []):
            loc = SOURCES.get(s.get("source_id"))
            if not loc:
                return self._send(200, {"error": "ukjent kilde «%s» på denne noden"
                                        % s.get("source_id")})
            sources.append({"alias": s["alias"], "location": loc, "level": LEVEL})
        task_id = uuid.uuid4().hex
        try:
            TASKS[task_id] = {"status": "completed",
                              "result": run_remote_from_sources(
                                  req["script"], sources,
                                  federated=bool(req.get("federated")))}
        except Exception as exc:
            TASKS[task_id] = {"status": "failed", "error": repr(exc)}
        self._send(200, {"task_id": task_id})

    def do_GET(self):
        if not self.path.startswith("/_/api/run_extended_status"):
            return self._send(404, {"error": "ukjent endepunkt"})
        task_id = self.path.split("task_id=", 1)[-1].split("&")[0]
        self._send(200, TASKS.get(task_id, {"status": "failed",
                                            "error": "ukjent task_id"}))

    def log_message(self, fmt, *args):
        print("[node:%s] %s" % (self.server.server_address[1], fmt % args))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--source", action="append", required=True,
                    metavar="ID=PATH")
    ap.add_argument("--level", default="public",
                    choices=["public", "protected", "sensitive"])
    args = ap.parse_args()
    global LEVEL
    LEVEL = args.level
    for pair in args.source:
        sid, path = pair.split("=", 1)
        SOURCES[sid] = path
    print(f"federert dev-node på :{args.port} ({', '.join(SOURCES)}, {LEVEL})")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
```

- [x] **Step 2: Verify the node end-to-end from the shell**

```bash
python3 scripts/dev_federert_node.py --port 9301 --source person=static_data/federert/nord/person.parquet &
sleep 1
TASK=$(curl -s -X POST localhost:9301/_/api/run_extended -H 'Content-Type: application/json' \
  -d '{"script":"create-dataset person\ntabulate BEFOLKNING_KJOENN","sources":[{"alias":"person","source_id":"person"}],"federated":true}' | python3 -c "import json,sys; print(json.load(sys.stdin)['task_id'])")
curl -s "localhost:9301/_/api/run_extended_status?task_id=$TASK" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['status'], d['result']['stats'][0]['kind'])"
kill %1
```

Expected: `completed tabulate`.

- [x] **Step 3: Registry entry**

Append to `data/data-sources.json` (same style as `demo-federert`):

```json
{
  "id": "demo-federert-node",
  "navn": "Demo (lokal dev): federert node-kjøring (2 noder)",
  "utgiver": "safestat",
  "tillit": "demo",
  "tilgang": "node",
  "kind": "federated",
  "partition": "horizontal",
  "entity": "unit_id",
  "overlap": "none",
  "members": [
    { "id": "nord", "tier": "node", "api": "http://localhost:9301", "source": "person" },
    { "id": "vest", "tier": "node", "api": "http://localhost:9302", "source": "person" }
  ]
}
```

Validate: `python3 -c "import json; json.load(open('data/data-sources.json')); print('json ok')"`.
Note: `resolve()` in data-directives ignores members without `url` for the pull path — Task 8 verifies pull-loading this entry yields a clear error, not a crash.

- [x] **Step 4: Commit**

```bash
git add scripts/dev_federert_node.py data/data-sources.json
git commit -m "feat(federert): local dev node implementing run_extended protocol"
```

---

### Task 8: Browser wiring — `maybeRunFederatedMicrodata`

**Files:**
- Modify: `index.html` (new function next to `maybeRunRemoteMicrodata` at line ~9660; call inserted where `maybeRunRemoteMicrodata` is dispatched — find with `grep -n "maybeRunRemoteMicrodata(" index.html`)
- Modify: `js/data-directives.js` (`resolveFederatedMember`: node members in the pull path must produce a clear error)
- Test: `tests/js/data-directives-federert.test.js` (extend)

**Interfaces:**
- Consumes: `Federate.runNodes` (Task 6), `deriveSafeStatExecutor(script)` (existing — `{cleanScript, sources: [{alias, source_id}], error}`), `loadPyodideAndM2py()` (existing), `renderSafeStatResult(res)` (existing), registry entry shape from Task 7.
- Produces: in microdata mode, a script whose single `require <target> as <alias>` target is a registry entry with `kind: "federated"` and node members fans out to every member, combines via Pyodide (`m2py_runtime.federate.combine_and_render`), renders. Mixed-target and multi-source scripts refuse with a clear message.

- [x] **Step 1: Pull-path guard test (data-directives)**

Append to `tests/js/data-directives-federert.test.js`:

```js
test('resolve: node-medlemmer (tier node, uten url) nektes i pull-veien', () => {
  const reg = [{ id: 'fed-node', navn: 'N', kind: 'federated',
    members: [{ id: 'nord', tier: 'node', api: 'http://localhost:9301', source: 'person' }] }];
  const items = DD.resolve(DD.parse('# connect fed-node as h\n# load h as df'), reg);
  assert.ok(items[0].error);
  assert.ok(items[0].error.indexOf('node') >= 0);
});
```

Run: `node --test tests/js/data-directives-federert.test.js` → new test FAILS (node member has no `url`; today `mm.url || mm.id` falls back to a registry-id lookup error — assert the message mentions node, which it doesn't yet).

- [x] **Step 2: Implement the guard**

In `js/data-directives.js`, in the registry-compound branch of `resolve()` (the `fedTargets = (srcMaybe.members || []).map(...)` line), map node members to an explicit error instead:

```js
        if (srcMaybe && (srcMaybe.kind === 'federated' || srcMaybe.members)) {
          var nodeMember = (srcMaybe.members || []).find(function (mm) { return mm.tier === 'node'; });
          if (nodeMember) {
            return { alias: l.alias, error: 'kilden «' + conn.target + '» har node-medlemmer — den kjøres federert i microdata-modus (require), ikke via load' };
          }
          fedTargets = (srcMaybe.members || []).map(function (mm) { return { target: mm.url || mm.id, member: mm }; });
          fedMeta = srcMaybe;
        }
```

Wait — this early-return sits inside the map callback for a LOAD line, where `l` is in scope; place it exactly there (it already is: the branch is inside `parsed.loads.map`). Run: `node --test tests/js/*.test.js` → all pass.

- [x] **Step 3: Implement `maybeRunFederatedMicrodata` in index.html**

Add above `maybeRunRemoteMicrodata` (line ~9660):

```js
    // Fase 1 federert (spec 2026-07-29 §5): require-mål som er en federert
    // registerkilde med node-medlemmer -> fan-out til hver node (kun
    // SDC-gatede aggregater kommer tilbake), kombiner i Pyodide, render.
    async function maybeRunFederatedMicrodata(script, ctx) {
      var re = /^\s*require\s+(\S+)\s+as\s+\w+/gim;
      var targets = [], m;
      while ((m = re.exec(script)) !== null) targets.push(m[1]);
      if (!targets.length) return false;
      var registry = [];
      try { registry = await (await fetch('data/data-sources.json')).json(); } catch (e) {}
      function fedEntry(t) {
        var src = registry.find(function (s) { return s.id === t; });
        return (src && (src.kind === 'federated') && (src.members || []).some(function (mm) { return mm.tier === 'node'; })) ? src : null;
      }
      var fedTargets = targets.filter(fedEntry);
      if (!fedTargets.length) return false;
      if (targets.length > 1) {
        outputArea.innerHTML = '<pre class="error">' + t('Federert kjøring støtter ett require-mål per skript (ennå).') + '</pre>';
        return true;
      }
      var entry = fedEntry(fedTargets[0]);
      var derived = await deriveSafeStatExecutor(script);
      if (derived.error) { outputArea.innerHTML = '<pre class="error">' + escapeHtmlOutput(derived.error) + '</pre>'; return true; }
      var alias = derived.sources[0] && derived.sources[0].alias;
      var nodes = entry.members.filter(function (mm) { return mm.tier === 'node'; }).map(function (mm) {
        return { id: mm.id, api: mm.api,
                 body: { script: derived.cleanScript, sources: [{ alias: alias, source_id: mm.source }],
                         backend: 'pandas', federated: true } };
      });
      outputArea.innerHTML = '<div style="padding:8px;opacity:.6">' + t('Federert: kjører på {n} noder…', { n: nodes.length }) + '</div>';
      try {
        var nodeResults = await window.Federate.runNodes(nodes, {});
        var badErr = nodeResults.map(function (r) { return r.result && r.result.err ? ('medlem «' + r.id + '»: ' + r.result.err) : null; }).filter(Boolean);
        if (badErr.length) { outputArea.innerHTML = '<pre class="error">' + escapeHtmlOutput(badErr.join('; ')) + '</pre>'; return true; }
        var payload = nodeResults.map(function (r) { return { member: r.id, stats: (r.result && r.result.stats) || [] }; });
        var py = await loadPyodideAndM2py();
        py.globals.set('__fed_payload', JSON.stringify({ per_node: payload, overlap: entry.overlap || null }));
        var resJson = py.runPython(
          'import json\n' +
          'from m2py_runtime.federate import combine_and_render\n' +
          '_p = json.loads(__fed_payload)\n' +
          'json.dumps(combine_and_render(_p["per_node"], overlap=_p["overlap"]))');
        renderSafeStatResult(JSON.parse(resJson));
      } catch (e) {
        outputArea.innerHTML = '<pre class="error">' + escapeHtmlOutput(String(e && e.message || e)) + '</pre>';
      }
      return true;
    }
```

Then find the dispatch site (`grep -n "maybeRunRemoteMicrodata(" index.html`) and insert immediately before it:

```js
          if (await maybeRunFederatedMicrodata(effectiveScript, _ctx)) { ...same early-return shape as the maybeRunRemoteMicrodata line... }
```

(Copy the exact surrounding statement pattern — whatever the existing call does on `true` (return/skip), mirror it.)

- [x] **Step 4: Static checks + suites**

Run: `node --test tests/js/*.test.js` and `python3 -m pytest tests/ -q` → green.
Run: `node -e "const s=require('fs').readFileSync('index.html','utf8'); console.log('fed fn:', /maybeRunFederatedMicrodata/.test(s))"` → `fed fn: true`.

- [x] **Step 5: Commit**

```bash
git add index.html js/data-directives.js tests/js/data-directives-federert.test.js
git commit -m "feat(federert): browser fan-out to node members with Pyodide combine"
```

---

### Task 9: End-to-end smoke with two local nodes

**Files:** none (verification; fix-forward as own commits). Also: update spec status + this plan's execution log; docs example in `docs/directive-language-examples.md` §14 gains a node-federation paragraph.

- [x] **Step 1: Start two nodes + static server**

```bash
python3 scripts/dev_federert_node.py --port 9301 --source person=static_data/federert/nord/person.parquet &
python3 scripts/dev_federert_node.py --port 9302 --source person=static_data/federert/vest/person.parquet &
python3 -m http.server 8127 --directory . &
```

- [x] **Step 2: Browser smoke (microdata mode, hard reload)**

Open `http://localhost:8127/index.html`, microdata mode, run:

```
require demo-federert-node as person
tabulate BEFOLKNING_KJOENN
```

Expected: one combined tabulate whose per-category counts equal `nord+vest` (verify against `python3 -c "import pandas as pd; print(pd.concat([pd.read_parquet('static_data/federert/nord/person.parquet'), pd.read_parquet('static_data/federert/vest/person.parquet')])['BEFOLKNING_KJOENN'].value_counts())"`), preceded by the fed-note naming both members with n.

- [x] **Step 3: Negative smokes**

(a) Stop node 9302; rerun → error naming «vest», no partial result. (b) Restart 9302 with `--level protected`; rerun → combined counts show rounding/suppression semantics (mixed public+protected nodes). (c) Run `summarize` and `regress` scripts; `boxplot`-style verbs → unsupported message.

- [x] **Step 4: Docs + status, final commit**

Add to `docs/directive-language-examples.md` §14 a "Node-federering (fase 1)" paragraph with the require-script above and one sentence: only aggregates leave each node; supported verbs tabulate/summarize/regress. Update spec Status line to "Phases 0–1 implemented". Tick this plan's checkboxes + execution log. Commit:

```bash
git add docs/
git commit -m "docs(federert): phase 1 executed"
```

---

## Self-review notes

- Spec §5 coverage: per-node SDC before emission (T2, T5), sufficient-stats gate (T2), positional combine with exact rules (T3–T4), browser coordinator + run_extended protocol (T6–T8), fail-on-any-node (T6), annotations incl. per-member n + overlap footnote (T4), verb refusals (T2/T3). Mixed-tier pull+node combine deferred (documented v1 scope cut; spec allows phasing).
- Sync: `m2py_runtime/federate.py` auto-syncs to the Anvil server via `sync_to_api.py`'s `m2py_runtime/*.py` glob (verified line 73–76); no sync changes needed.
- Type consistency: fedstats dict keys identical in T1/T2/T4; stat `kind` strings identical across T2–T5; `runNodes` node/result shapes identical in T6/T8; dev-node protocol (T7) matches `runNodes` (T6) URL paths and status fields.

---

## Execution log (2026-07-29)

All 9 tasks executed on branch `federert-fase1`. Deviations from plan:

- **`maybeRunFederatedMicrodata` does NOT use `deriveSafeStatExecutor`** (plan
  said it would): that helper resolves require-targets against server grants
  and rejects federated registry ids («ukjent kilde»). The dispatch parses
  require-lines itself (target + alias) and strips them for cleanScript.
  Federated scripts follow the extended-DSL shape: `require <id> as <alias>` +
  `create-dataset <alias>` + verbs.
- **`runNodes` wraps network-level fetch failures** so a downed node reports
  «federert medlem 'x': nåes ikke (…)» instead of a bare "Failed to fetch"
  (smoke-found; regression test added).
- **`ensureM2pyRuntime`'s rtMods list** gained `federate`; `M2PY_VERSION`
  bumped to 2026-07-29a (pandas_ops changed).
- Summarize's `by` parameter is a STRING (`by='grp'`), not a list — one plan
  test adjusted.
- E2E smoke (two dev nodes 9301 public + 9302, app on 8127): tabulate combined
  5634/5477 == pooled exact; with 9302 restarted `--level protected`, combined
  showed per-node rounding (5632/5473, vest n=5550) — the documented
  suppress-then-combine semantics; summarize and regress combined across the
  mixed pair; node-down failed the whole run naming the member.
