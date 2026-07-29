"""Split static_data/person.parquet into three disjoint "region" members for
the demo-federert source (spec 2026-07-29-federated-sources-design §7).
Deterministic thirds by row order — rerunning build_static_data.py then this
keeps members in sync with the unsplit table (the equality invariant the
federated union is tested against)."""
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
df = pd.read_parquet(ROOT / "static_data" / "person.parquet")
n = len(df)
cuts = [0, n // 3, 2 * n // 3, n]
for name, a, b in zip(["nord", "vest", "sor"], cuts, cuts[1:]):
    out = ROOT / "static_data" / "federert" / name
    out.mkdir(parents=True, exist_ok=True)
    df.iloc[a:b].to_parquet(out / "person.parquet", index=False)
    print(f"{name}: {b - a} rader")
print(f"totalt: {n} rader")
