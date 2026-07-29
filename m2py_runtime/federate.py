"""Fase 1 federert (spec 2026-07-29-federated-sources-design §5).

Node side: extract_stats turns the result_* namespace into JSON-safe,
combineable, per-node-SDC-gated statistics. Combine side:
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
