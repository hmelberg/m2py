"""Pure pandas runtime ops.

Each op takes a ``pd.DataFrame`` plus parsed-IR arguments and returns a *new*
frame; none mutate their input or log. Expression and condition evaluation is
delegated to the emulator's own helpers so behaviour matches the in-browser
engine bit-for-bit.

IR argument shapes (from ``m2py.MicroParser.parse_line``):
    generate/replace : args={'target', 'expression'}, condition=str|None
    keep/drop        : args={'mode', 'vars'}, condition=str|None
    recode           : args={'vars', 'rules': ['1=10', ...], 'prefix'}
    collapse/aggregate: args={'targets': [{'stat','src','target'}]}, options={'by'}
    merge            : args=[name, 'on', key]  (resolved by the caller)
    summarize        : args=[var, ...], options={'by'}
"""

import numpy as np
import pandas as pd

from m2py import _py_eval_expr, _py_eval_cond, AGG_STAT_ALIAS


# ── value-producing verbs ────────────────────────────────────────────────────

def _assign(df, target, expression, cond):
    out = df.copy()
    values = _py_eval_expr(out, expression)
    if cond:
        mask = _py_eval_cond(out, cond)
        if target in out.columns:
            out.loc[mask, target] = values[mask]
        else:
            col = pd.Series(np.nan, index=out.index)
            col[mask] = values[mask]
            out[target] = col
    else:
        out[target] = values
    return out


def generate(df, target, expression, cond=None):
    """Add (or, with a condition on an existing column, partially set) a column."""
    return _assign(df, target, expression, cond)


def replace(df, target, expression, cond=None):
    """Overwrite a column's values (only where ``cond`` holds, if given)."""
    return _assign(df, target, expression, cond)


def _parse_recode_rule(rule):
    """'1=10' -> (1.0, 10.0). Numeric where possible, else string."""
    lhs, rhs = rule.split("=", 1)
    return _coerce(lhs.strip()), _coerce(rhs.strip())


def _coerce(tok):
    tok = tok.strip().strip("'\"")
    try:
        f = float(tok)
        return int(f) if f.is_integer() else f
    except ValueError:
        return tok


def recode(df, vars, rules, prefix=None):
    """Map values in each listed column per ``rules`` ('old=new'); unmatched
    values are left unchanged. ``prefix`` writes results to new columns."""
    out = df.copy()
    mapping = dict(_parse_recode_rule(r) for r in rules)
    for v in vars:
        if v not in out.columns:
            continue
        target = f"{prefix}{v}" if prefix else v
        out[target] = out[v].map(lambda x: mapping.get(x, x))
    return out


# ── row/column shaping ───────────────────────────────────────────────────────

def keep(df, vars=None, cond=None):
    out = df
    if vars:
        out = out[[c for c in vars if c in out.columns]]
    if cond:
        mask = _py_eval_cond(out, cond)
        out = out.loc[mask]
    return out.reset_index(drop=True).copy()


def drop(df, vars=None, cond=None):
    out = df
    if vars:
        out = out.drop(columns=[c for c in vars if c in out.columns])
    if cond:
        mask = _py_eval_cond(out, cond)
        out = out.loc[~mask]
    return out.reset_index(drop=True).copy()


# ── aggregation / reshaping ──────────────────────────────────────────────────

def collapse(df, targets, by=None):
    """Replace the frame with one aggregated row per ``by`` group (or one row
    overall when ``by`` is None)."""
    if isinstance(by, str) and by.strip():
        by = by.strip().split()[0]
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


def aggregate(df, targets, by=None):
    """Add group-wise aggregate columns without collapsing rows (groupby
    transform)."""
    out = df.copy()
    for t in targets:
        stat_fn = AGG_STAT_ALIAS.get(t["stat"], t["stat"])
        new_var = t["target"] or t["src"]
        out[new_var] = out.groupby(by)[t["src"]].transform(stat_fn)
    return out


def merge(df, other, on, how="left"):
    """Left-join ``other`` onto ``df`` by key ``on`` (adds the right frame's
    non-key columns)."""
    return pd.merge(df, other, on=on, how=how)


# ── analysis ─────────────────────────────────────────────────────────────────

def summarize(df, vars=None, by=None):
    """Descriptive statistics (count/mean/std/min/max) for numeric ``vars``,
    optionally per ``by`` group. Returns a tidy frame."""
    if not vars:
        vars = [c for c in df.columns
                if c not in ("unit_id", "PERSONID_1")
                and pd.api.types.is_numeric_dtype(df[c])]
    vars = [v for v in vars if v in df.columns and pd.api.types.is_numeric_dtype(df[v])]
    aggs = ["count", "mean", "std", "min", "max"]
    if by and by in df.columns:
        frames = []
        g = df.groupby(by)
        for v in vars:
            s = g[v].agg(aggs)
            s.columns = [f"{v}_{a}" for a in aggs]
            frames.append(s)
        return pd.concat(frames, axis=1).reset_index()
    rows = []
    for v in vars:
        r = {"variable": v}
        r.update({a: df[v].agg(a) for a in aggs})
        rows.append(r)
    return pd.DataFrame(rows)
