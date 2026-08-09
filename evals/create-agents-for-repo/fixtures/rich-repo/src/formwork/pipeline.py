"""Pipeline orchestration: load config, apply transforms, write output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl
import yaml


@dataclass
class PipelineConfig:
    source: Path
    transforms: list[dict[str, Any]]
    sink: dict[str, Any]


def load_config(path: Path) -> PipelineConfig:
    with path.open() as f:
        raw = yaml.safe_load(f)
    return PipelineConfig(
        source=Path(raw["source"]),
        transforms=raw.get("transforms", []),
        sink=raw["sink"],
    )


def apply_transforms(df: pl.DataFrame, transforms: list[dict[str, Any]]) -> pl.DataFrame:
    for t in transforms:
        kind = t["type"]
        if kind == "rename":
            df = df.rename(t["mapping"])
        elif kind == "filter":
            df = df.filter(pl.col(t["column"]) > t["threshold"])
        elif kind == "cast":
            df = df.with_columns(pl.col(t["column"]).cast(getattr(pl, t["dtype"])))
        else:
            msg = f"unknown transform type: {kind}"
            raise ValueError(msg)
    return df


def run(config: PipelineConfig) -> pl.DataFrame:
    df = (
        pl.read_csv(config.source)
        if config.source.suffix == ".csv"
        else pl.read_parquet(config.source)
    )
    return apply_transforms(df, config.transforms)
