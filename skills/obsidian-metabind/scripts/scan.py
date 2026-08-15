#!/usr/bin/env python3
# /// script
# requires-python = ">=3.14"
# dependencies = [
#   "pyyaml>=6.0",
# ]
# ///
"""Inventory or validate every Meta Bind declaration in an Obsidian vault.

--list answers "which notes bind to `count`?"; --check validates declarations
against references/field-spec.json — unknown field types and arguments,
arguments illegal on a field type, wrong arity, malformed button YAML, unknown
button actions, and unresolved BUTTON[id] references.

--strict additionally reports bind targets naming a frontmatter property that
does not exist. It is off by default because Meta Bind creates the property on
first write, so a fresh note legitimately has none — but it is exactly the
signal you want after a rename.

Output: JSON or text on stdout.
Exit codes: 0 clean check / declarations listed, 1 findings or bad invocation,
2 unreadable vault or missing field-spec.json, 3 nothing in scope.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
from typing import TYPE_CHECKING, Any, cast

from parser import (
    Declaration,
    FieldSpec,
    NotInVaultError,
    SpecError,
    button_actions,
    iter_notes,
    load_spec,
    locate_vault,
    parse_note,
    read_frontmatter,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from parser import BindTarget

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_SYSTEM_ERROR = 2
EXIT_NOT_FOUND = 3

#: Bind targets with one of these storage types live in memory, not frontmatter.
_MEMORY_STORAGE_TYPES = frozenset({"memory", "globalMemory"})

#: The two declaration kinds validated against the field/argument tables.
_FIELD_KINDS = frozenset({"input", "view"})


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    severity: str
    file: str
    line: int
    column: int
    message: str


def _finding_at(
    declaration: Declaration, code: str, message: str, severity: str = "error"
) -> Finding:
    """A finding located at the declaration it was raised against."""
    return Finding(
        code, severity, str(declaration.file), declaration.line, declaration.column, message
    )


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def _check_arguments(declaration: Declaration, spec: FieldSpec) -> list[Finding]:
    """Validate a field's arguments against the spec table for its kind."""
    table = spec.arguments_for(declaration.kind)
    findings: list[Finding] = []
    seen: Counter[str] = Counter()

    def add(code: str, message: str) -> None:
        findings.append(_finding_at(declaration, code, message))

    for argument in declaration.arguments:
        config = table.get(argument.name)
        if config is None:
            add(
                "metabind.unknown-argument",
                f"unknown {declaration.kind} field argument {argument.name!r}",
            )
            continue

        seen[argument.name] += 1
        if seen[argument.name] > 1 and not config["allow_multiple"]:
            add(
                "metabind.duplicate-argument",
                f"argument {argument.name!r} may only be given once",
            )

        allowed_types: list[str] = config["allowed_field_types"]
        if (
            allowed_types
            and declaration.field_type is not None
            and declaration.field_type not in allowed_types
        ):
            add(
                "metabind.argument-not-allowed",
                f"argument {argument.name!r} is not allowed on field type "
                f"{declaration.field_type!r} (allowed: {', '.join(allowed_types)})",
            )

        arities: list[int] = config["arities"]
        if len(argument.values) not in arities:
            add(
                "metabind.argument-arity",
                f"argument {argument.name!r} takes "
                f"{' or '.join(str(a) for a in arities)} value(s), got {len(argument.values)}",
            )
            continue

        signature = next(
            (s for s in config["signatures"] if len(s) == len(argument.values)),
            None,
        )
        if signature is None:
            continue
        for value, value_config in zip(argument.values, signature, strict=True):
            allowed: list[str] = value_config["allowed"]
            if not allowed:
                continue
            if allowed == ["number"]:
                try:
                    float(value)
                except ValueError:
                    add(
                        "metabind.argument-value",
                        f"argument {argument.name!r} expects a number, got {value!r}",
                    )
            elif value not in allowed:
                add(
                    "metabind.argument-value",
                    f"argument {argument.name!r} expects one of "
                    f"{', '.join(allowed)}, got {value!r}",
                )
    return findings


