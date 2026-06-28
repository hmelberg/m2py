"""Best-effort variable metadata inference for sources without a schema.

Fills dtype + a nominal/continuous guess + cardinality. Ordinality and code-set
meaning are never inferred (they must be declared). UX/validation only — the
run-time dtype remains authoritative for actual behaviour.
"""

import pandas as pd

_NOMINAL_MAX_CARD = 10


def infer_schema(df):
    out = {}
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_bool_dtype(s):
            dtype = "bool"
        elif pd.api.types.is_integer_dtype(s):
            dtype = "int"
        elif pd.api.types.is_float_dtype(s):
            dtype = "float"
        elif pd.api.types.is_datetime64_any_dtype(s):
            dtype = "date"
        else:
            dtype = "string"
        card = int(s.nunique(dropna=True))
        if dtype in ("int", "float"):
            level = "nominal" if card < _NOMINAL_MAX_CARD else "continuous"
        else:
            level = "nominal"
        out[col] = {"dtype": dtype, "level": level, "cardinality": card}
    return out
