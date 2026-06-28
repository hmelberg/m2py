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


def rename(df, old, new):
    """Rename column ``old`` to ``new``."""
    return df.rename(columns={old: new})


def destring(df, vars):
    """Coerce string columns to numeric (non-parseable values -> NaN)."""
    out = df.copy()
    for v in vars:
        if v in out.columns:
            out[v] = pd.to_numeric(out[v], errors="coerce")
    return out


# ── analysis ─────────────────────────────────────────────────────────────────

def _numeric_vars(df, vars):
    if not vars:
        vars = [c for c in df.columns if c not in ("unit_id", "PERSONID_1")]
    return [v for v in vars if v in df.columns and pd.api.types.is_numeric_dtype(df[v])]


# Percentiles the emulator reports for an ungrouped summarize (incl. median).
_SUM_PCTLS = [("p1", 0.01), ("p25", 0.25), ("p50", 0.5), ("p75", 0.75), ("p99", 0.99)]


def _extra_stat_cols(s, gini, iqr):
    cols = {}
    if gini:
        cols["gini"] = AGG_STAT_ALIAS["gini"](s)
    if iqr:
        cols["iqr"] = AGG_STAT_ALIAS["iqr"](s)
    return cols


def summarize(df, vars=None, by=None, gini=False, iqr=False):
    """Descriptive statistics for numeric ``vars`` as a tidy long frame, matching
    the emulator's two paths (verified against ``StatsEngine``):

      - ungrouped: ``[variable, mean, std, count, p1, p25, p50, p75, p99]``
        (percentiles incl. the median; no min/max — same as the emulator)
      - grouped (``by``): ``[<by>, variable, mean, std, min, max, count]``
        (no percentiles — same as the emulator)

    ``gini``/``iqr`` (reusing the emulator's ``calculate_gini``/``calculate_iqr``)
    append columns in either path. Analysis result; the dataset is unchanged."""
    vars = _numeric_vars(df, vars)

    if by and by in df.columns:
        recs = []
        for key, sub in df.groupby(by, dropna=False):
            for v in vars:
                s = sub[v]
                r = {by: key, "variable": v, "mean": s.mean(), "std": s.std(),
                     "min": s.min(), "max": s.max(), "count": s.count()}
                r.update(_extra_stat_cols(s, gini, iqr))
                recs.append(r)
        return pd.DataFrame(recs)

    recs = []
    for v in vars:
        s = df[v]
        r = {"variable": v, "mean": s.mean(), "std": s.std(), "count": s.count()}
        r.update({label: s.quantile(q) for label, q in _SUM_PCTLS})
        r.update(_extra_stat_cols(s, gini, iqr))
        recs.append(r)
    return pd.DataFrame(recs)


def _chi2_stats(sub, v1, v2, dropna):
    """(chi2, p, dof) for the v1×v2 contingency of ``sub``; NaN if degenerate."""
    from scipy.stats import chi2_contingency
    ct = pd.crosstab(sub[v1], sub[v2], dropna=dropna)
    if ct.shape[0] < 2 or ct.shape[1] < 2:
        return (np.nan, np.nan, np.nan)
    chi2, p, dof, _ = chi2_contingency(ct)
    return (float(chi2), float(p), float(dof))


