#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyyaml>=6.0",
# ]
# ///
"""List notes in a vault, with optional tag/property/folder filters.

Library API:
    list_notes(vault, tag=None, has_property=None, property_value=None,
               folder=None) -> list[Path]
    list_plugins(vault) -> dict     # {enabled_community, installed_community,
                                       enabled_core}

CLI:
    vault_list.py [--vault PATH]
                  [--tag T]              filter notes that have tag T
                  [--has-property P]     filter notes whose frontmatter has P
                  [--property P=V]       filter where P == V (string compare)
                  [--folder F]           limit to notes under F (relative)
                  [--plugins]            instead of notes, dump plugin status
                  [--json]               JSON output
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, cast

from links import parse_tags
from vault import NotInVaultError, iter_notes, locate_vault
from vault_frontmatter import FrontmatterError, read


def _has_tag(fm: dict[str, Any], body: str, tag: str) -> bool:
    fm_tags: Any = fm.get("tags") or []
    if isinstance(fm_tags, str):
        fm_tags = [fm_tags]
    if tag in fm_tags:
        return True
    return any(t.name == tag for t in parse_tags(body))


def list_notes(
    vault: str | Path,
    *,
    tag: str | None = None,
    has_property: str | None = None,
    property_value: str | None = None,
    folder: str | None = None,
) -> list[Path]:
    vault = Path(vault)
    out: list[Path] = []
    folder_path = (vault / folder).resolve() if folder else None
    for md in iter_notes(vault):
        if folder_path is not None:
            try:
                md.resolve().relative_to(folder_path)
            except ValueError:
                continue
        try:
            fm, body = read(md)
        except FrontmatterError:
            fm, body = {}, md.read_text(encoding="utf-8")
        if tag is not None and not _has_tag(fm, body, tag):
            continue
        if has_property is not None:
            if has_property not in fm:
                continue
            if property_value is not None and str(fm[has_property]) != property_value:
                continue
        out.append(md)
    return out


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return None


def list_plugins(vault: str | Path) -> dict[str, list[str]]:
    vault = Path(vault)
    obs = vault / ".obsidian"

    enabled = _read_json(obs / "community-plugins.json")
    if not isinstance(enabled, list):
        enabled = []

    installed: list[str] = []
    plugins_dir = obs / "plugins"
    if plugins_dir.is_dir():
        installed.extend(
            child.name
            for child in sorted(plugins_dir.iterdir())
            if child.is_dir() and (child / "manifest.json").exists()
        )

    enabled_core: Any = _read_json(obs / "core-plugins.json")
    if not isinstance(enabled_core, list):
        # Newer Obsidian versions use {"id": true/false}
        if isinstance(enabled_core, dict):
            core_dict = cast("dict[str, bool]", enabled_core)
            enabled_core = [k for k, v in core_dict.items() if v]
        else:
            enabled_core = []

    return {
        "enabled_community": [str(x) for x in cast("list[Any]", enabled)],
        "installed_community": installed,
        "enabled_core": [str(x) for x in cast("list[Any]", enabled_core)],
    }


def _resolve_vault(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser().resolve()
    return locate_vault(Path.cwd())


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--vault", help="vault root (default: discover from cwd)")
    parser.add_argument("--tag", help="only notes with this tag")
    parser.add_argument("--has-property", dest="has_property", help="only notes with this property")
    parser.add_argument(
        "--property",
        dest="prop_eq",
        help="only notes where PROPERTY=VALUE (sets --has-property too)",
    )
    parser.add_argument("--folder", help="only notes under this folder")
    parser.add_argument(
        "--plugins",
        action="store_true",
        help="output plugin status JSON instead of note list",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    try:
        vault = _resolve_vault(args.vault)
    except NotInVaultError as exc:
        print(f"vault_list: {exc}", file=sys.stderr)
        return 1

    if args.plugins:
        print(json.dumps(list_plugins(vault), indent=2))
        return 0

    has_property = args.has_property
    property_value = None
    if args.prop_eq:
        if "=" not in args.prop_eq:
            print("vault_list: --property must be KEY=VALUE", file=sys.stderr)
            return 2
        has_property, property_value = args.prop_eq.split("=", 1)

    notes = list_notes(
        vault,
        tag=args.tag,
        has_property=has_property,
        property_value=property_value,
        folder=args.folder,
    )

    if args.json:
        print(json.dumps([str(p) for p in notes]))
    else:
        for p in notes:
            print(p)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
