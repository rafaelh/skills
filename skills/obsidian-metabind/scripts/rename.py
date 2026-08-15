#!/usr/bin/env python3
# /// script
# requires-python = ">=3.14"
# dependencies = [
#   "pyyaml>=6.0",
# ]
# ///
"""Retarget Meta Bind bind targets across a vault after a rename.

--property renames a frontmatter key everywhere it is bound: INPUT and VIEW
bind targets and button `updateMetadata` bindTarget lines alike.

--path rewrites the *file* half of bind targets pointing at a note
(`INPUT[text:other note#select]`). The obsidian skill's rename_note.py fixes
wikilinks but is blind to bind targets, so renaming a note otherwise breaks
every field aimed at it silently. Run this alongside it.

This tool rewrites references only — it never moves or renames a file. Because
it is normally run *after* the note has already moved, --path accepts an OLD
that no longer exists on disk.

It never edits identifiers inside JS. `getMetadata('count')` in a js or
inlineJS action is reported as a site needing manual attention, never
pattern-rewritten: rewriting identifiers inside arbitrary JS eventually
corrupts someone's code.

Output: JSON or a unified diff / summary on stdout.
Exit codes: 0 rewrote (or would rewrite) something, 1 bad invocation,
2 unreadable or unwritable vault, 3 nothing referenced the old name.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict, dataclass
import difflib
import json
from pathlib import Path
import re
import sys
from typing import TYPE_CHECKING, Any, cast

from parser import (
    Declaration,
    NotInVaultError,
    button_actions,
    iter_notes,
    locate_vault,
    parse_note,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from parser import BindTarget

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_SYSTEM_ERROR = 2
EXIT_NOT_FOUND = 3

_IDENT_RE = re.compile(r"^[^\W\d][\w\-$]*$")

#: Button action types whose payload is JS we must never rewrite.
_JS_ACTION_TYPES = frozenset({"js", "inlineJS"})


@dataclass(frozen=True, slots=True)
class Edit:
    """A byte-range replacement within one note."""

    file: Path
    start: int
    end: int
    replacement: str


@dataclass(frozen=True, slots=True)
class Site:
    file: str
    line: int
    column: int
    before: str
    after: str


@dataclass(frozen=True, slots=True)
class ManualSite:
    file: str
    line: int
    column: int
    reason: str


@dataclass(frozen=True, slots=True)
class Plan:
    edits: list[Edit]
    sites: list[Site]
    manual: list[ManualSite]


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def _property_edits(
    target: BindTarget, old: tuple[str, ...], new: tuple[str, ...], file: Path
) -> tuple[list[Edit], str | None]:
    """Edits retargeting `target` from the `old` property prefix to `new`.

    Returns (edits, blocked_reason). A numeric list index inside the matched
    prefix is a position, not a name, so it blocks the rewrite rather than
    silently producing something wrong.
    """
    if target.prop_path[: len(old)] != old:
        return [], None

    edits: list[Edit] = []
    for access, replacement in zip(target.props[: len(old)], new, strict=True):
        if access.kind == "ident":
            edits.append(Edit(file, access.span.start, access.span.end, replacement))
        elif access.kind == "quoted":
            edits.append(Edit(file, access.span.start, access.span.end, f'["{replacement}"]'))
        else:
            return [], (
                f"bind target {target.render()!r} reaches the renamed property through "
                f"list index [{access.name}]; rewrite it by hand"
            )
    return edits, None


def _path_edit(target: BindTarget, old: str, new: str, file: Path) -> Edit | None:
    if target.storage_path is None or target.storage_path_span is None:
        return None
    written = target.storage_path
    if written == old:
        replacement = new
    elif written == Path(old).name:
        replacement = Path(new).name
    else:
        return None
    return Edit(file, target.storage_path_span.start, target.storage_path_span.end, replacement)


def _js_mentions(declaration: Declaration, needle: re.Pattern[str]) -> bool:
    if declaration.js_code and needle.search(declaration.js_code):
        return True
    if not isinstance(declaration.button_config, dict):
        return False
    return any(
        isinstance(action, dict)
        and cast("dict[str, Any]", action).get("type") in _JS_ACTION_TYPES
        and needle.search(json.dumps(action))
        for action in button_actions(declaration.button_config)
    )


def build_plan(
    declarations: Iterable[Declaration],
    *,
    old: str,
    new: str,
    mode: str,
) -> Plan:
    edits: list[Edit] = []
    sites: list[Site] = []
    manual: list[ManualSite] = []
    old_segments = tuple(old.split("."))
    new_segments = tuple(new.split("."))
    old_path = old.removesuffix(".md")
    new_path = new.removesuffix(".md")
    needle = old_segments[0] if mode == "property" else Path(old_path).name
    needle_re = re.compile(rf"\b{re.escape(needle)}\b")

    for declaration in declarations:
        target_edits: list[Edit] = []
        for target in declaration.bind_targets:
            if mode == "property":
                found, blocked = _property_edits(
                    target, old_segments, new_segments, declaration.file
                )
                if blocked is not None:
                    manual.append(
                        ManualSite(
                            str(declaration.file),
                            declaration.line,
                            declaration.column,
                            blocked,
                        )
                    )
                    continue
            else:
                edit = _path_edit(target, old_path, new_path, declaration.file)
                found = [edit] if edit is not None else []
            target_edits.extend(found)

        if target_edits:
            edits.extend(target_edits)
            sites.append(
                Site(
                    str(declaration.file),
                    declaration.line,
                    declaration.column,
                    declaration.raw,
                    _apply_to(declaration.raw, target_edits, declaration.span.start),
                )
            )
        # Not an elif: a button can carry both an updateMetadata bindTarget we
        # rewrite and a js action mentioning the same name that we must not.
        if _js_mentions(declaration, needle_re):
            manual.append(
                ManualSite(
                    str(declaration.file),
                    declaration.line,
                    declaration.column,
                    f"JS mentions {needle!r}; identifiers inside JS are never rewritten",
                )
            )

    return Plan(edits, sites, manual)


def _apply_to(text: str, edits: list[Edit], base: int) -> str:
    """Apply edits to `text`, whose first character is at absolute offset `base`."""
    for edit in sorted(edits, key=lambda e: e.start, reverse=True):
        start, end = edit.start - base, edit.end - base
        if 0 <= start <= end <= len(text):
            text = text[:start] + edit.replacement + text[end:]
    return text


def apply_edits(edits: Iterable[Edit], *, dry_run: bool) -> dict[Path, tuple[str, str]]:
    """Return {file: (before, after)}, writing unless dry_run."""
    by_file: defaultdict[Path, list[Edit]] = defaultdict(list)
    for edit in edits:
        by_file[edit.file].append(edit)

    changed: dict[Path, tuple[str, str]] = {}
    for file, file_edits in by_file.items():
        before = file.read_text(encoding="utf-8")
        after = _apply_to(before, file_edits, 0)
        if after == before:
            continue
        changed[file] = (before, after)
        if not dry_run:
            file.write_text(after, encoding="utf-8")
    return changed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _emit_error(message: str, code: str, hint: str | None = None) -> None:
    payload: dict[str, str] = {"error": message, "code": code}
    if hint is not None:
        payload["hint"] = hint
    print(json.dumps(payload), file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n", 1)[0],
        epilog=(
            "examples:\n"
            "  rename.py --property count hitPoints --dry-run\n"
            "  rename.py --property nested.object nested.payload\n"
            "  rename.py --path 'Other Note' 'Reference Note'   # after rename_note.py\n"
            "  rename.py --vault ~/vault --path old/note.md new/note.md --json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--vault", help="vault root (default: walk up from cwd)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--property",
        nargs=2,
        metavar=("OLD", "NEW"),
        help="rename a frontmatter property (dotted paths allowed)",
    )
    mode.add_argument(
        "--path",
        nargs=2,
        metavar=("OLD", "NEW"),
        help="retarget bind targets naming a note; OLD need not still exist",
    )
    parser.add_argument("--dry-run", action="store_true", help="show the diff without writing")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument("--json", action="store_true", help="alias for --format json")
    parser.add_argument("--quiet", action="store_true", help="suppress informational stderr")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    as_json = args.json or args.format == "json"
    mode = "property" if args.property else "path"
    old, new = args.property or args.path

    if mode == "property":
        old_segments, new_segments = old.split("."), new.split(".")
        if len(old_segments) != len(new_segments):
            _emit_error(
                f"--property OLD and NEW must have the same number of dotted segments "
                f"({len(old_segments)} vs {len(new_segments)})",
                "SEGMENT_MISMATCH",
                hint="rename one level at a time, e.g. --property nested.object nested.payload",
            )
            return EXIT_USER_ERROR
        for segment in new_segments:
            if not _IDENT_RE.match(segment):
                _emit_error(
                    f"{segment!r} is not a valid property name",
                    "INVALID_PROPERTY",
                    hint="property names start with a letter and contain letters, digits, - _ $",
                )
                return EXIT_USER_ERROR

    try:
        vault = locate_vault(args.vault or ".")
    except NotInVaultError as exc:
        _emit_error(str(exc), "NOT_IN_VAULT", hint="pass --vault pointing at the vault root")
        return EXIT_USER_ERROR

    try:
        declarations = [
            declaration for note in iter_notes(vault) for declaration in parse_note(note)
        ]
    except OSError as exc:
        _emit_error(f"vault is unreadable: {exc}", "VAULT_UNREADABLE")
        return EXIT_SYSTEM_ERROR

    plan = build_plan(declarations, old=old, new=new, mode=mode)

    try:
        changed = apply_edits(plan.edits, dry_run=args.dry_run)
    except OSError as exc:
        _emit_error(f"could not write note: {exc}", "WRITE_FAILED")
        return EXIT_SYSTEM_ERROR

    if not args.quiet:
        verb = "would rewrite" if args.dry_run else "rewrote"
        print(
            f"rename: {verb} {len(plan.sites)} declaration(s) in {len(changed)} note(s); "
            f"{len(plan.manual)} need manual attention",
            file=sys.stderr,
        )

    meta = {
        "count": len(plan.sites),
        "files": len(changed),
        "manual": len(plan.manual),
        "dry_run": args.dry_run,
        "mode": mode,
        "old": old,
        "new": new,
    }
    if as_json:
        payload: dict[str, Any] = {
            "data": {
                "rewritten": [asdict(site) for site in plan.sites],
                "manual": [asdict(site) for site in plan.manual],
            },
            "meta": meta,
        }
        print(json.dumps(payload, indent=2))
    else:
        if args.dry_run:
            for file, (before, after) in sorted(changed.items()):
                sys.stdout.writelines(
                    difflib.unified_diff(
                        before.splitlines(keepends=True),
                        after.splitlines(keepends=True),
                        fromfile=str(file),
                        tofile=str(file),
                    )
                )
        else:
            for site in plan.sites:
                print(f"{site.file}:{site.line}:{site.column}  {site.before}  ->  {site.after}")
        for site in plan.manual:
            print(f"{site.file}:{site.line}:{site.column}  MANUAL: {site.reason}", file=sys.stderr)
        print(f"{len(plan.sites)} declaration(s), {len(plan.manual)} needing manual attention")

    if not plan.sites and not plan.manual:
        return EXIT_NOT_FOUND
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