def _check_field(declaration: Declaration, spec: FieldSpec) -> list[Finding]:
    types = spec.types_for(declaration.kind)

    # A view field without a `[type]` section defaults, and an input field with
    # a template takes its type from that template. A bare `INPUT[...]` with no
    # type never reaches here — the grammar rejects it as a parse error.
    if declaration.field_type is None:
        return _check_arguments(declaration, spec)
    if declaration.field_type not in types:
        return [
            _finding_at(
                declaration,
                "metabind.unknown-field-type",
                f"unknown {declaration.kind} field type {declaration.field_type!r}",
            )
        ]

    findings = _check_arguments(declaration, spec)
    config = types[declaration.field_type]
    if declaration.host == "inline" and config.get("allow_inline") is False:
        findings.append(
            _finding_at(
                declaration,
                "metabind.inline-not-allowed",
                f"field type {declaration.field_type!r} does not render in an inline "
                "code span — use a ```meta-bind fenced block",
            )
        )
    return findings


def _check_button_action(
    declaration: Declaration, raw_action: Any, spec: FieldSpec
) -> list[Finding]:
    if not isinstance(raw_action, dict):
        return [
            _finding_at(declaration, "metabind.button-config", "button action must be a mapping")
        ]

    action = cast("dict[str, Any]", raw_action)
    action_type = action.get("type")
    known = spec.button_action_types
    if not isinstance(action_type, str) or action_type not in known:
        return [
            _finding_at(
                declaration,
                "metabind.unknown-button-action",
                f"unknown button action type {action_type!r} (known: {', '.join(sorted(known))})",
            )
        ]

    schema = known[action_type]
    keys = set(action)
    allowed = set(schema["required"]) | set(schema["optional"]) | {"type"}
    code = "metabind.button-action-field"
    return [
        _finding_at(
            declaration,
            code,
            f"button action {action_type!r} is missing required field {missing!r}",
        )
        for missing in sorted(set(schema["required"]) - keys)
    ] + [
        _finding_at(
            declaration, code, f"button action {action_type!r} has unknown field {unknown!r}"
        )
        for unknown in sorted(keys - allowed)
    ]


def _check_button_config(declaration: Declaration, spec: FieldSpec) -> list[Finding]:
    config = declaration.button_config
    code = "metabind.button-config"
    if not isinstance(config, dict):
        return [_finding_at(declaration, code, "button config must be a YAML mapping")]

    fields = spec.button_config_fields
    keys = {str(key) for key in config}
    required: list[str] = fields.get("required", [])
    allowed = set(required) | set(fields.get("optional", []))
    findings: list[Finding] = [
        _finding_at(declaration, code, f"button config is missing required key {missing!r}")
        for missing in sorted(set(required) - keys)
    ]
    findings.extend(
        _finding_at(declaration, code, f"button config has unknown key {unknown!r}")
        for unknown in sorted(keys - allowed)
    )
    if "action" in config and "actions" in config:
        findings.append(
            _finding_at(
                declaration,
                code,
                "button config sets both 'action' and 'actions' — they are mutually exclusive",
            )
        )
    style = config.get("style")
    styles: list[str] = spec.raw.get("button_styles", [])
    if isinstance(style, str) and styles and style not in styles:
        findings.append(
            _finding_at(
                declaration, code, f"unknown button style {style!r} (known: {', '.join(styles)})"
            )
        )

    for action in button_actions(config):
        findings.extend(_check_button_action(declaration, action, spec))
    return findings


def _resolve_note(vault: Path, notes: Mapping[str, list[Path]], storage_path: str) -> Path | None:
    """Resolve a bind target's file half the way Obsidian resolves a link name."""
    direct = vault / f"{storage_path.removesuffix('.md')}.md"
    if direct.is_file():
        return direct
    candidates = notes.get(Path(storage_path).name.removesuffix(".md"), [])
    return candidates[0] if len(candidates) == 1 else None


