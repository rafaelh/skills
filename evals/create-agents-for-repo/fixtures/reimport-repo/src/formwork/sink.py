"""Output sinks: write transformed data to Parquet or PostgreSQL."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import polars as pl


def write_parquet(df: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)


def write_postgres(df: pl.DataFrame, config: dict[str, Any]) -> None:
    import psycopg

    dsn = os.environ.get("DATABASE_URL", config.get("dsn", ""))
    table = config["table"]
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cols = ", ".join(df.columns)
            placeholders = ", ".join(["%s"] * len(df.columns))
            for row in df.iter_rows():
                cur.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", row)  # noqa: S608
        conn.commit()


def dispatch(df: pl.DataFrame, sink: dict[str, Any]) -> None:
    kind = sink["type"]
    if kind == "parquet":
        write_parquet(df, Path(sink["path"]))
    elif kind == "postgres":
        write_postgres(df, sink)
    else:
        msg = f"unknown sink type: {kind}"
        raise ValueError(msg)
