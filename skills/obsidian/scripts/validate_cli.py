#!/usr/bin/env python3
# agent-tool: false
"""Command-line front end shared by the .canvas and .base validators.

Both expose `validate(path) -> ValidationResult` and need the same CLI: a
file argument, `--json` for a machine-readable summary, `ok` on stdout
otherwise, and exit 0 when valid / 1 when not. Callers pass their own
`description` so `--help` still names the format being validated.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from models import ValidationResult


def run_validation_cli(
    argv: list[str],
    *,
    description: str,
    validate: Callable[[str], ValidationResult],
) -> int:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("file")
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="emit JSON summary on stdout",
    )
    args = parser.parse_args(argv)
    result = validate(args.file)
    if args.as_json:
        print(
            json.dumps(
                {
                    "file": args.file,
                    "valid": result.valid,
                    "errors": result.errors,
                },
                indent=2,
            )
        )
        return 0 if result.valid else 1
    if result.valid:
        print("ok")
        return 0
    for err in result.errors:
        print(err, file=sys.stderr)
    return 1
