#!/usr/bin/env python3
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Compact, machine-readable rendering of the installed Azure CLI's own help.

Why this exists: `az <command> -h` is authoritative and version-exact, but
verbose. `az sql db create -h` is 17 KB, of which ~1.5 KB is global arguments
the agent already knows and most of the rest is prose describing optional
flags it will not use. This tool reduces that to ~1.2 KB by keeping required
arguments in full, reducing optional arguments to their names plus enumerated
values, and dropping the global-argument block.

Three modes:
    group   `az-help.py sql`                 subgroups + commands, one line each
    command `az-help.py sql db create`       compact argument reference
    tree    `az-help.py --tree sql`          every leaf command beneath a group

No network access is required: `az` renders help from locally installed
command modules. The one exception is a command belonging to an extension that
is not yet installed, which `az` will fetch on demand.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import re
import sys
from typing import Any

from _common import (
    EXIT_NOT_FOUND,
    EXIT_OK,
    EXIT_SYSTEM_ERROR,
    EXIT_USER_ERROR,
    HELP_TIMEOUT,
    AgentToolParser,
    AzUnavailableError,
    Timer,
    add_common_flags,
    emit_error,
    emit_json,
    install_hint,
    last_error_line,
    log,
    run_az,
)

# Argument entries begin at column 4 with a dash; deeper indentation is a
# wrapped continuation of the preceding entry's description.
ARG_ENTRY_SPLIT = re.compile(r"\n(?=    -)")
# "    db                      : Manage databases."
# "    instance-pool [Preview] : Manage instance pools."
LISTING_ENTRY = re.compile(r"^ {4}(\S+)(?: +\[(\w+)\])? +: (.*)$")
ALLOWED_VALUES = re.compile(r"Allowed values:\s*([^.]+?)\.")
DEFAULT_VALUE = re.compile(r"Default:\s*([^.\s][^.]*?)\.")
REQUIRED_MARKER = "[Required]"

# Global arguments are identical on every command and already known to the
# agent; dropping them is most of the token saving.
GLOBAL_SECTIONS = frozenset({"Global Arguments", "Global Policy Arguments"})
MAX_TREE_WORKERS = 8

# Subgroups and commands directly under one command path.
type Listing = tuple[list[dict[str, Any]], list[dict[str, Any]]]


def unwrap(lines: list[str]) -> str:
    """Join help lines that the CLI hard-wrapped at the terminal width.

    `az` wraps mid-token, leaving a trailing hyphen (``--backup-storage-`` /
    ``redundancy``). Rejoining on whitespace alone would corrupt those flags,
    so a trailing hyphen joins with no separator.
    """
    joined = ""
    for raw in lines:
        piece = raw.strip()
        if not piece:
            continue
        if not joined:
            joined = piece
        elif joined.endswith("-"):
            joined += piece
        else:
            joined += " " + piece
    return joined


def split_sections(text: str) -> dict[str, list[str]]:
    """Split raw help output into its column-0 section headings."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line and not line.startswith(" "):
            current = line.strip()
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return sections


def parse_listing(body: list[str]) -> list[dict[str, Any]]:
    """Parse a `Subgroups:` or `Commands:` block into name/status/summary."""
    entries: list[tuple[str, str | None, list[str]]] = []
    for line in body:
        match = LISTING_ENTRY.match(line)
        if match:
            entries.append((match.group(1), match.group(2), [match.group(3)]))
        elif entries:
            entries[-1][2].append(line)
    return [
        {"name": name, "status": status, "summary": unwrap(summary)}
        for name, status, summary in entries
    ]


def parse_arguments(
    sections: dict[str, list[str]], *, full: bool
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split every argument section into required and optional entries.

    Optional entries keep their description only in full mode; in compact mode
    they are reduced to flags plus any enumerated values, which is what an
    agent needs to decide whether a flag is the one it wants.
    """
    required: list[dict[str, Any]] = []
    optional: list[dict[str, Any]] = []
    for name, body in sections.items():
        if not name.endswith("Arguments"):
            continue
        if name in GLOBAL_SECTIONS and not full:
            continue
        for chunk in ARG_ENTRY_SPLIT.split("\n".join(body)):
            entry = unwrap(chunk.splitlines())
            if not entry.startswith("-"):
                continue
            head, _, description = entry.partition(" : ")
            is_required = REQUIRED_MARKER in head
            flags = head.replace(REQUIRED_MARKER, "").split()
            allowed = ALLOWED_VALUES.search(description)
            default = DEFAULT_VALUE.search(description)
            record: dict[str, Any] = {"flags": flags}
            if allowed:
                record["allowed"] = [v.strip() for v in allowed.group(1).split(",")]
            if default:
                record["default"] = default.group(1).strip()
            if is_required or full:
                record["description"] = description.strip()
            if name not in GLOBAL_SECTIONS and name != "Arguments":
                record["group"] = name.removesuffix(" Arguments")
            (required if is_required else optional).append(record)
    return required, optional


