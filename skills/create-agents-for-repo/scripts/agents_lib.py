"""Shared helpers for create-agents-for-repo scripts.

Imported by scan_delegation_targets.py and validate_agent_def.py. Stdlib only.
"""
# agent-tool: false

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from pathlib import Path

# Values Claude Code accepts in subagent frontmatter. `model` also accepts a full
# model ID, which is checked separately by shape rather than by membership.
VALID_MODELS = frozenset({"haiku", "sonnet", "opus", "fable", "inherit"})
VALID_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})
VALID_PERMISSION_MODES = frozenset(
    {"default", "acceptEdits", "auto", "dontAsk", "bypassPermissions", "plan", "manual"}
)
VALID_COLORS = frozenset({"red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"})

# Built-in tools grantable to a subagent. Unknown entries are warned about, not
# failed, because MCP tools and new built-ins both show up here legitimately.
KNOWN_TOOLS = frozenset(
    {
        "Agent",
        "AskUserQuestion",
        "Bash",
        "BashOutput",
        "Edit",
        "Glob",
        "Grep",
        "KillShell",
        "Monitor",
        "NotebookEdit",
        "Read",
        "Skill",
        "SlashCommand",
        "Task",
        "TodoWrite",
        "WebFetch",
        "WebSearch",
        "Write",
    }
)

# Pruned from every directory walk: large, generated, or vendored trees that
# never hold delegation surface and dominate walk time when they do get visited.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "site-packages",
        "target",
        "vendor",
        "venv",
    }
)

_FENCE_END_RE = re.compile(r"^---[ \t]*$", re.MULTILINE)
_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):[ \t]?(.*)$")
_MODEL_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+$")
_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FOLDED_MARKERS = frozenset({">", ">-", ">+", "|", "|-", "|+"})


def is_valid_agent_name(name: str) -> bool:
    return bool(_NAME_RE.match(name))


def is_model_id(value: str) -> bool:
    """True for full model IDs like `claude-opus-5`, as distinct from aliases."""
    return bool(_MODEL_ID_RE.match(value))


def parse_frontmatter(text: str) -> tuple[dict[str, Any] | None, str]:
    """Return (frontmatter, body), or (None, text) when there is no frontmatter.

    Covers the YAML subset that appears in agent and skill frontmatter: scalars,
    quoted scalars, inline `[a, b]` lists, block `- item` lists, one level of
    nesting, folded/block scalars, and plain multi-line scalars continued by
    indentation — which agent `description` fields use constantly.
    """
    if not text.startswith("---") or len(text) < 4 or text[3] not in "\n\r":
        return None, text
    match = _FENCE_END_RE.search(text, 3)
    if not match:
        return None, text
    return _parse_yaml_subset(text[3 : match.start()].strip("\r\n")), text[match.end() :]


def _parse_yaml_subset(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        match = _KEY_RE.match(line)
        if not match:
            index += 1
            continue
        key, raw = match.group(1), match.group(2).rstrip()
        block, index = _collect_indented(lines, index + 1)
        result[key] = _value_for(raw, block)
    return result


def _value_for(raw: str, block: list[str]) -> Any:
    if raw in _FOLDED_MARKERS:
        separator = " " if raw.startswith(">") else "\n"
        return separator.join(line.strip() for line in block)
    if raw:
        # A plain scalar followed by indented lines is one wrapped value.
        scalar = " ".join([raw, *(line.strip() for line in block)]) if block else raw
        return _strip_quotes(scalar)
    if block and block[0].lstrip().startswith("- "):
        return [_strip_quotes(line.lstrip()[2:].strip()) for line in block]
    nested: dict[str, str] = {}
    for line in block:
        entry = _KEY_RE.match(line.strip())
        if entry:
            nested[entry.group(1)] = _strip_quotes(entry.group(2).strip())
    return nested or ""


def _collect_indented(lines: list[str], start: int) -> tuple[list[str], int]:
    """Return (non-blank indented lines following *start*, index after them)."""
    collected: list[str] = []
    index = start
    while index < len(lines) and (lines[index].startswith((" ", "\t")) or not lines[index].strip()):
        if lines[index].strip():
            collected.append(lines[index])
        index += 1
    return collected, index


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def get_str(frontmatter: dict[str, Any], key: str) -> str | None:
    """Frontmatter value as a string, or None when absent or not scalar."""
    value = frontmatter.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def get_list(frontmatter: dict[str, Any], key: str) -> list[str] | None:
    """Frontmatter value as a list, accepting `[a, b]`, `a, b`, and block lists.

    Returns an empty list when the key is present but holds nothing — the caller
    needs that distinct from absent, because `tools:` with no entries stops the
    subagent launching while an omitted `tools:` inherits everything.
    """
    value = frontmatter.get(key)
    if value is None:
        return None
    if isinstance(value, list):
        items = cast("list[object]", value)
        return [str(item).strip() for item in items if str(item).strip()]
    if not isinstance(value, str):
        return []
    text = value.strip().removeprefix("[").removesuffix("]")
    return [item.strip() for item in text.split(",") if item.strip()]


def walk_files(root: Path, filename: str, max_depth: int = 4) -> list[Path]:
    """Find *filename* under *root*, pruning SKIP_DIRS and stopping at max_depth."""
    found: list[Path] = []
    frontier = [(root, 0)]
    while frontier:
        directory, depth = frontier.pop()
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if depth < max_depth and entry.name not in SKIP_DIRS:
                    frontier.append((entry, depth + 1))
            elif entry.name == filename:
                found.append(entry)
    return sorted(found)


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return None