def tabulate(df, vars, by=None, missing=False,
             cellpct=False, rowpct=False, colpct=False,
             chi2=False, top=None, bottom=None):
    """Frequency table: counts of each combination of ``vars`` (one-way for a
    single variable, cross-tab for two), optionally within ``by`` groups.

    Missing/null key values are dropped by default, kept when ``missing`` is set.
    Percentage columns (0-100), each computed within the ``by`` group when given:
      - ``cellpct``: share of the whole table
      - ``rowpct``:  share within the first variable (``vars[0]``)
      - ``colpct``:  share within the second variable (``vars[1]``, or the only
        variable for a one-way table)
    ``chi2`` (two-way only) adds constant ``chi2``/``chi2_p``/``chi2_dof`` columns
    (per ``by`` group), using scipy's chi-square test of independence — computed
    on the full table, before any top/bottom row limit.
    ``top``/``bottom`` keep the first/last n categories of the first variable
    (positional, in value-sorted order — same as microdata/the emulator, which
    head/tail the table rows; ``top(n)``; bare ``top`` -> 10). Columns: the
    grouping variables, ``n``, then any extras."""
    keys = ([by] if by and by in df.columns else []) + list(vars)
    out = df.groupby(keys, dropna=not missing).size().reset_index(name="n")
    grp = [by] if by and by in df.columns else []
    first = vars[0]
    second = vars[1] if len(vars) > 1 else vars[0]
    if cellpct:
        denom = out.groupby(grp)["n"].transform("sum") if grp else out["n"].sum()
        out["cellpct"] = 100.0 * out["n"] / denom
    if rowpct:
        out["rowpct"] = 100.0 * out["n"] / out.groupby(grp + [first])["n"].transform("sum")
    if colpct:
        out["colpct"] = 100.0 * out["n"] / out.groupby(grp + [second])["n"].transform("sum")
    if chi2 and len(vars) >= 2:
        if grp:
            stats = {k: _chi2_stats(sub, first, second, not missing)
                     for k, sub in df.groupby(by)}
            for i, col in enumerate(("chi2", "chi2_p", "chi2_dof")):
                out[col] = out[by].map(lambda k, i=i: stats.get(k, (np.nan,) * 3)[i])
        else:
            out["chi2"], out["chi2_p"], out["chi2_dof"] = _chi2_stats(
                df, first, second, not missing)
    if top is not None or bottom is not None:
        from m2py import _parse_count_option
        # positional (emulator/microdata): first/last n categories of the first
        # variable, in value-sorted order (groupby already sorts keys ascending).
        cats = out[first].drop_duplicates()
        n = _parse_count_option(top if top is not None else bottom)
        keep = cats.head(n) if top is not None else cats.tail(n)
        out = out[out[first].isin(keep)].reset_index(drop=True)
    return out


def correlate(df, vars):
    """Pearson correlation matrix for numeric ``vars`` as a frame whose first
    column ``variable`` labels each row."""
    vars = _numeric_vars(df, vars)
    c = df[vars].corr()
    return c.reset_index(names="variable")


# ── plots (terminal; return a plotly Figure) ─────────────────────────────────
# plotly is imported lazily so this module stays importable without it (and
# under Pyodide). Figures are built with plotly express where it matches the
# emulator's trace data, mirroring m2py.PlotHandler so the offline charts equal
# the in-browser ones (verified by comparing trace x/y in the tests).

_BAR_AGG = {"mean": "mean", "median": "median", "sum": "sum",
            "sd": "std", "min": "min", "max": "max"}


def histogram(df, vars, bins=30, discrete=False, percent=False, density=False):
    """Histogram of ``vars[0]``. Numeric -> ``go.Histogram`` (``histnorm`` for
    percent/density); categorical or ``discrete`` -> value-counts bar (as percent
    when requested). Mirrors the emulator."""
    import plotly.express as px
    var = vars[0]
    s = df[var].dropna()
    if discrete or not pd.api.types.is_numeric_dtype(s):
        vc = s.value_counts().sort_index()
        if percent:
            vc = (vc / vc.sum() * 100).round(2)
        return px.bar(x=vc.index.tolist(), y=vc.values.tolist())
    histnorm = "probability density" if density else ("percent" if percent else None)
    return px.histogram(df.dropna(subset=[var]), x=var, nbins=bins, histnorm=histnorm)


