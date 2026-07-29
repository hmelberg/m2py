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


def _combine_tabulate(stats):
    frames = [s["records"] for s in stats]
    keys = stats[0]["keys"]

    def on_row(matches):
        acc = 0
        for m in matches:
            if m is None:
                continue            # fravær = 0
            if m["n"] is None:
                return {"n": None}  # undertrykt et sted -> undertrykt (spec §5)
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
        std = None
        if all(m.get("std") is not None for m in parts) and n > 1:
            ss = 0.0
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


def _combine_regress(stats):
    return {"kind": "unsupported", "reason": "regress-kombinering kommer i Task 4"}


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
            out.append(_combine_regress(stats))
        else:
            out.append({"kind": "unsupported", "reason":
                        "ukjent statistikk-type «" + kind + "»"})
    return out
