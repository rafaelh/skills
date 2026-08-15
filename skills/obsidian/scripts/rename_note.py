#!/usr/bin/env python3
"""Rename or move a note and rewrite inbound wikilinks across the vault.

Library API:
    rename_note(old_path, new_path, dry_run=False) -> RenameResult

CLI:
    rename_note.py OLD NEW [--dry-run]

Both OLD and NEW are filesystem paths (absolute or relative to cwd) that
must live inside the same Obsidian vault. The vault root is auto-discovered
by walking up to find .obsidian/.

What it does
    1. Moves OLD to NEW.
    2. Rewrites every wikilink in every .md file across the vault that
       referred to OLD by bare name (e.g. [[Alpha]] when OLD was Alpha.md).
    3. Rewrites every wikilink that referred to OLD by path
       (e.g. [[notes/Alpha]]) when the path component changed.

What it does NOT do
    - Touch markdown-style links [text](path.md). Coverage in v2.
    - Update embeds in .canvas files. Warns if any are detected.
    - Update plain-text mentions ("the Alpha note") that aren't links.
    - Update Dataview / Tasks / other plugin queries.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import shutil
import sys

from links import rewrite_link_target
from vault import NotInVaultError, iter_canvas, iter_notes, locate_vault, relpath_no_ext


class RenameError(Exception):
    pass


@dataclass
class RenameResult:
    moved: bool
    updated_files: list[Path] = field(default_factory=list[Path])
    canvas_warnings: list[Path] = field(default_factory=list[Path])


def rename_note(
    old_path: str | Path,
    new_path: str | Path,
    dry_run: bool = False,
) -> RenameResult:
    old = Path(old_path).expanduser()
    new = Path(new_path).expanduser()

    if not old.exists():
        raise RenameError(f"source does not exist: {old}")
    if new.exists():
        raise RenameError(f"target already exists: {new}")

    try:
        old_vault = locate_vault(old)
    except NotInVaultError as exc:
        raise RenameError(f"source is not in a vault: {exc}") from exc

    # The new file may not exist yet, so we locate the vault from its parent.
    new_parent = new.parent
    if not new_parent.exists():
        raise RenameError(f"target directory does not exist: {new_parent}")
    try:
        new_vault = locate_vault(new_parent)
    except NotInVaultError as exc:
        raise RenameError(f"target is not in a vault: {exc}") from exc

    if old_vault != new_vault:
        raise RenameError(f"old and new paths are in different vaults: {old_vault} vs {new_vault}")

    vault = old_vault
    old_basename = old.stem
    new_basename = new.stem
    old_relpath = relpath_no_ext(vault, old)
    new_relpath = relpath_no_ext(vault, new.parent / new.name)

    name_changed = old_basename != new_basename
    path_changed = old_relpath != new_relpath

    result = RenameResult(moved=False)

    for md in iter_notes(vault):
        if md.resolve() == old.resolve():
            continue
        original = md.read_text(encoding="utf-8")
        text = original
        if path_changed:
            text = rewrite_link_target(text, old_relpath, new_relpath)
        if name_changed:
            text = rewrite_link_target(text, old_basename, new_basename)
        if text != original:
            result.updated_files.append(md)
            if not dry_run:
                md.write_text(text, encoding="utf-8")

    for canvas in iter_canvas(vault):
        try:
            text = canvas.read_text(encoding="utf-8")
        except OSError:
            continue
        if old_basename in text or old_relpath in text:
            result.canvas_warnings.append(canvas)

    if not dry_run:
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old), str(new))
        result.moved = True

    return result


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("old", help="current note path")
    parser.add_argument("new", help="target note path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report planned changes without modifying files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit JSON summary on stdout",
    )
    args = parser.parse_args(argv)

    try:
        result = rename_note(args.old, args.new, dry_run=args.dry_run)
    except RenameError as exc:
        print(f"rename_note: {exc}", file=sys.stderr)
        return 1

    summary = {
        "moved": result.moved,
        "updated_files": [str(p) for p in result.updated_files],
        "canvas_warnings": [str(p) for p in result.canvas_warnings],
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        action = "would update" if args.dry_run else "updated"
        print(f"{action} {len(result.updated_files)} note(s)")
        for p in result.updated_files:
            print(f"  {p}")
        if result.canvas_warnings:
            print(
                f"warning: {len(result.canvas_warnings)} canvas file(s) "
                f"may reference {args.old}; not auto-rewritten",
                file=sys.stderr,
            )
            for p in result.canvas_warnings:
                print(f"  {p}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