def parse_examples(body: list[str]) -> list[str]:
    """Extract the runnable command lines from the Examples section."""
    examples: list[str] = []
    pending: list[str] = []
    for line in body:
        indent = len(line) - len(line.lstrip())
        if not line.strip():
            continue
        if indent >= 8:
            pending.append(line)
        elif pending:
            examples.append(unwrap(pending))
            pending = []
    if pending:
        examples.append(unwrap(pending))
    return examples


def fetch_help(path: list[str], timeout: int) -> str:
    """Return raw help text for a command path, or raise on an unknown path."""
    result = run_az([*path, "-h"], timeout=timeout)
    if result.returncode != 0 or not result.stdout.strip():
        raise LookupError(last_error_line(result.stderr or result.stdout))
    return result.stdout


def describe(path: list[str], *, full: bool, timeout: int) -> dict[str, Any]:
    """Parse one command path into the compact envelope payload."""
    sections = split_sections(fetch_help(path, timeout))
    command = " ".join(["az", *path])
    is_group = "Group" in sections
    header = sections.get("Group") or sections.get("Command") or []
    summary = unwrap(header)
    # The header repeats the command path before the summary; drop it.
    summary = summary.partition(" : ")[2] or summary

    if is_group:
        return {
            "kind": "group",
            "command": command,
            "summary": summary,
            "subgroups": parse_listing(sections.get("Subgroups:", [])),
            "commands": parse_listing(sections.get("Commands:", [])),
        }

    required, optional = parse_arguments(sections, full=full)
    return {
        "kind": "command",
        "command": command,
        "summary": summary,
        "required": required,
        "optional": optional,
        "examples": parse_examples(sections.get("Examples", [])),
    }


def walk_tree(root: list[str], timeout: int, max_depth: int) -> list[dict[str, str]]:
    """Collect every leaf command beneath a group, one level at a time.

    `az <group> -h` only reveals one level, so finding a deeply nested command
    such as `az sql db advanced-threat-protection-setting update` otherwise
    costs several sequential round trips. Each call is cheap (~0.1-0.3s) and
    sibling branches are independent, so every level fans out across the pool.

    The walk is breadth-first rather than recursive on purpose: submitting
    child work to the same bounded pool from inside a running task deadlocks
    once the tree is deeper than the worker count, because every worker ends
    up blocked waiting on children that are still queued behind it.
    """
    found: list[dict[str, str]] = []
    level: list[list[str]] = [root]

    def visit(path: list[str]) -> tuple[list[str], Listing | None]:
        return path, _listing_at(path, timeout)

    with ThreadPoolExecutor(max_workers=MAX_TREE_WORKERS) as pool:
        for depth in range(max_depth + 1):
            if not level:
                break
            results = list(pool.map(visit, level))
            next_level: list[list[str]] = []
            for path, listing in results:
                if listing is None:
                    continue
                subgroups, commands = listing
                prefix = " ".join(["az", *path])
                found.extend(
                    {"command": f"{prefix} {c['name']}", "summary": c["summary"]} for c in commands
                )
                if depth < max_depth:
                    next_level.extend([*path, s["name"]] for s in subgroups)
            level = next_level
    return sorted(found, key=lambda r: r["command"])


def _listing_at(path: list[str], timeout: int) -> Listing | None:
    """Subgroups and commands directly under one path, or None if unreadable.

    Only an unrecognised path is tolerated: mid-walk it means the branch
    vanished between listings, and skipping it still yields a useful tree. An
    unusable `az` propagates instead, because reporting a missing CLI as an
    empty group would tell the agent the commands do not exist.
    """
    try:
        sections = split_sections(fetch_help(path, timeout))
    except LookupError:
        return None
    return parse_listing(sections.get("Subgroups:", [])), parse_listing(
        sections.get("Commands:", [])
    )


