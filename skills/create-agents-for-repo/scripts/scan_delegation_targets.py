#!/usr/bin/env python3
"""Inventory a repo's delegation surface: skills, agents, commands, and toolchain.

One call replaces the dozen Glob/Read round trips it otherwise takes to answer
"what could be delegated here, and what am I allowed to edit". Reports each
skill's origin (repo / plugin / symlink) because that decides whether wiring an
agent call into its SKILL.md survives the next update.

Usage:
    scan_delegation_targets.py <repo-root> [--format json|text] [--plugins-dir PATH]

Exit codes:
    0   Delegation surface found
    1   Bad invocation (path missing or not a directory)
    2   System error (repo root unreadable)
    3   No delegation surface found
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
import subprocess
import sys
import textwrap
import tomllib
from typing import Any

from agents_lib import get_list, get_str, parse_frontmatter, read_text, walk_files

EXIT_OK = 0
EXIT_BAD_INVOCATION = 1
EXIT_SYSTEM = 2
EXIT_EMPTY = 3

# Outline entries per skill. Enough to walk a workflow step by step in Lens A;
# capped so one long skill cannot dominate the payload.
MAX_OUTLINE = 60
MAX_FENCED_COMMANDS = 40

_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$")
_STEP_RE = re.compile(r"^\s{0,3}(\d+)\.\s+(?:\*\*)?(.+?)(?:\*\*)?\s*$")
_MAKE_TARGET_RE = re.compile(r"^([A-Za-z0-9_][A-Za-z0-9_.-]*):(?!=)")
_FENCE_RE = re.compile(r"^```(?:bash|sh|shell|console)\s*$")
_FENCE_CLOSE_RE = re.compile(r"^```\s*$")


@dataclass
class SkillEntry:
    name: str
    path: str
    origin: str
    editable: bool
    description: str
    body_lines: int
    outline: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])


@dataclass
class AgentEntry:
    name: str
    path: str
    model: str | None
    tools: list[str] | None
    max_turns: str | None
    description: str


@dataclass
class CommandEntry:
    name: str
    path: str
    description: str


@dataclass
class ToolchainEntry:
    kind: str
    command: str
    source: str


def _error(message: str, code: str, hint: str) -> None:
    """Structured error on stderr — the agent gets one shape from every failure."""
    print(json.dumps({"error": message, "code": code, "hint": hint}), file=sys.stderr)


def _first_sentence(text: str, limit: int = 240) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


def _outline(body: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for number, line in enumerate(body.splitlines(), start=1):
        heading = _HEADING_RE.match(line)
        if heading:
            entries.append({"kind": "heading", "text": heading.group(2), "line": number})
        else:
            step = _STEP_RE.match(line)
            if step:
                entries.append(
                    {"kind": "step", "text": _first_sentence(step.group(2), 120), "line": number}
                )
        if len(entries) >= MAX_OUTLINE:
            break
    return entries


def _classify_origin(skill_md: Path, repo_root: Path, plugins_dir: Path) -> tuple[str, bool]:
    """Return (origin, editable) for a skill, following symlinks to decide."""
    resolved = skill_md.resolve()
    if _is_relative_to(resolved, plugins_dir):
        return "plugin", False
    if resolved != skill_md.absolute() and not _is_relative_to(resolved, repo_root):
        return "symlink", False
    if _is_relative_to(resolved, repo_root):
        return "repo", True
    return "external", False


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def collect_skills(repo_root: Path, plugins_dir: Path) -> list[SkillEntry]:
    # Deduped by resolved path: a repo whose .claude is a symlink to .agents
    # otherwise reports every skill twice, once down each spelling of the tree.
    seen: set[Path] = set()
    skills: list[SkillEntry] = []
    for skill_md in walk_files(repo_root, "SKILL.md"):
        real = skill_md.resolve()
        if real in seen:
            continue
        seen.add(real)
        text = read_text(skill_md)
        if text is None:
            continue
        frontmatter, body = parse_frontmatter(text)
        frontmatter = frontmatter or {}
        origin, editable = _classify_origin(skill_md, repo_root, plugins_dir)
        skills.append(
            SkillEntry(
                name=get_str(frontmatter, "name") or skill_md.parent.name,
                path=str(skill_md),
                origin=origin,
                editable=editable,
                description=_first_sentence(get_str(frontmatter, "description") or ""),
                body_lines=len(body.splitlines()),
                outline=_outline(body),
            )
        )
    return skills


def collect_agents(agents_dir: Path) -> list[AgentEntry]:
    if not agents_dir.is_dir():
        return []
    agents: list[AgentEntry] = []
    for agent_md in sorted(agents_dir.rglob("*.md")):
        text = read_text(agent_md)
        if text is None:
            continue
        frontmatter, _ = parse_frontmatter(text)
        frontmatter = frontmatter or {}
        agents.append(
            AgentEntry(
                name=get_str(frontmatter, "name") or agent_md.stem,
                path=str(agent_md),
                model=get_str(frontmatter, "model"),
                tools=get_list(frontmatter, "tools"),
                max_turns=get_str(frontmatter, "maxTurns"),
                description=_first_sentence(get_str(frontmatter, "description") or ""),
            )
        )
    return agents


def collect_commands(repo_root: Path) -> list[CommandEntry]:
    commands_dir = repo_root / ".claude" / "commands"
    if not commands_dir.is_dir():
        return []
    commands: list[CommandEntry] = []
    for command_md in sorted(commands_dir.rglob("*.md")):
        text = read_text(command_md)
        if text is None:
            continue
        frontmatter, body = parse_frontmatter(text)
        description = get_str(frontmatter or {}, "description") or body.strip().split("\n", 1)[0]
        commands.append(
            CommandEntry(
                name=command_md.stem,
                path=str(command_md),
                description=_first_sentence(description),
            )
        )
    return commands


def _pyproject_toolchain(repo_root: Path) -> list[ToolchainEntry]:
    pyproject = repo_root / "pyproject.toml"
    text = read_text(pyproject)
    if text is None:
        return []
    try:
        data: dict[str, Any] = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    tools: dict[str, Any] = data.get("tool", {})
    runner = "uv run " if (repo_root / "uv.lock").exists() else ""
    entries: list[ToolchainEntry] = []
    if "pytest" in tools:
        entries.append(ToolchainEntry("test", f"{runner}pytest", "pyproject.toml"))
    if "ruff" in tools:
        entries.append(ToolchainEntry("lint", f"{runner}ruff check .", "pyproject.toml"))
        entries.append(ToolchainEntry("format", f"{runner}ruff format .", "pyproject.toml"))
    if "pyright" in tools:
        entries.append(ToolchainEntry("typecheck", f"{runner}pyright", "pyproject.toml"))
    if "mypy" in tools:
        entries.append(ToolchainEntry("typecheck", f"{runner}mypy .", "pyproject.toml"))
    scripts: dict[str, Any] = data.get("project", {}).get("scripts", {})
    entries.extend(
        ToolchainEntry("entrypoint", f"{runner}{name}", "pyproject.toml") for name in scripts
    )
    return entries


def _package_json_toolchain(repo_roots: list[Path]) -> list[ToolchainEntry]:
    entries: list[ToolchainEntry] = []
    for package_json in repo_roots:
        text = read_text(package_json)
        if text is None:
            continue
        try:
            data: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError:
            continue
        scripts: dict[str, Any] = data.get("scripts", {})
        entries.extend(
            ToolchainEntry(_script_kind(name), f"npm run {name}", str(package_json))
            for name in scripts
        )
    return entries


def _script_kind(name: str) -> str:
    lowered = name.lower()
    for keyword, kind in (
        ("test", "test"),
        ("lint", "lint"),
        ("format", "format"),
        ("typecheck", "typecheck"),
        ("build", "build"),
    ):
        if keyword in lowered:
            return kind
    return "script"


def _makefile_toolchain(repo_root: Path) -> list[ToolchainEntry]:
    makefile = repo_root / "Makefile"
    text = read_text(makefile)
    if text is None:
        return []
    entries: list[ToolchainEntry] = []
    for line in text.splitlines():
        match = _MAKE_TARGET_RE.match(line)
        if match and not match.group(1).startswith("."):
            target = match.group(1)
            entries.append(ToolchainEntry(_script_kind(target), f"make {target}", "Makefile"))
    return entries


def collect_toolchain(repo_root: Path) -> list[ToolchainEntry]:
    return [
        *_pyproject_toolchain(repo_root),
        *_package_json_toolchain(walk_files(repo_root, "package.json", max_depth=3)),
        *_makefile_toolchain(repo_root),
    ]


def _fenced_commands(body: str) -> list[str]:
    commands: list[str] = []
    inside = False
    for line in body.splitlines():
        if not inside:
            if _FENCE_RE.match(line):
                inside = True
            continue
        if _FENCE_CLOSE_RE.match(line):
            inside = False
            continue
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped not in commands:
            commands.append(stripped)
        if len(commands) >= MAX_FENCED_COMMANDS:
            break
    return commands


def collect_claude_md(repo_root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for claude_md in walk_files(repo_root, "CLAUDE.md", max_depth=3):
        text = read_text(claude_md)
        if text is None:
            continue
        docs.append(
            {
                "path": str(claude_md),
                "lines": len(text.splitlines()),
                "has_delegation_section": "## Delegation" in text,
                "fenced_commands": _fenced_commands(text),
            }
        )
    return docs


def _is_gitignored(repo_root: Path, target: Path) -> bool | None:
    """True/False when git can answer, None when it cannot (no git, no repo)."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "check-ignore", "-q", str(target)],
            capture_output=True,
            check=False,
            timeout=10,
        )
    except OSError, subprocess.SubprocessError:
        return None
    if result.returncode in {0, 1}:
        return result.returncode == 0
    return None


