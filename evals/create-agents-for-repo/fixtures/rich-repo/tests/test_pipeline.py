"""Tests for pipeline transforms."""

import polars as pl
import pytest

from formwork.pipeline import apply_transforms


@pytest.fixture
def sample_df():
    return pl.DataFrame({"name": ["a", "b", "c"], "value": [10, 20, 30], "score": [1.1, 2.2, 3.3]})


def test_rename(sample_df):
    result = apply_transforms(sample_df, [{"type": "rename", "mapping": {"name": "label"}}])
    assert "label" in result.columns
    assert "name" not in result.columns


def test_filter(sample_df):
    result = apply_transforms(sample_df, [{"type": "filter", "column": "value", "threshold": 15}])
    assert len(result) == 2


def test_unknown_transform(sample_df):
    with pytest.raises(ValueError, match="unknown transform"):
        apply_transforms(sample_df, [{"type": "explode"}])


def test_chain(sample_df):
    transforms = [
        {"type": "filter", "column": "value", "threshold": 5},
        {"type": "rename", "mapping": {"name": "id"}},
    ]
    result = apply_transforms(sample_df, transforms)
    assert "id" in result.columns
    assert len(result) == 3