def render_group(data: dict[str, Any]) -> str:
    lines = [f"{data['command']} — {data['summary']}"]
    for label, key in (("SUBGROUPS", "subgroups"), ("COMMANDS", "commands")):
        if not data[key]:
            continue
        lines.append(label)
        labelled = [
            (e["name"] + (f" [{e['status']}]" if e["status"] else ""), e["summary"])
            for e in data[key]
        ]
        width = max(len(name) for name, _ in labelled)
        lines.extend(f"  {name:<{width}}  {summary}" for name, summary in labelled)
    return "\n".join(lines)


def render_command(data: dict[str, Any]) -> str:
    lines = [f"{data['command']} — {data['summary']}"]
    if data["required"]:
        lines.append("REQUIRED")
        width = max(len(" ".join(a["flags"])) for a in data["required"])
        for arg in data["required"]:
            flags = " ".join(arg["flags"])
            allowed = f" ({'|'.join(arg['allowed'])})" if "allowed" in arg else ""
            lines.append(f"  {flags:<{width}}  {arg.get('description', '')}{allowed}")
    if data["optional"]:
        rendered: list[str] = []
        for arg in data["optional"]:
            flag = arg["flags"][0]
            if "allowed" in arg:
                flag += "=" + "|".join(arg["allowed"])
            rendered.append(flag)
        lines.append("OPTIONAL")
        lines.append("  " + " ".join(rendered))
    if data["examples"]:
        lines.append("EXAMPLES")
        lines.extend(f"  {ex}" for ex in data["examples"])
    return "\n".join(lines)


def render_tree(rows: list[dict[str, str]]) -> str:
    width = max(len(r["command"]) for r in rows)
    return "\n".join(f"{r['command']:<{width}}  # {r['summary']}" for r in rows)


def tree_mode(args: argparse.Namespace, pattern: re.Pattern[str] | None, timer: Timer) -> int:
    """Walk every leaf command beneath a group, then filter, cap, and emit."""
    log(f"walking `az {' '.join(args.path)}` ...", quiet=args.quiet)
    try:
        rows = walk_tree(args.path, args.timeout, args.max_depth)
    except AzUnavailableError as exc:
        emit_error(str(exc), "AZ_UNAVAILABLE", hint=install_hint())
        return EXIT_SYSTEM_ERROR
    total = len(rows)
    if pattern:
        rows = [r for r in rows if pattern.search(r["command"] + " " + r["summary"])]
    matched = len(rows)
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        emit_error(
            f"No commands found under `az {' '.join(args.path)}`"
            + (f" matching {args.match!r}" if args.match else ""),
            "NOT_FOUND",
            hint="Check the group name with `az-help.py` (no arguments) or widen --match.",
        )
        return EXIT_NOT_FOUND
    if args.format == "text":
        print(render_tree(rows))
    else:
        emit_json(
            {
                "data": rows,
                "meta": {
                    "count": len(rows),
                    "matched": matched,
                    "total": total,
                    "truncated": bool(args.limit and matched > args.limit),
                    "elapsed_ms": timer.elapsed_ms,
                },
            }
        )
    return EXIT_OK


