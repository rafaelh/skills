"""CLI entry point for widgetly."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

from .render import render_widget
from .schema import ValidationError, validate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render SVG widgets from TOML configs")
    parser.add_argument("config", type=Path, help="Path to TOML config file")
    parser.add_argument("-o", "--output", type=Path, help="Output SVG path (default: stdout)")
    args = parser.parse_args(argv)

    if not args.config.exists():
        print(f"error: {args.config} not found", file=sys.stderr)
        return 1

    with args.config.open("rb") as f:
        raw = tomllib.load(f)

    try:
        config = validate(raw)
    except ValidationError as e:
        print(f"validation error: {e}", file=sys.stderr)
        return 1

    svg = render_widget(config)
    if args.output:
        args.output.write_text(svg, encoding="utf-8")
    else:
        print(svg, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