def barchart(df, vars, stat="count", over=None):
    """Bar chart of ``vars[0]``. The statistic comes from the parenthesised
    ``(stat)`` form: count/percent -> value counts (one bar per category, or one
    trace per category grouped over ``over``); a numeric stat
    (mean/median/sum/sd/min/max) -> that statistic, by ``over`` group when given.
    Mirrors the emulator's trace construction."""
    import plotly.express as px
    import plotly.graph_objects as go
    var = vars[0]
    if stat in ("count", "percent"):
        as_pct = stat == "percent"
        if over and over in df.columns:
            ct = pd.crosstab(df[over], df[var], dropna=False)
            if as_pct:
                ct = ct.div(ct.sum(axis=1), axis=0).multiply(100).round(1)
            fig = go.Figure()
            for col in ct.columns:
                fig.add_trace(go.Bar(name=str(col), x=ct.index.tolist(), y=ct[col].values))
            fig.update_layout(barmode="group")
            return fig
        s = df[var].value_counts(dropna=False).sort_index()
        if as_pct:
            s = (s / s.sum() * 100).round(1)
        return px.bar(x=s.index.tolist(), y=s.values.tolist())
    agg = _BAR_AGG.get(stat, "mean")
    if over and over in df.columns:
        grp = df.groupby(over, dropna=False)[var].agg(agg)
        return go.Figure(data=[go.Bar(x=grp.index.tolist(), y=grp.values)])
    return go.Figure(data=[go.Bar(x=[var], y=[df[var].agg(agg)])])


def scatter(df, vars, by=None):
    """Scatter of ``vars[0]`` (x) vs ``vars[1]`` (y); one trace per ``by`` group
    (in first-seen order, matching the emulator) when given."""
    import plotly.express as px
    import plotly.graph_objects as go
    x, y = vars[0], vars[1]
    if by and by in df.columns:
        sub = df[[x, y, by]].dropna()
        fig = go.Figure()
        for val in sub[by].unique():
            m = sub[by] == val
            fig.add_trace(go.Scatter(x=sub.loc[m, x], y=sub.loc[m, y],
                                     mode="markers", name=str(val)))
        return fig
    sub = df[[x, y]].dropna()
    return px.scatter(sub, x=x, y=y)


def boxplot(df, vars, over=None):
    """Box plot of ``vars[0]`` (grouped by ``over`` when given), or one box per
    variable when several are listed. Mirrors the emulator."""
    import plotly.express as px
    import plotly.graph_objects as go
    if len(vars) > 1:
        fig = go.Figure()
        for v in vars:
            s = df[v].dropna()
            if not s.empty:
                fig.add_trace(go.Box(y=s, name=v))
        return fig
    var = vars[0]
    if over and over in df.columns:
        return px.box(df[[over, var]], x=over, y=var)
    return px.box(df[[var]], y=var)


def piechart(df, vars, stat="count"):
    """Pie chart of ``vars[0]`` value counts, or percents with the ``(percent)``
    statistic. Mirrors the emulator."""
    import plotly.graph_objects as go
    s = df[vars[0]].value_counts(dropna=False).sort_index()
    if stat == "percent":
        values = (s / s.sum() * 100).round(1).tolist()
    else:
        values = s.values.tolist()
    return go.Figure(data=[go.Pie(labels=s.index.tolist(), values=values, hole=0)])


def hexbin(df, vars, bins=30):
    """2-D density (hexbin-style) of ``vars[0]`` vs ``vars[1]`` via Histogram2d."""
    import plotly.graph_objects as go
    x, y = vars[0], vars[1]
    sub = df[[x, y]].dropna()
    return go.Figure(data=[go.Histogram2d(
        x=sub[x], y=sub[y], nbinsx=bins, nbinsy=bins,
        colorscale="Blues", showscale=True)])