def describe_mode(args: argparse.Namespace, timer: Timer) -> int:
    """Render one command path as a group listing or an argument reference."""
    try:
        data = describe(args.path, full=args.full, timeout=args.timeout)
    except LookupError as exc:
        emit_error(
            str(exc),
            "NOT_FOUND",
            hint=f"List what exists with `az-help.py {' '.join(args.path[:-1])}`"
            if len(args.path) > 1
            else "List the top-level groups with `az-help.py` (no arguments).",
            input=" ".join(["az", *args.path]),
        )
        return EXIT_NOT_FOUND
    except AzUnavailableError as exc:
        emit_error(str(exc), "AZ_UNAVAILABLE", hint=install_hint())
        return EXIT_SYSTEM_ERROR

    if args.format == "text":
        print(render_group(data) if data["kind"] == "group" else render_command(data))
        return EXIT_OK

    meta: dict[str, Any] = {"elapsed_ms": timer.elapsed_ms, "full": args.full}
    if data["kind"] == "group":
        meta["subgroup_count"] = len(data["subgroups"])
        meta["command_count"] = len(data["commands"])
    else:
        meta["required_count"] = len(data["required"])
        meta["optional_count"] = len(data["optional"])
    emit_json({"data": data, "meta": meta})
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = AgentToolParser(
        prog="az-help.py",
        description="Compact rendering of the installed Azure CLI's own help.",
        epilog="""Examples:
  az-help.py sql                          list subgroups and commands under `az sql`
  az-help.py sql db create                compact argument reference (~14x smaller than -h)
  az-help.py sql db create --full         include optional descriptions and global arguments
  az-help.py --tree webapp                every leaf command under `az webapp`
  az-help.py --tree monitor --match log   only commands whose name or summary mentions "log"
  az-help.py --format text webapp config  compact text rendering, cheaper than JSON
  az-help.py --tree aks --quiet           suppress the progress line on stderr

Exit codes: 0 ok · 1 bad invocation · 2 `az` missing or wedged · 3 command path
not recognised by the installed CLI (or --tree/--match matched nothing).""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "path",
        nargs="*",
        help="Command path without the leading `az`, e.g. `sql db create`. "
        "Omit entirely for the top-level group listing.",
    )
    parser.add_argument(
        "--tree",
        action="store_true",
        help="Recursively list every leaf command beneath the given group.",
    )
    parser.add_argument(
        "--match",
        help="With --tree, keep only rows whose command or summary matches this "
        "case-insensitive regular expression.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Keep optional-argument descriptions and the global-argument block. "
        "Roughly the size of raw `az -h`; use only when compact output is ambiguous.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="With --tree, return at most N rows (applied after --match).",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=6,
        help="With --tree, how many subgroup levels to descend (default: 6).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=HELP_TIMEOUT,
        help=f"Per-invocation timeout in seconds for each `az` call (default: {HELP_TIMEOUT}).",
    )
    add_common_flags(parser)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # Validate everything before spending a subprocess.
    if any(segment.startswith("-") for segment in args.path):
        emit_error(
            f"Command path contains a flag: {args.path}",
            "INVALID_ARG",
            hint="Pass only the command path, e.g. `sql db create`. Flags come after it.",
        )
        return EXIT_USER_ERROR
    if args.path and args.path[0] == "az":
        emit_error(
            "Command path must not include the leading `az`",
            "INVALID_ARG",
            hint=f"Use `{' '.join(args.path[1:]) or '<group>'}` instead of `{' '.join(args.path)}`",
        )
        return EXIT_USER_ERROR
    if args.tree and not args.path:
        emit_error(
            "--tree requires a command group",
            "MISSING_ARG",
            hint="Walking the whole CLI yields thousands of commands. "
            "Start from a group, e.g. `--tree webapp`.",
        )
        return EXIT_USER_ERROR
    if args.match and not args.tree:
        emit_error(
            "--match is only meaningful with --tree",
            "INVALID_ARG",
            hint="Add --tree, or drop --match.",
        )
        return EXIT_USER_ERROR
    if args.limit is not None and args.limit < 1:
        emit_error("--limit must be 1 or greater", "INVALID_ARG", input=str(args.limit))
        return EXIT_USER_ERROR

    pattern = None
    if args.match:
        try:
            pattern = re.compile(args.match, re.IGNORECASE)
        except re.error as exc:
            emit_error(
                f"--match is not a valid regular expression: {exc}", "INVALID_ARG", input=args.match
            )
            return EXIT_USER_ERROR

    timer = Timer()
    if args.tree:
        return tree_mode(args, pattern, timer)
    return describe_mode(args, timer)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AzUnavailableError as exc:  # pragma: no cover - guard for stray call paths
        emit_error(str(exc), "AZ_UNAVAILABLE", hint=install_hint())
        sys.exit(EXIT_SYSTEM_ERROR)
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(EXIT_SYSTEM_ERROR)
    except Exception as exc:
        emit_error(
            f"Unhandled failure: {exc}",
            "INTERNAL_ERROR",
            hint="Re-run with --full to see whether the help text parsed at all.",
        )
        sys.exit(EXIT_SYSTEM_ERROR)
