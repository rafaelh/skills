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

from pathlib import Path
import sys
from typing import Any, cast

from models import ValidationResult
from validate_cli import run_validation_cli
import yaml


def _check_sort(sort: Any, idx: int, errors: list[str]) -> None:
    if not isinstance(sort, list):
        errors.append(f"views[{idx}]: 'sort' must be a list")
        return
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
        _check_sort(sort, idx, errors)


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

    # A missing (or null) 'views' is tolerated for partial / templated bases.
    views: Any = top.get("views")
    if isinstance(views, list):
        for idx, view in enumerate(cast("list[Any]", views)):
            _check_view(view, idx, errors)
    elif views is not None:
        errors.append("'views' must be a list")

    return ValidationResult(valid=not errors, errors=errors)


if __name__ == "__main__":
    sys.exit(
        run_validation_cli(
            sys.argv[1:],
            description=(__doc__ or "").split("\n", 1)[0],
            validate=validate_base,
        )
    )
