"""Pure polars runtime ops (lazy).

Each op takes a ``pl.LazyFrame`` plus parsed-IR arguments and returns a new
``pl.LazyFrame`` — the whole pipeline stays lazy so a single
``.collect(engine="streaming")`` at the end can process larger-than-memory data.
Mirrors :mod:`m2py_runtime.pandas_ops` op-for-op. polars is imported lazily
inside the module so importing this package never fails under Pyodide.

Expression handling goes through :mod:`m2py_runtime.exprcompile`, which raises
``UnsupportedExpr`` for syntax it can't map — callers (the translator) turn that
into an ``UNTRANSLATED`` marker rather than emitting wrong polars.
"""

from .exprcompile import compile_expr, UnsupportedExpr  # noqa: F401

# microdata collapse/summarize stat -> polars Expr method (element of a group agg)
_AGG_METHOD = {
    "mean": "mean", "sum": "sum", "min": "min", "max": "max",
    "count": "count", "median": "median", "std": "std", "sd": "std",
    "var": "var", "first": "first", "last": "last",
}


def _pl():
    import polars as pl
    return pl


def _agg_expr(stat, src, alias):
    pl = _pl()
    method = _AGG_METHOD.get(stat)
    if method is None:
        raise UnsupportedExpr(f"collapse/summarize stat ({stat}) unsupported in polars")
    return getattr(pl.col(src), method)().alias(alias)


# ── value-producing verbs ────────────────────────────────────────────────────

def generate(lf, target, expression, cond=None):
    pl = _pl()
    e = compile_expr(expression)
    if cond:
        c = compile_expr(cond, condition=True)
        existing = lf.collect_schema().names()
        otherwise = pl.col(target) if target in existing else pl.lit(None)
        e = pl.when(c).then(e).otherwise(otherwise)
    return lf.with_columns(e.alias(target))


def replace(lf, target, expression, cond=None):
    return generate(lf, target, expression, cond)


def recode(lf, vars, rules, prefix=None):
    pl = _pl()
    from .pandas_ops import _parse_recode_rule
    mapping = dict(_parse_recode_rule(r) for r in rules)
    old = list(mapping.keys())
    new = list(mapping.values())
    cols = []
    for v in vars:
        target = f"{prefix}{v}" if prefix else v
        cols.append(pl.col(v).replace(old=old, new=new).alias(target))
    return lf.with_columns(cols)


# ── row/column shaping ───────────────────────────────────────────────────────

def keep(lf, vars=None, cond=None):
    if vars:
        lf = lf.select(vars)
    if cond:
        lf = lf.filter(compile_expr(cond, condition=True))
    return lf


def drop(lf, vars=None, cond=None):
    if vars:
        lf = lf.drop(vars)
    if cond:
        lf = lf.filter(~compile_expr(cond, condition=True))
    return lf


# ── aggregation / reshaping ──────────────────────────────────────────────────

def collapse(lf, targets, by=None):
    if isinstance(by, str) and by.strip():
        by = by.strip().split()[0]
    aggs = [_agg_expr(t["stat"], t["src"], t["target"] or t["src"]) for t in targets]
    if not by:
        return lf.select(aggs)
    return lf.group_by(by).agg(aggs)


def aggregate(lf, targets, by=None):
    pl = _pl()
    cols = []
    for t in targets:
        method = _AGG_METHOD.get(t["stat"])
        if method is None:
            raise UnsupportedExpr(f"aggregate stat ({t['stat']}) unsupported in polars")
        new_var = t["target"] or t["src"]
        cols.append(getattr(pl.col(t["src"]), method)().over(by).alias(new_var))
    return lf.with_columns(cols)


def merge(lf, other, on, how="left"):
    # pandas uses how="outer"; polars renamed that to "full" and needs
    # coalesce=True so the join key stays a single column (matching pandas).
    if how == "outer":
        return lf.join(other, on=on, how="full", coalesce=True)
    return lf.join(other, on=on, how=how)


def rename(lf, old, new):
    return lf.rename({old: new})


def destring(lf, vars):
    pl = _pl()
    return lf.with_columns(
        [pl.col(v).cast(pl.Float64, strict=False) for v in vars])


# ── analysis ─────────────────────────────────────────────────────────────────

# ── analysis sinks ────────────────────────────────────────────────────────────
# These are terminal outputs (not part of the lazy transform pipeline), so they
# collect the frame and delegate to the tested pandas implementation, returning
# a pl.DataFrame. Equivalence with the pandas backend is therefore guaranteed;
# the lazy/streaming benefit lives in the transform ops above. regress needs
# pandas+statsmodels regardless.

def _analysis(lf, fn, *a, **kw):
    pl = _pl()
    from . import pandas_ops as pdo
    pdf = lf.collect().to_pandas()
    return pl.from_pandas(getattr(pdo, fn)(pdf, *a, **kw).reset_index(drop=True))


def summarize(lf, vars=None, by=None, gini=False, iqr=False):
    return _analysis(lf, "summarize", vars, by, gini=gini, iqr=iqr)


def tabulate(lf, vars, by=None, missing=False):
    return _analysis(lf, "tabulate", vars, by, missing=missing)


def correlate(lf, vars):
    return _analysis(lf, "correlate", vars)


def regress(lf, dep, indep):
    return _analysis(lf, "regress", dep, indep)