def scan(repo_root: Path, plugins_dir: Path) -> dict[str, Any]:
    agents_dir = repo_root / ".claude" / "agents"
    return {
        "repo_root": str(repo_root),
        "agents_dir": {
            "path": str(agents_dir),
            "exists": agents_dir.is_dir(),
            "gitignored": _is_gitignored(repo_root, agents_dir),
        },
        "agents": [asdict(a) for a in collect_agents(agents_dir)],
        "skills": [asdict(s) for s in collect_skills(repo_root, plugins_dir)],
        "commands": [asdict(c) for c in collect_commands(repo_root)],
        "toolchain": [asdict(t) for t in collect_toolchain(repo_root)],
        "claude_md": collect_claude_md(repo_root),
    }


def _surface_count(data: dict[str, Any]) -> int:
    return sum(len(data[key]) for key in ("agents", "skills", "commands", "toolchain", "claude_md"))


def _emit_json(data: dict[str, Any]) -> None:
    print(json.dumps({"data": data, "meta": {"count": _surface_count(data)}}, indent=2))


def _emit_text(data: dict[str, Any]) -> None:
    lines: list[str] = [f"Delegation surface: {data['repo_root']}", ""]

    agents_dir: dict[str, Any] = data["agents_dir"]
    state = "exists" if agents_dir["exists"] else "missing"
    if agents_dir["gitignored"]:
        state += ", GITIGNORED — agents will not travel with the repo"
    lines.append(f"Agents dir: {agents_dir['path']} ({state})")
    for agent in data["agents"]:
        tools = ", ".join(agent["tools"]) if agent["tools"] else "ALL (unrestricted)"
        lines.append(f"  - {agent['name']}  model={agent['model'] or 'inherit'}  tools={tools}")

    lines.append("")
    lines.append(f"Skills ({len(data['skills'])}):")
    for skill in data["skills"]:
        flag = "editable" if skill["editable"] else f"{skill['origin']} — do not edit in place"
        lines.append(f"  - {skill['name']}  [{flag}]  {skill['body_lines']} lines")
        lines.append(f"      {skill['path']}")

    if data["commands"]:
        lines.append("")
        lines.append(f"Commands ({len(data['commands'])}):")
        lines.extend(f"  - /{command['name']}" for command in data["commands"])

    lines.append("")
    lines.append(f"Toolchain ({len(data['toolchain'])}):")
    lines.extend(
        f"  - [{entry['kind']}] {entry['command']}  ({entry['source']})"
        for entry in data["toolchain"]
    )

    lines.append("")
    for doc in data["claude_md"]:
        marker = " (has ## Delegation)" if doc["has_delegation_section"] else ""
        lines.append(f"CLAUDE.md: {doc['path']} — {doc['lines']} lines{marker}")
        lines.extend(f"    $ {command}" for command in doc["fenced_commands"][:12])

    print("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n", 1)[0] if __doc__ else "",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              scan_delegation_targets.py .                  # readable summary
              scan_delegation_targets.py . --format json    # machine-readable
        """),
    )
    parser.add_argument("repo_root", help="Path to the repository to scan")
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="text",
        help="Output format (default: text). Use json when feeding another tool.",
    )
    parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Alias for --format json."
    )
    parser.add_argument(
        "--plugins-dir",
        default="~/.claude/plugins",
        help="Where installed plugins live; used to mark skills as plugin-sourced.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress informational stderr.")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        _error(
            f"not a directory: {repo_root}",
            "bad-invocation",
            "Pass the path to the repository you want to scan.",
        )
        return EXIT_BAD_INVOCATION

    plugins_dir = Path(args.plugins_dir).expanduser()
    try:
        data = scan(repo_root, plugins_dir)
    except OSError as exc:
        _error(f"cannot scan {repo_root}: {exc}", "system", "Check read permissions on the repo.")
        return EXIT_SYSTEM

    if args.as_json or args.format == "json":
        _emit_json(data)
    else:
        _emit_text(data)

    if _surface_count(data) == 0:
        if not args.quiet:
            _error(
                "no delegation surface found",
                "empty",
                "No skills, agents, commands, CLAUDE.md or build config under this root.",
            )
        return EXIT_EMPTY
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