def _check_property_exists(
    declaration: Declaration,
    target: BindTarget,
    vault: Path,
    notes: Mapping[str, list[Path]],
    frontmatter_cache: dict[Path, dict[str, object]],
) -> Finding | None:
    if target.storage_type in _MEMORY_STORAGE_TYPES or not target.props:
        return None
    note = declaration.file
    if target.storage_path is not None:
        resolved = _resolve_note(vault, notes, target.storage_path)
        if resolved is None:
            return _finding_at(
                declaration,
                "metabind.unresolved-note",
                f"bind target names note {target.storage_path!r}, which does not resolve",
                "warning",
            )
        note = resolved
    if note not in frontmatter_cache:
        try:
            frontmatter_cache[note] = read_frontmatter(note)
        except OSError:
            frontmatter_cache[note] = {}
    if target.props[0].name not in frontmatter_cache[note]:
        return _finding_at(
            declaration,
            "metabind.missing-property",
            f"bind target {target.render()!r} names property "
            f"{target.props[0].name!r}, absent from {note.name}'s frontmatter",
            "warning",
        )
    return None


def check(
    declarations: Iterable[Declaration],
    spec: FieldSpec,
    *,
    vault: Path,
    known_button_ids: set[str],
    notes_by_name: Mapping[str, list[Path]],
    strict: bool,
) -> list[Finding]:
    findings: list[Finding] = []
    frontmatter_cache: dict[Path, dict[str, object]] = {}

    for declaration in declarations:
        findings.extend(
            _finding_at(declaration, "metabind.parse-error", error.message)
            for error in declaration.errors
        )
        if declaration.errors:
            continue

        if declaration.kind in _FIELD_KINDS:
            findings.extend(_check_field(declaration, spec))
        elif declaration.kind == "button-config":
            findings.extend(_check_button_config(declaration, spec))
        elif declaration.kind == "button-group":
            findings.extend(
                _finding_at(
                    declaration,
                    "metabind.unresolved-button-id",
                    f"BUTTON[{button_id}] references no button config with that id",
                )
                for button_id in declaration.button_ids
                if button_id not in known_button_ids
            )

        if strict:
            findings.extend(
                finding
                for target in declaration.bind_targets
                if (
                    finding := _check_property_exists(
                        declaration, target, vault, notes_by_name, frontmatter_cache
                    )
                )
                is not None
            )

    return findings


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------


def collect(paths: Iterable[Path]) -> list[Declaration]:
    return [declaration for note in paths for declaration in parse_note(note)]


def button_ids(declarations: Iterable[Declaration]) -> set[str]:
    ids: set[str] = set()
    for declaration in declarations:
        if declaration.kind == "button-config" and isinstance(declaration.button_config, dict):
            button_id = declaration.button_config.get("id")  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            if isinstance(button_id, str):
                ids.add(button_id)
    return ids


def _row(declaration: Declaration) -> dict[str, Any]:
    return {
        "file": str(declaration.file),
        "line": declaration.line,
        "column": declaration.column,
        "kind": declaration.kind,
        "host": declaration.host,
        "field_type": declaration.field_type,
        "template_name": declaration.template_name,
        "bind_target": (
            declaration.bind_target.render() if declaration.bind_target is not None else None
        ),
        "read_targets": [target.render() for target in declaration.read_targets],
        "arguments": [argument.name for argument in declaration.arguments],
        "button_ids": list(declaration.button_ids),
        "button_id": (
            declaration.button_config.get("id")
            if isinstance(declaration.button_config, dict)
            else None
        ),
        "embed_target": declaration.embed_target,
        "has_errors": bool(declaration.errors),
        "raw": declaration.raw if len(declaration.raw) <= 120 else declaration.raw[:117] + "...",
    }


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
            "  scan.py --list                            # every declaration in the vault\n"
            "  scan.py --list --json | jq '.data[].bind_target'\n"
            "  scan.py --check                           # validate the whole vault\n"
            "  scan.py --check --strict Notes/Health.md  # after a frontmatter rename\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths", nargs="*", type=Path, help="narrow the scan (default: whole vault)"
    )
    parser.add_argument("--vault", help="vault root (default: walk up from cwd)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true", help="inventory every declaration")
    mode.add_argument("--check", action="store_true", help="validate against field-spec.json")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also report bind targets naming a property absent from frontmatter",
    )
    parser.add_argument("--spec-path", type=Path, help="override references/field-spec.json")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument("--json", action="store_true", help="alias for --format json")
    parser.add_argument("--quiet", action="store_true", help="suppress informational stderr")
    return parser


