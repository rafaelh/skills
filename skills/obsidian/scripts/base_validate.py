#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyyaml>=6.0",
# ]
# ///
"""Validate an Obsidian .base file (Bases plugin).

Bases is a YAML database-view feature. The format is still evolving, so
this validator checks structural correctness rather than every formula
detail. It catches: missing required fields, wrong types, malformed sort
entries, and bad property maps.

Library API:
    validate_base(path) -> ValidationResult

CLI:
    base_validate.py FILE
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
from typing import Any, cast

import yaml


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list[str])


def _check_view(view: Any, idx: int, errors: list[str]) -> None:
    if not isinstance(view, dict):
        errors.append(f"views[{idx}]: must be a mapping")
        return
    v = cast("dict[str, Any]", view)
    if "type" not in v:
        errors.append(f"views[{idx}]: missing 'type'")
    elif not isinstance(v["type"], str):
        errors.append(f"views[{idx}]: 'type' must be a string")
    if "name" in v and not isinstance(v["name"], str):
        errors.append(f"views[{idx}]: 'name' must be a string")
    if "order" in v and not isinstance(v["order"], list):
        errors.append(f"views[{idx}]: 'order' must be a list")
    sort: Any = v.get("sort")
    if sort is not None:
        if not isinstance(sort, list):
            errors.append(f"views[{idx}]: 'sort' must be a list")
        else:
            for sidx, entry in enumerate(cast("list[Any]", sort)):
                if not isinstance(entry, dict):
                    errors.append(f"views[{idx}].sort[{sidx}]: must be a mapping")
                    continue
                ent = cast("dict[str, Any]", entry)
                if "property" not in ent:
                    errors.append(f"views[{idx}].sort[{sidx}]: missing 'property'")
                direction: Any = ent.get("direction", "ASC")
                if direction not in ("ASC", "DESC"):
                    errors.append(f"views[{idx}].sort[{sidx}]: direction must be ASC or DESC")


def _check_properties(properties: Any, errors: list[str]) -> None:
    if not isinstance(properties, dict):
        errors.append("'properties' must be a mapping")
        return
    props = cast("dict[str, Any]", properties)
    for key, value in props.items():
        if not isinstance(value, dict):
            errors.append(f"properties[{key!r}]: must be a mapping")
            continue
        val = cast("dict[str, Any]", value)
        display: Any = val.get("displayName")
        if display is not None and not isinstance(display, str):
            errors.append(f"properties[{key!r}].displayName must be a string")


def validate_base(path: str | Path) -> ValidationResult:
    errors: list[str] = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        return ValidationResult(False, [f"cannot read file: {exc}"])
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return ValidationResult(False, [f"invalid yaml: {exc}"])

    if data is None:
        return ValidationResult(True, [])

    if not isinstance(data, dict):
        return ValidationResult(False, ["top-level must be a mapping"])

    top = cast("dict[str, Any]", data)
    if "properties" in top:
        _check_properties(top["properties"], errors)

    views: Any = top.get("views")
    if views is None:
        # Missing 'views' is tolerated for partial / templated bases.
        pass
    elif not isinstance(views, list):
        errors.append("'views' must be a list")
    else:
        for idx, view in enumerate(cast("list[Any]", views)):
            _check_view(view, idx, errors)

    return ValidationResult(valid=not errors, errors=errors)


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("file")
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="emit JSON summary on stdout",
    )
    args = parser.parse_args(argv)
    result = validate_base(args.file)
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


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
