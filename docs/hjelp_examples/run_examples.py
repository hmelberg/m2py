#!/usr/bin/env python3
"""Kjører hjelpesidenes strict-eksempler og skriver resultatet til output/.

Hjelpesidene skal vise faktiske resultater, ikke plausible. Dette skriptet er
kilden: hvert eksempel kjøres mot safepy, og teksten det skriver limes rett inn
i <pre class="result"> i hjelp.html. tests/test_hjelp.py sammenligner de to, så
et eksempel som slutter å stemme blir fanget.

Kjør:  .venv/bin/python docs/hjelp_examples/run_examples.py
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from tempfile import mkdtemp

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUTDIR = HERE / "output"


def _load_safepy():
    """safepy bor i vendor/safepy.zip — pakk ut til en temp-mappe og importer."""
    dest = mkdtemp(prefix="safepy-hjelp-")
    with zipfile.ZipFile(REPO / "vendor" / "safepy.zip") as z:
        z.extractall(dest)
    sys.path.insert(0, dest)
    import safepy
    return safepy


def build_frame():
    """Deterministisk demoramme. Frøet er låst — endrer du det, endres hvert
    resultattall i hjelpesidene."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    n = 5000
    return pd.DataFrame({
        "kjonn": rng.choice([1, 2], n),
        "alder": rng.integers(20, 70, n),
        "lonn": rng.normal(520000, 130000, n).round(0),
    })


EXAMPLES = [
    {
        "id": "strict-py-gruppegjennomsnitt",
        "dialect": "pandas",
        "expect_ok": True,
        "code": 'df.groupby("kjonn")["lonn"].mean()',
    },
    {
        "id": "strict-py-avvist-head",
        "dialect": "pandas",
        "expect_ok": False,
        "code": "df.head()",
    },
    {
        "id": "strict-py-avvist-posisjon",
        "dialect": "pandas",
        "expect_ok": False,
        "code": 'df["lonn"][0]',
    },
    {
        "id": "strict-py-avvist-import",
        "dialect": "pandas",
        "expect_ok": False,
        "code": 'import os\ndf.groupby("kjonn")["lonn"].mean()',
    },
    {
        "id": "strict-r-summarise",
        "dialect": "r",
        "expect_ok": True,
        "code": "df |> group_by(kjonn) |> summarise(m = mean(lonn), n = n())",
    },
    {
        "id": "strict-r-avvist-head",
        "dialect": "r",
        "expect_ok": False,
        "code": "head(df)",
    },
    {
        "id": "strict-sql-gruppe",
        "dialect": "duckdb",
        "expect_ok": True,
        "code": "SELECT kjonn, avg(lonn) AS m, count(*) AS n FROM df GROUP BY kjonn",
    },
]


def _format_payload(payload) -> str:
    """Gjør safepy sin payload til noe en leser forstår."""
    if not isinstance(payload, dict):
        return str(payload)
    t = payload.get("type")
    if t == "series":
        lines = [f"{payload.get('index_name', '')}  {payload.get('name', '')}"]
        for k, v in zip(payload["index"], payload["values"]):
            lines.append(f"{k}  {v:,.0f}".replace(",", " "))
        return "\n".join(lines)
    if t == "frame":
        cols = payload["columns"]
        lines = ["  ".join([""] + list(cols))]
        for idx, row in zip(payload["index"], payload["data"]):
            cells = [f"{v:,.0f}".replace(",", " ") if isinstance(v, float) else str(v)
                     for v in row]
            lines.append("  ".join([str(idx)] + cells))
        return "\n".join(lines)
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def run_one(example: dict, df) -> str:
    """Kjør ett eksempel og returner tekstblokken som skal limes inn."""
    safepy = _load_safepy()
    r = safepy.run(example["code"], {"df": df}, "protected",
                   profile="strict", dialect=example["dialect"])
    if r.ok != example["expect_ok"]:
        raise AssertionError(
            f"{example['id']}: forventet ok={example['expect_ok']}, fikk ok={r.ok} "
            f"({r.error!r})")
    if r.ok:
        return _format_payload(r.payload)
    err = r.error
    msg = err.get("message") if isinstance(err, dict) else str(err)
    kind = err.get("kind") if isinstance(err, dict) else "error"
    return f"Avvist ({kind}): {msg}"


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    df = build_frame()
    for ex in EXAMPLES:
        text = run_one(ex, df)
        (OUTDIR / f"{ex['id']}.txt").write_text(text + "\n", encoding="utf-8")
        print(f"  {ex['id']}: {len(text)} tegn")
    print(f"Skrev {len(EXAMPLES)} eksempler til {OUTDIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