def _print_list(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        detail = row["bind_target"] or ", ".join(row["button_ids"]) or row["embed_target"] or ""
        kind = row["kind"] if row["field_type"] is None else f"{row['kind']}:{row['field_type']}"
        print(f"{row['file']}:{row['line']}:{row['column']}  {kind}  {detail}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    as_json = args.json or args.format == "json"

    try:
        vault = locate_vault(args.vault or (args.paths[0] if args.paths else "."))
    except NotInVaultError as exc:
        _emit_error(str(exc), "NOT_IN_VAULT", hint="pass --vault pointing at the vault root")
        return EXIT_USER_ERROR

    for path in args.paths:
        if not path.exists():
            _emit_error(f"path does not exist: {path}", "PATH_NOT_FOUND")
            return EXIT_USER_ERROR

    try:
        scope: list[Path] = []
        if args.paths:
            for path in args.paths:
                scope.extend(iter_notes(path))
        else:
            scope = list(iter_notes(vault))
        declarations = collect(scope)
    except OSError as exc:
        _emit_error(f"vault is unreadable: {exc}", "VAULT_UNREADABLE")
        return EXIT_SYSTEM_ERROR

    if not args.quiet:
        print(
            f"scan: {len(declarations)} declaration(s) in {len(scope)} note(s) under {vault}",
            file=sys.stderr,
        )

    if args.list:
        if not declarations:
            if as_json:
                print(json.dumps({"data": [], "meta": {"count": 0, "notes": len(scope)}}))
            return EXIT_NOT_FOUND
        rows = [_row(declaration) for declaration in declarations]
        if as_json:
            print(
                json.dumps(
                    {"data": rows, "meta": {"count": len(rows), "notes": len(scope)}}, indent=2
                )
            )
        else:
            _print_list(rows)
        return EXIT_OK

    try:
        spec = load_spec(args.spec_path)
    except SpecError as exc:
        _emit_error(str(exc), "SPEC_UNAVAILABLE", hint="run refresh_docs.py --only spec")
        return EXIT_SYSTEM_ERROR

    # Button ids resolve across the whole vault, so they are collected vault-wide
    # even when positional paths narrow what gets validated.
    try:
        vault_declarations = declarations if not args.paths else collect(iter_notes(vault))
    except OSError as exc:
        _emit_error(f"vault is unreadable: {exc}", "VAULT_UNREADABLE")
        return EXIT_SYSTEM_ERROR

    notes_by_name: defaultdict[str, list[Path]] = defaultdict(list)
    for note in iter_notes(vault):
        notes_by_name[note.stem].append(note)

    findings = check(
        declarations,
        spec,
        vault=vault,
        known_button_ids=button_ids(vault_declarations),
        notes_by_name=notes_by_name,
        strict=args.strict,
    )

    if not declarations:
        return EXIT_NOT_FOUND

    errors = sum(1 for finding in findings if finding.severity == "error")
    meta = {
        "count": len(findings),
        "errors": errors,
        "warnings": len(findings) - errors,
        "declarations": len(declarations),
        "notes": len(scope),
    }
    if as_json:
        print(json.dumps({"data": [asdict(f) for f in findings], "meta": meta}, indent=2))
    else:
        for finding in findings:
            print(
                f"{finding.file}:{finding.line}:{finding.column}: "
                f"{finding.severity}: [{finding.code}] {finding.message}"
            )
        print(f"{meta['errors']} error(s), {meta['warnings']} warning(s)")
    return EXIT_USER_ERROR if findings else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
