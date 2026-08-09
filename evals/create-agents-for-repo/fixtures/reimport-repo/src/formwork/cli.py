"""CLI entry point for formwork."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pipeline import load_config, run
from .sink import dispatch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a data pipeline from config")
    sub = parser.add_subparsers(dest="command")
    run_cmd = sub.add_parser("run", help="Execute a pipeline config")
    run_cmd.add_argument("config", type=Path, help="Path to pipeline YAML config")
    run_cmd.add_argument("--dry-run", action="store_true", help="Validate but don't write output")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1

    config = load_config(args.config)
    df = run(config)

    if args.dry_run:
        print(f"OK: {len(df)} rows, {len(df.columns)} columns")
        return 0

    dispatch(df, config.sink)
    print(f"Written {len(df)} rows to {config.sink['type']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
