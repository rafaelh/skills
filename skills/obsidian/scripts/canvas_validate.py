#!/usr/bin/env python3
"""Validate an Obsidian .canvas file (a.k.a. JSON Canvas).

Spec: https://jsoncanvas.org/spec/1.0/

Library API:
    validate_canvas(path) -> ValidationResult

CLI:
    canvas_validate.py FILE          # exits 0 if valid, 1 if invalid
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, cast

from models import ValidationResult
from validate_cli import run_validation_cli

_NODE_REQUIRED = ("id", "type", "x", "y", "width", "height")
_TYPE_REQUIRED_EXTRA = {
    "text": ("text",),
    "file": ("file",),
    "link": ("url",),
    "group": (),
}
# Tuple, not the dict itself: `in` against a dict raises TypeError when a
# malformed node carries an unhashable 'type'.
_NODE_TYPES = tuple(_TYPE_REQUIRED_EXTRA)


def _validate_node(node: Any, idx: int, errors: list[str]) -> str | None:
    """Return the node's id if it is a usable string, else None.

    A None return means the node cannot take part in the duplicate-id and
    edge-reference checks; the reason is already recorded in `errors`.
    """
    if not isinstance(node, dict):
        errors.append(f"nodes[{idx}]: must be an object")
        return None
    n = cast("dict[str, Any]", node)
    errors.extend(
        f"nodes[{idx}]: missing required field {key!r}" for key in _NODE_REQUIRED if key not in n
    )
    node_type = n.get("type")
    if node_type not in _NODE_TYPES:
        errors.append(f"nodes[{idx}]: type must be one of {_NODE_TYPES}, got {node_type!r}")
    else:
        errors.extend(
            f"nodes[{idx}]: type={node_type} requires field {extra!r}"
            for extra in _TYPE_REQUIRED_EXTRA[node_type]
            if extra not in n
        )
    node_id = n.get("id")
    if isinstance(node_id, str):
        return node_id
    if "id" in n:
        errors.append(f"nodes[{idx}]: 'id' must be a string, got {node_id!r}")
    return None


def _validate_edge(edge: Any, idx: int, node_ids: set[str], errors: list[str]) -> None:
    if not isinstance(edge, dict):
        errors.append(f"edges[{idx}]: must be an object")
        return
    e = cast("dict[str, Any]", edge)
    errors.extend(
        f"edges[{idx}]: missing required field {key!r}"
        for key in ("id", "fromNode", "toNode")
        if key not in e
    )
    for ref_field in ("fromNode", "toNode"):
        ref = e.get(ref_field)
        if isinstance(ref, str) and ref not in node_ids:
            errors.append(f"edges[{idx}]: {ref_field}={ref!r} references unknown node")
    for side_field in ("fromSide", "toSide"):
        side = e.get(side_field)
        if side is not None and side not in ("top", "right", "bottom", "left"):
            errors.append(f"edges[{idx}]: {side_field}={side!r} must be top/right/bottom/left")
    for end_field in ("fromEnd", "toEnd"):
        end = e.get(end_field)
        if end is not None and end not in ("none", "arrow"):
            errors.append(f"edges[{idx}]: {end_field}={end!r} must be 'none' or 'arrow'")


def validate_canvas(path: str | Path) -> ValidationResult:
    errors: list[str] = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        return ValidationResult(False, [f"cannot read file: {exc}"])
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return ValidationResult(False, [f"invalid JSON: {exc}"])

    if not isinstance(data, dict):
        return ValidationResult(False, ["top-level must be an object with 'nodes' and 'edges'"])

    top = cast("dict[str, Any]", data)
    nodes: Any = top.get("nodes", [])
    edges: Any = top.get("edges", [])
    if not isinstance(nodes, list):
        errors.append("'nodes' must be an array")
        nodes = []
    if not isinstance(edges, list):
        errors.append("'edges' must be an array")
        edges = []

    node_ids: set[str] = set()
    for idx, node in enumerate(cast("list[Any]", nodes)):
        nid = _validate_node(node, idx, errors)
        if nid is not None:
            if nid in node_ids:
                errors.append(f"nodes[{idx}]: duplicate id {nid!r}")
            node_ids.add(nid)

    for idx, edge in enumerate(cast("list[Any]", edges)):
        _validate_edge(edge, idx, node_ids, errors)

    return ValidationResult(valid=not errors, errors=errors)


if __name__ == "__main__":
    sys.exit(
        run_validation_cli(
            sys.argv[1:],
            description=(__doc__ or "").split("\n", 1)[0],
            validate=validate_canvas,
        )
    )