def sankey(df, vars):
    """Sankey diagram of transitions across the listed categorical variables
    (one node per stage+value). Mirrors the emulator's node/link construction."""
    import plotly.graph_objects as go
    vars_list = [v for v in vars if v in df.columns]
    sub = df[vars_list].dropna(how="any")
    stages, stage_idx, offsets = [], [], [0]
    for va in vars_list:
        uniq = sub[va].dropna().unique().tolist()
        stages.append(uniq)
        stage_idx.append({v: offsets[-1] + j for j, v in enumerate(uniq)})
        offsets.append(offsets[-1] + len(uniq))
    labels = [str(v) for uniq in stages for v in uniq]
    src, tgt, val = [], [], []
    for i in range(len(vars_list) - 1):
        va, vb = vars_list[i], vars_list[i + 1]
        grp = sub.groupby([va, vb], dropna=False).size().reset_index(name="count")
        ia, ib = stage_idx[i], stage_idx[i + 1]
        for _, row in grp.iterrows():
            a, b = row[va], row[vb]
            if pd.isna(a) or pd.isna(b):
                continue
            s, t = ia.get(a), ib.get(b)
            if s is not None and t is not None:
                src.append(s)
                tgt.append(t)
                val.append(int(row["count"]))
    return go.Figure(data=[go.Sankey(
        node=dict(label=labels, pad=15, thickness=20),
        link=dict(source=src, target=tgt, value=val))])


def coefplot(df, reg_cmd, dep, indep, standardize=False, noconstant=False):
    """Coefficient plot: fit ``reg_cmd`` (regress/logit/probit/poisson) of ``dep``
    on ``indep`` and plot the non-intercept coefficients (x) against variable
    names (y) with 95% CI error bars. Mirrors the emulator's `_fit_simple`."""
    import statsmodels.api as sm
    import plotly.graph_objects as go
    d = df[[dep] + list(indep)].apply(pd.to_numeric, errors="coerce").dropna().astype(float)
    X = d[list(indep)].copy()
    if standardize:
        for v in indep:
            sd = X[v].std()
            if sd > 0:
                X[v] = (X[v] - X[v].mean()) / sd
    if not noconstant:
        X = sm.add_constant(X, has_constant="add")
    Y = d[dep]
    if reg_cmd == "regress":
        model = sm.OLS(Y, X).fit()
    elif reg_cmd == "logit":
        model = sm.Logit(Y, X).fit(disp=0)
    elif reg_cmd == "probit":
        model = sm.Probit(Y, X).fit(disp=0)
    elif reg_cmd == "poisson":
        model = sm.GLM(Y, X, family=sm.families.Poisson()).fit()
    else:
        raise ValueError(f"coefplot does not support '{reg_cmd}'")
    params = model.params.drop("const", errors="ignore")
    ci = model.conf_int().drop("const", errors="ignore")
    coefs = params.values.tolist()
    lo, hi = ci.iloc[:, 0].tolist(), ci.iloc[:, 1].tolist()
    err_minus = [c - l for c, l in zip(coefs, lo)]
    err_plus = [h - c for c, h in zip(coefs, hi)]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=coefs, y=list(params.index), mode="markers",
        marker=dict(size=9, color="#2563eb"),
        error_x=dict(type="data", symmetric=False, array=err_plus,
                     arrayminus=err_minus, thickness=1.5, width=6)))
    fig.add_vline(x=0, line_dash="dot", line_color="#9ca3af", line_width=1)
    return fig


def regress(df, dep, indep):
    """OLS of ``dep`` on ``indep`` (+ intercept) via statsmodels. Returns a
    coefficient table ``[term, coef, se, t, p]``."""
    import statsmodels.api as sm
    d = df[[dep] + list(indep)].dropna()
    X = sm.add_constant(d[list(indep)], has_constant="add")
    model = sm.OLS(d[dep].astype(float), X.astype(float)).fit()
    return pd.DataFrame({
        "term": model.params.index,
        "coef": model.params.to_numpy(),
        "se": model.bse.to_numpy(),
        "t": model.tvalues.to_numpy(),
        "p": model.pvalues.to_numpy(),
    })
