# Manuell ekvivalenstest: csv-pushdown (trinn B)

Fiksturen `csv_pushdown_ekviv.csv` dekker: NA-tokens (NA, N/A, NULL, tom),
kvotert komma, dato-strenger (skal IKKE bli DATE), True/False (skal bli bool),
æøå. Server repoet lokalt og kjør i **python-modus**:

    # connect http://localhost:8642/tests/manual/csv_pushdown_ekviv.csv as kilde
    # load kilde as a
    import io, pandas as pd
    b = pd.read_csv("tests/manual/csv_pushdown_ekviv.csv")  # pandas-fasit (samme innhold)
    print(a.dtypes.astype(str).tolist() == b.dtypes.astype(str).tolist())
    print(a.astype(str).where(a.notna(), "x").equals(b.astype(str).where(b.notna(), "x")))

Begge skal skrive True (verifisert 2026-07-10: dtyper int64/str/float64/str/
bool/str, identiske verdier og NA-masker). I **r-modus** skal samme
connect+load gi numeric verdi med NA, character dato, logical flagg — uten at
én pyodide-ressurs lastes (sjekk Network-panelet).
