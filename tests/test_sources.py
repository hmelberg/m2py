# tests/test_sources.py
import pandas as pd
import pytest
from m2py_runtime.sources import read_source, scan_source


def test_read_csv_and_parquet(tmp_path):
    df = pd.DataFrame({"id": [1, 2], "x": [10, 20]})
    csv = tmp_path / "d.csv"; df.to_csv(csv, index=False)
    pq = tmp_path / "d.parquet"; df.to_parquet(pq)
    pd.testing.assert_frame_equal(read_source(str(csv)), df)
    pd.testing.assert_frame_equal(read_source(str(pq)), df)


def test_scan_returns_lazyframe(tmp_path):
    import polars as pl
    df = pd.DataFrame({"id": [1, 2]})
    pq = tmp_path / "d.parquet"; df.to_parquet(pq)
    lf = scan_source(str(pq))
    assert isinstance(lf, pl.LazyFrame)
    assert lf.collect().to_pandas()["id"].tolist() == [1, 2]


def test_unsupported_format_names_followon(tmp_path):
    with pytest.raises(NotImplementedError, match="DuckDB"):
        read_source("x.sqlite")
