"""Tests for sink dispatch."""

import polars as pl

from formwork.sink import write_parquet


def test_write_parquet(tmp_path):
    df = pl.DataFrame({"x": [1, 2, 3]})
    out = tmp_path / "out.parquet"
    write_parquet(df, out)
    assert out.exists()
    loaded = pl.read_parquet(out)
    assert len(loaded) == 3
