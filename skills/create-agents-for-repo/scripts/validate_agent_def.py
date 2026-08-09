#!/usr/bin/env python3
"""Validate Claude Code subagent definitions in .claude/agents/.

Checks frontmatter against the subagent spec (name shape, valid model, tool
names that resolve, enum fields) and body health (non-empty, states a return
contract). With --check-references, also fails any agent that nothing in the
repo names — an unreferenced agent is the default failure mode of adding
agents, since automatic delegation alone rarely fires for repo-specific work.

Usage:
    validate_agent_def.py <agents-dir-or-file> [--check-references REPO_ROOT]

Exit codes:
    0   All checks pass
    1   One or more FAIL-level findings
    2   Bad invocation (path missing or unreadable)
    3   No agent definition files found
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import sys
import textwrap
from typing import Any

from agents_lib import (
    KNOWN_TOOLS,
    VALID_COLORS,
    VALID_EFFORTS,
    VALID_MODELS,
    VALID_PERMISSION_MODES,
    get_list,
    get_str,
    is_model_id,
    is_valid_agent_name,
    parse_frontmatter,
    read_text,
    walk_files,
)

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_BAD_INVOCATION = 2
EXIT_EMPTY = 3

# Below this, a description is too thin to drive automatic delegation — it has
# to say when to hand work over, not just name the job.
MIN_DESCRIPTION_CHARS = 40

_TOOL_PATTERN_RE = re.compile(
    r"^(?:mcp__[\w-]+(?:__[\w*-]+)?|Agent\([\w\s,-]+\)|Task\([\w\s,-]+\))$"
)
_RETURN_CONTRACT_RE = re.compile(
    r"^#{1,4}\s*(report|output|return|response|deliverable)\b|^(report|return)\b",
    re.IGNORECASE | re.MULTILINE,
)
_REFERENCE_FILENAMES = ("CLAUDE.md", "SKILL.md", "README.md")
_WRITE_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})


def _error(message: str, code: str, hint: str) -> None:
    """Structured error on stderr — the agent gets one shape from every failure."""
    print(json.dumps({"error": message, "code": code, "hint": hint}), file=sys.stderr)


@dataclass
class Finding:
    code: str
    severity: str  # "fail" | "warn" | "info"
    message: str
    agent: str


def _check_name(frontmatter: dict[str, Any], path: Path, agent: str) -> list[Finding]:
    name = get_str(frontmatter, "name")
    if not name:
        return [Finding("agent.name.missing", "fail", "No `name` in frontmatter", agent)]
    findings: list[Finding] = []
    if ":" in name:
        findings.append(
            Finding(
                "agent.name.colon",
                "fail",
                f"`name: {name}` contains ':', reserved for plugin-scoped names — "
                "Claude Code will not load this file",
                agent,
            )
        )
    elif not is_valid_agent_name(name):
        findings.append(
            Finding(
                "agent.name.invalid",
                "fail",
                f"`name: {name}` must be lowercase letters, digits and hyphens",
                agent,
            )
        )
    if name != path.stem:
        findings.append(
            Finding(
                "agent.name.file-mismatch",
                "warn",
                f"`name: {name}` does not match filename `{path.name}` — dispatch uses the "
                "name, so the file becomes hard to find",
                agent,
            )
        )
    return findings


def _check_description(frontmatter: dict[str, Any], agent: str) -> list[Finding]:
    description = get_str(frontmatter, "description")
    if not description:
        return [
            Finding(
                "agent.description.missing",
                "fail",
                "No `description` — this is the field the main thread matches on to delegate",
                agent,
            )
        ]
    if len(description) < MIN_DESCRIPTION_CHARS:
        return [
            Finding(
                "agent.description.thin",
                "warn",
                f"Description is {len(description)} chars — say when to delegate, "
                "what the scope boundary is, and 'use proactively' if it should self-trigger",
                agent,
            )
        ]
    return []


def _check_model(frontmatter: dict[str, Any], agent: str) -> list[Finding]:
    model = get_str(frontmatter, "model")
    if model is None:
        return [
            Finding(
                "agent.model.unset",
                "warn",
                "No `model` — defaults to inherit, so the agent runs on the session's model "
                "and gives up the cost saving",
                agent,
            )
        ]
    if model not in VALID_MODELS and not is_model_id(model):
        return [
            Finding(
                "agent.model.invalid",
                "fail",
                f"`model: {model}` is not an alias ({', '.join(sorted(VALID_MODELS))}) "
                "or a full model ID",
                agent,
            )
        ]
    return []


def _check_tools(frontmatter: dict[str, Any], agent: str) -> list[Finding]:
    tools = get_list(frontmatter, "tools")
    if tools is None:
        if get_list(frontmatter, "disallowedTools") is not None:
            return []
        return [
            Finding(
                "agent.tools.unset",
                "warn",
                "No `tools` or `disallowedTools` — inherits every tool, including Write and "
                "Edit on agents meant only to report",
                agent,
            )
        ]
    if not tools:
        return [
            Finding(
                "agent.tools.empty",
                "fail",
                "`tools` is present but empty — the subagent will refuse to launch",
                agent,
            )
        ]
    unknown = [t for t in tools if t not in KNOWN_TOOLS and not _TOOL_PATTERN_RE.match(t)]
    if unknown:
        return [
            Finding(
                "agent.tools.unknown",
                "warn",
                f"Unrecognised tool name(s): {', '.join(unknown)} — if nothing in the list "
                "resolves, the subagent fails to launch",
                agent,
            )
        ]
    return []


def _check_enums(frontmatter: dict[str, Any], agent: str) -> list[Finding]:
    findings: list[Finding] = []
    for key, allowed, severity in (
        ("effort", VALID_EFFORTS, "fail"),
        ("permissionMode", VALID_PERMISSION_MODES, "fail"),
        ("color", VALID_COLORS, "warn"),
    ):
        value = get_str(frontmatter, key)
        if value is not None and value not in allowed:
            findings.append(
                Finding(
                    f"agent.{key.lower()}.invalid",
                    severity,
                    f"`{key}: {value}` is not one of {', '.join(sorted(allowed))}",
                    agent,
                )
            )
    max_turns = get_str(frontmatter, "maxTurns")
    if max_turns is not None and not max_turns.isdigit():
        findings.append(
            Finding(
                "agent.maxturns.invalid",
                "fail",
                f"`maxTurns: {max_turns}` is not an integer",
                agent,
            )
        )
    return findings


def _check_body(body: str, frontmatter: dict[str, Any], agent: str) -> list[Finding]:
    if not body.strip():
        return [
            Finding(
                "agent.body.empty",
                "fail",
                "Empty body — the body is the agent's entire system prompt",
                agent,
            )
        ]
    findings: list[Finding] = []
    if not _RETURN_CONTRACT_RE.search(body):
        findings.append(
            Finding(
                "agent.body.no-return-contract",
                "warn",
                "No Report/Return section found — without a stated output ceiling the agent "
                "hands back its evidence and the context saving disappears",
                agent,
            )
        )
    tools = get_list(frontmatter, "tools") or []
    writes = any(tool in _WRITE_TOOLS for tool in tools)
    if writes and "Bash" not in tools:
        findings.append(
            Finding(
                "agent.tools.unverified-writes",
                "warn",
                "Agent can edit files but has no Bash — it cannot run anything to prove it "
                "did not break the build",
                agent,
            )
        )
    return findings


def validate_file(path: Path) -> list[Finding]:
    agent = path.stem
    text = read_text(path)
    if text is None:
        return [Finding("agent.file.unreadable", "fail", f"Cannot read {path}", agent)]
    frontmatter, body = parse_frontmatter(text)
    if frontmatter is None:
        return [
            Finding(
                "agent.frontmatter.missing",
                "fail",
                "No YAML frontmatter — the file will not register as a subagent",
                agent,
            )
        ]
    return [
        *_check_name(frontmatter, path, agent),
        *_check_description(frontmatter, agent),
        *_check_model(frontmatter, agent),
        *_check_tools(frontmatter, agent),
        *_check_enums(frontmatter, agent),
        *_check_body(body, frontmatter, agent),
    ]


def _reference_corpus(repo_root: Path) -> list[tuple[Path, str]]:
    """Every file a reader could plausibly hit and learn the agent exists.

    Keyed by resolved path. Repos that symlink .claude to another directory
    otherwise yield each file twice under two names, and the second name stops
    the self-reference filter from recognising an agent's own definition —
    which silently passes every agent as referenced.
    """
    paths: list[Path] = []
    for filename in _REFERENCE_FILENAMES:
        paths.extend(walk_files(repo_root, filename))
    for subdir in ("commands", "agents"):
        directory = repo_root / ".claude" / subdir
        if directory.is_dir():
            paths.extend(sorted(directory.rglob("*.md")))
    corpus: list[tuple[Path, str]] = []
    for path in dict.fromkeys(p.resolve() for p in paths):
        text = read_text(path)
        if text is not None:
            corpus.append((path, text))
    return corpus


def check_references(
    repo_root: Path, agents: dict[str, Path]
) -> tuple[list[Finding], dict[str, list[str]]]:
    corpus = _reference_corpus(repo_root)
    findings: list[Finding] = []
    references: dict[str, list[str]] = {}
    for name, own_path in agents.items():
        own = own_path.resolve()
        pattern = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")
        hits = [str(path) for path, text in corpus if path != own and pattern.search(text)]
        references[name] = hits
        if not hits:
            findings.append(
                Finding(
                    "agent.refs.unreferenced",
                    "fail",
                    "Nothing in the repo names this agent — add a CLAUDE.md routing entry or a "
                    "call site in a skill, or the main thread will keep doing the work inline",
                    name,
                )
            )
    return findings, references


def _emit_json(target: Path, findings: list[Finding], references: dict[str, list[str]]) -> None:
    print(
        json.dumps(
            {
                "data": {
                    "target": str(target),
                    "findings": [asdict(f) for f in findings],
                    "references": references,
                },
                "meta": {
                    "count": len(findings),
                    "fail": sum(1 for f in findings if f.severity == "fail"),
                    "warn": sum(1 for f in findings if f.severity == "warn"),
                },
            },
            indent=2,
        )
    )


def _emit_text(target: Path, findings: list[Finding], references: dict[str, list[str]]) -> None:
    if not findings:
        print(f"PASS: {target} — {len(references) or 'all'} agent(s) valid")
    else:
        for finding in sorted(findings, key=lambda f: (f.agent, f.severity)):
            print(f"{finding.severity.upper():4}  {finding.agent}  {finding.code}")
            print(f"      {finding.message}")
    if references:
        print("\nReferenced from:")
        for name, hits in sorted(references.items()):
            print(f"  {name}: {', '.join(hits) if hits else 'NOWHERE'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n", 1)[0] if __doc__ else "",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              validate_agent_def.py .claude/agents
              validate_agent_def.py .claude/agents --check-references .
              validate_agent_def.py .claude/agents/test-runner.md --format json
        """),
    )
    parser.add_argument("target", help="Agents directory, or a single agent .md file")
    parser.add_argument(
        "--check-references",
        metavar="REPO_ROOT",
        help="Fail agents that nothing in REPO_ROOT names. This is the check that catches "
        "the usual failure: a correct agent nobody ever invokes.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="text",
        help="Output format (default: text). Use json when feeding another tool.",
    )
    parser.add_argument(
        "--json", dest="as_json", action="store_true", help="Alias for --format json."
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress informational stderr.")
    parser.add_argument(
        "--exit-on-warn", action="store_true", help="Exit 1 on warnings as well as failures"
    )
    args = parser.parse_args(argv)

    target = Path(args.target).expanduser().resolve()
    if not target.exists():
        _error(
            f"path does not exist: {target}",
            "bad-invocation",
            "Pass .claude/agents or a single agent .md file.",
        )
        return EXIT_BAD_INVOCATION

    files = [target] if target.is_file() else sorted(target.rglob("*.md"))
    if not files:
        if not args.quiet:
            _error(
                f"no agent definitions found in {target}",
                "empty",
                "Write the agent files before validating them.",
            )
        return EXIT_EMPTY

    findings: list[Finding] = []
    agents: dict[str, Path] = {}
    for path in files:
        findings.extend(validate_file(path))
        text = read_text(path)
        frontmatter, _ = parse_frontmatter(text or "")
        agents[get_str(frontmatter or {}, "name") or path.stem] = path

    references: dict[str, list[str]] = {}
    if args.check_references:
        repo_root = Path(args.check_references).expanduser().resolve()
        if not repo_root.is_dir():
            _error(
                f"not a directory: {repo_root}",
                "bad-invocation",
                "--check-references takes the repo root to search for agent mentions.",
            )
            return EXIT_BAD_INVOCATION
        reference_findings, references = check_references(repo_root, agents)
        findings.extend(reference_findings)

    if args.as_json or args.format == "json":
        _emit_json(target, findings, references)
    else:
        _emit_text(target, findings, references)

    if any(f.severity == "fail" for f in findings):
        return EXIT_FAIL
    if args.exit_on_warn and any(f.severity == "warn" for f in findings):
        return EXIT_FAIL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
