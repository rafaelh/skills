"""One turn of the Claude CLI, in and out — the plumbing under any scripted eval run.

Used by drivers that hold a conversation with the thing under test, and by the
model-graded half of a rubric. Suites whose runs are launched as subagents never
touch it.

Developer harness, not something an agent calls — see ../eval-approach.md.
"""

# agent-tool: false

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

Json = dict[str, object]

# What a run under test may reach for. Blocking Skill matters most: without it the
# without_skill arm can load the skill on its own and stop being a baseline.
READ_ONLY_TOOLS = ("Read", "Grep", "Glob")
EDITING_TOOLS = ("Read", "Grep", "Glob", "Edit", "Write", "Bash")

# Blocked in every arm whatever else a suite grants, because each of these is a way
# back to the skill under test or to the wider machine. A suite that hands a run
# write access still starts from this list.
ISOLATION_BLOCKED_TOOLS = ("Task", "Skill", "SlashCommand", "WebFetch", "WebSearch")
BLOCKED_TOOLS = (
    "Bash",
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "TodoWrite",
    *ISOLATION_BLOCKED_TOOLS,
)


def cli_path() -> str:
    """The Claude CLI this harness drives.

    Claude Code sets CLAUDE_CODE_EXECPATH when it runs; outside it, `claude` on PATH.
    """
    exec_path = os.environ.get("CLAUDE_CODE_EXECPATH")
    if exec_path and Path(exec_path).exists():
        return exec_path
    found = shutil.which("claude")
    if found:
        return found
    raise RuntimeError("no Claude CLI found — set CLAUDE_CODE_EXECPATH or put `claude` on PATH")


@dataclass
class CliResult:
    text: str
    session_id: str
    tools: list[str]
    tokens: int
    duration_ms: int
    cost_usd: float


# How much of a tool's argument the log keeps. A suite grading *what* a Bash call did
# raises it: an inline timing script prefixed with a `cd` into an absolute workspace path
# spends its first 150 characters before reaching the part a check reads.
TOOL_SUMMARY_CHARS = 200


def _tool_summary(name: str, tool_input: Json, root: Path, limit: int) -> str:
    # `command` last and truncated: it is what a Bash call actually did, which is the
    # difference between "ran the suite between edits" and "ran a linter that is not
    # configured here" — invisible when only the tool name is recorded.
    for key in ("file_path", "path", "pattern", "command"):
        value = tool_input.get(key)
        if isinstance(value, str):
            target = Path(value)
            if target.is_absolute() and target.is_relative_to(root):
                value = str(target.relative_to(root))
            return f"{name} {value[:limit].replace(chr(10), ' ')}"
    return name


def _usage_tokens(usage: Json) -> int:
    keys = (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    )
    return sum(int(cast("int", usage.get(k, 0))) for k in keys)


def run_claude(
    prompt: str,
    *,
    cwd: Path,
    model: str,
    system_prompt: str | None = None,
    session_id: str | None = None,
    allowed_tools: Sequence[str] | None = None,
    disallowed_tools: Sequence[str] = BLOCKED_TOOLS,
    permission_mode: str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: int = 600,
    tool_summary_chars: int = TOOL_SUMMARY_CHARS,
) -> CliResult:
    """One CLI turn. Returns the assistant's text plus what it cost to get it.

    `env` is merged over the harness's own environment rather than replacing it, so a
    suite can put a stand-in binary first on PATH — the az suite's fake CLI — without
    having to reconstruct everything the Claude CLI needs to start.
    """
    argv = [
        cli_path(),
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        # Without this the run inherits whoever's machine it is on — their global
        # CLAUDE.md, their skills, their MCP servers — and stops being comparable
        # to the same eval run anywhere else. Auth and built-in tools still work.
        "--safe-mode",
        "--model",
        model,
        "--disallowed-tools",
        *disallowed_tools,
    ]
    if allowed_tools:
        argv += ["--allowed-tools", *allowed_tools]
    if permission_mode:
        # A suite that hands the run write tools also has to say edits are pre-approved:
        # there is no one at the terminal to answer a permission prompt, and the run
        # stalls until the timeout instead of failing.
        argv += ["--permission-mode", permission_mode]
    if system_prompt:
        argv += ["--append-system-prompt", system_prompt]
    if session_id:
        argv += ["--resume", session_id]

    proc = subprocess.run(
        argv,
        cwd=cwd,
        env={**os.environ, **env} if env else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        # The CLI reports the reason on stdout as a result event, not on stderr, so a
        # failure looks like silence unless both are carried into the message.
        raise RuntimeError(
            f"claude exited {proc.returncode}\nstderr: {proc.stderr[-1000:]}"
            f"\nstdout: {proc.stdout[-1500:]}"
        )

    text_parts: list[str] = []
    tools: list[str] = []
    result: Json = {}
    for raw_line in proc.stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = cast("Json", json.loads(line))
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "assistant":
            message = cast("Json", event.get("message", {}))
            for block in cast("list[object]", message.get("content", [])):
                blk = cast("Json", block)
                if blk.get("type") == "text":
                    text_parts.append(str(blk.get("text", "")))
                elif blk.get("type") == "tool_use":
                    tools.append(
                        _tool_summary(
                            str(blk.get("name")),
                            cast("Json", blk.get("input", {})),
                            cwd,
                            tool_summary_chars,
                        )
                    )
        elif kind == "result":
            result = event

    if not result:
        raise RuntimeError(f"no result event in CLI output: {proc.stdout[-2000:]}")

    return CliResult(
        text="\n\n".join(p for p in text_parts if p.strip()),
        session_id=str(result.get("session_id", "")),
        tools=tools,
        tokens=_usage_tokens(cast("Json", result.get("usage", {}))),
        duration_ms=int(cast("int", result.get("duration_ms", 0))),
        cost_usd=float(cast("float", result.get("total_cost_usd", 0.0))),
    )


def extract_json_array(text: str) -> list[Json]:
    """Pull a JSON array out of a model reply that may be fenced or prefaced."""
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end <= start:
            raise ValueError(f"no JSON array in reply: {text[:500]}")
        candidate = text[start : end + 1]
    return [cast("Json", item) for item in cast("list[object]", json.loads(candidate))]
