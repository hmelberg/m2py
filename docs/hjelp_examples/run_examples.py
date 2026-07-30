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
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from tempfile import mkdtemp

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUTDIR = HERE / "output"
NODE_HARNESS = HERE / "run_examples_js.mjs"


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
        # ORDER BY kjonn is load-bearing, not cosmetic: DuckDB's GROUP BY
        # without an explicit order is NOT deterministic — measured ~35/65
        # split in row order over 20 consecutive calls on 2026-07-30, in this
        # very process (not just across engine versions). Without ORDER BY,
        # the help page's SQL example would show a coin flip's worth of row
        # order and the content-anchor test in tests/test_hjelp_examples.py
        # would be flaky. Do not "simplify" this away.
        "code": ("SELECT kjonn, avg(lonn) AS m, count(*) AS n "
                 "FROM df GROUP BY kjonn ORDER BY kjonn"),
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


# ─────────────────────────────────────────────────────────────────────────────
# #microdata (Task 12b): m2py kjørt headless, samme mønster som
# tests/test_if_condition.py — MicroInterpreter med et manuelt datasett,
# _execute_instruction(parser.parse_line(...)), output_log leses ut som tekst.
# Samme demoramme som EXAMPLES over (build_frame(), frø 42) — én kilde til
# tallene på hele siden.
#
# Avsløringskontroll er AV som modul-default (M2PY_DISCLOSURE_CONTROL mangler
# => '0', se m2py.py:1-13) — appen slår den PÅ som standard via hamburger-
# menyen/script-direktivet `// m2py: disclosure-control=on`. Eksemplene under
# slår den PÅ eksplisitt via samme modul-global appen selv styrer, slik at
# reglene som faktisk beskrives i #microdata (populasjonsminimum, liten-
# endring-regelen, pseudonymvern) er de som utløses.
MICRODATA_EXAMPLES = [
    {
        "id": "microdata-generer-og-aggreger",
        "dc": True,
        "lines": [
            "generate lonn_1000 = lonn / 1000",
            "collapse (mean) lonn_1000 -> snittlonn_1000, by(kjonn)",
        ],
    },
    {
        # Min populasjon 1000: "keep if alder > 68" etterlater 109 enheter.
        "id": "microdata-avvist-populasjon",
        "dc": True,
        "lines": ["keep if alder > 68"],
    },
    {
        # Endringer må påvirke >=10 enheter: grensa 933381 er valgt slik at
        # nøyaktig 7 av 5000 rader i denne seede rammen ligger over den.
        "id": "microdata-avvist-liten-endring",
        "dc": True,
        "lines": ["generate hoyeste = 1 if lonn > 933381"],
    },
    {
        # Pseudonym-variabler (navn som slutter på _FNR) kan ikke brukes i
        # generate/replace/sammenligninger — bare som nøkkel i collapse(by)
        # eller merge(on).
        "id": "microdata-avvist-pseudonym",
        "dc": True,
        "lines": [
            "generate BEFOLKNING_MOR_FNR = alder",
            "generate test = BEFOLKNING_MOR_FNR + 1",
        ],
    },
]


def run_microdata_example(example: dict, df) -> str:
    """Kjør en sekvens av microdata-linjer på et fersk MicroInterpreter og
    returner alle output_log-meldingene, strippet for m2py sin faste
    to-mellomrom-innrykk (_log(msg, indent=True))."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    import m2py
    from m2py import MicroInterpreter

    saved = getattr(m2py, "M2PY_DISCLOSURE_CONTROL", None)
    m2py.M2PY_DISCLOSURE_CONTROL = "1" if example.get("dc", True) else "0"
    try:
        it = MicroInterpreter(metadata_path=None)
        it.datasets["testdata"] = df.copy()
        it.active_name = "testdata"
        parts = []
        for line in example["lines"]:
            it.output_log.clear()
            it._execute_instruction(it.parser.parse_line(line))
            parts.extend(str(m).strip() for m in it.output_log if str(m).strip())
        return "\n".join(parts)
    finally:
        if saved is None:
            try:
                del m2py.M2PY_DISCLOSURE_CONTROL
            except AttributeError:
                pass
        else:
            m2py.M2PY_DISCLOSURE_CONTROL = saved


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    df = build_frame()
    for ex in EXAMPLES:
        text = run_one(ex, df)
        (OUTDIR / f"{ex['id']}.txt").write_text(text + "\n", encoding="utf-8")
        print(f"  {ex['id']}: {len(text)} tegn")
    print(f"Skrev {len(EXAMPLES)} eksempler til {OUTDIR}")

    for ex in MICRODATA_EXAMPLES:
        text = run_microdata_example(ex, df)
        (OUTDIR / f"{ex['id']}.txt").write_text(text + "\n", encoding="utf-8")
        print(f"  {ex['id']}: {len(text)} tegn")
    print(f"Skrev {len(MICRODATA_EXAMPLES)} microdata-eksempler til {OUTDIR}")

    node = shutil.which("node")
    if node is None:
        raise SystemExit(
            "node ikke funnet i PATH — kreves for felles-lagre/felles-forklar/"
            "felles-widgets-eksemplene (run_examples_js.mjs)"
        )
    subprocess.run([node, str(NODE_HARNESS)], cwd=REPO, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
