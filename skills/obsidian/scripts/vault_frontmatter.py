#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyyaml>=6.0",
# ]
# ///
"""Read and edit YAML frontmatter in Obsidian notes.

Operates on a single note file at a time. Preserves key insertion order on
round-trip. Frontmatter comments are not preserved (rare in Obsidian; the
Properties UI strips them anyway).

Library API:
    read(path) -> (dict, str)               # frontmatter, body
    write(path, fm, body)                   # overwrite the file
    set_key(path, key, value)               # in-place set
    delete_key(path, key)                   # in-place delete
    merge(path, updates)                    # in-place merge

CLI:
    vault_frontmatter.py show NOTE
    vault_frontmatter.py get NOTE KEY
    vault_frontmatter.py set NOTE KEY VALUE [--json]
    vault_frontmatter.py delete NOTE KEY

VALUE without --json is parsed as a YAML scalar (so '3' is int, 'true' is
bool, anything else is a string). With --json, VALUE is parsed as JSON,
which is the safest way to pass lists/dicts on the shell.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, cast

import yaml

PathLike = str | Path
DELIM = "---"


class FrontmatterError(Exception):
    """Raised when a file's frontmatter block is malformed."""


def _split(text: str) -> tuple[str, str]:
    """Return (frontmatter_yaml, body). frontmatter_yaml is "" if absent.

    Frontmatter is the block between two `---` lines at the very start of the
    file. Anything else (a `---` later in the document, text before the first
    `---`) is body.
    """
    if not text.startswith(DELIM + "\n") and text != DELIM + "\n" and text.rstrip("\n") != DELIM:
        # File doesn't open with a delimiter line.
        if not text.startswith(DELIM):
            return "", text
        # Edge case: file is just "---" with no newline.
        if text.strip() == DELIM:
            return "", text

    lines = text.split("\n")
    if not lines or lines[0] != DELIM:
        return "", text

    for i in range(1, len(lines)):
        if lines[i] == DELIM:
            fm_yaml = "\n".join(lines[1:i])
            # Body is everything after the closing delim line. We dropped one
            # trailing newline by splitting on "\n", so reconstruct carefully.
            body = "\n".join(lines[i + 1 :])
            return fm_yaml, body

    raise FrontmatterError("frontmatter block opened with --- but never closed")


def read(path: PathLike) -> tuple[dict[str, Any], str]:
    text = Path(path).read_text(encoding="utf-8")
    fm_yaml, body = _split(text)
    if not fm_yaml.strip():
        return {}, body
    try:
        parsed = yaml.safe_load(fm_yaml)
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"invalid YAML in frontmatter: {exc}") from exc
    if parsed is None:
        return {}, body
    if not isinstance(parsed, dict):
        raise FrontmatterError(f"frontmatter must be a mapping, got {type(parsed).__name__}")
    return cast("dict[str, Any]", parsed), body


def _dump(fm: dict[str, Any]) -> str:
    return yaml.safe_dump(
        fm,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )


def write(path: PathLike, fm: dict[str, Any], body: str) -> None:
    """Overwrite path with fm rendered as frontmatter followed by body.

    If fm is empty, the frontmatter block is stripped.
    """
    path = Path(path)
    if not fm:
        path.write_text(body, encoding="utf-8")
        return
    rendered = _dump(fm).rstrip("\n")
    path.write_text(f"{DELIM}\n{rendered}\n{DELIM}\n{body}", encoding="utf-8")


def set_key(path: PathLike, key: str, value: Any) -> None:
    fm, body = read(path)
    fm[key] = value
    write(path, fm, body)


def delete_key(path: PathLike, key: str) -> None:
    fm, body = read(path)
    fm.pop(key, None)
    write(path, fm, body)


def merge(path: PathLike, updates: dict[str, Any]) -> None:
    fm, body = read(path)
    fm.update(updates)
    write(path, fm, body)


def _parse_value(raw: str, as_json: bool) -> Any:
    if as_json:
        return json.loads(raw)
    return yaml.safe_load(raw)


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_show = sub.add_parser("show", help="print frontmatter as JSON")
    p_show.add_argument("note")

    p_get = sub.add_parser("get", help="print one frontmatter key as JSON")
    p_get.add_argument("note")
    p_get.add_argument("key")

    p_set = sub.add_parser("set", help="set one frontmatter key")
    p_set.add_argument("note")
    p_set.add_argument("key")
    p_set.add_argument("value")
    p_set.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="parse VALUE as JSON (use for lists/dicts/typed values)",
    )

    p_del = sub.add_parser("delete", help="delete one frontmatter key")
    p_del.add_argument("note")
    p_del.add_argument("key")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "show":
            fm, _ = read(args.note)
            print(json.dumps(fm))
        elif args.cmd == "get":
            fm, _ = read(args.note)
            if args.key not in fm:
                print(f"vault_frontmatter: key not found: {args.key}", file=sys.stderr)
                return 1
            print(json.dumps(fm[args.key]))
        elif args.cmd == "set":
            value = _parse_value(args.value, args.as_json)
            set_key(args.note, args.key, value)
        elif args.cmd == "delete":
            delete_key(args.note, args.key)
    except FrontmatterError as exc:
        print(f"vault_frontmatter: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"vault_frontmatter: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
