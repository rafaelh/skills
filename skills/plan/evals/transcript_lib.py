"""Shared pieces of the plan-skill eval harness: CLI invocation and transcript analysis.

Both `drive_interview.py` and `grade.py` need to shell out to the Claude CLI and to
decide what counts as a question, so those live here rather than in either script.

Developer harness, not something an agent calls — see README.md.
"""

# agent-tool: false

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import cast

Json = dict[str, object]

# The interviewer may look at the repo but may not change it or escape into
# another agent. Blocking Skill matters most: without it the no-skill arm can
# load the plan skill on its own and stop being a baseline.
READ_ONLY_TOOLS = ["Read", "Grep", "Glob"]
BLOCKED_TOOLS = [
    "Bash",
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "Task",
    "Skill",
    "SlashCommand",
    "WebFetch",
    "WebSearch",
    "TodoWrite",
]

_FENCED = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_QUESTION = re.compile(r"[^.?!\n]*\?")

# Phrasings that mark an answer the user is being asked to confirm rather than supply.
# Deliberately generous: a miss here understates the skill, so the threshold that
# consumes this is a two-thirds majority rather than a clean sweep.
_RECOMMENDATION = re.compile(
    r"""
    \bI(?:'d|\ would)\ (?:recommend|suggest|propose|go\ with|default|pick|lean|start|keep|
        drop|replace|use|treat|split|say|argue)\b
    | \bI\ (?:recommend|suggest|propose)\b
    | \bmy\ (?:recommendation|suggestion|take|instinct|vote)\b
    | \brecommend(?:ation|ed\ answer)\s*:
    | \blet'?s\ go\ with\b
    | \bthe\ (?:right|better|safer|obvious)\ (?:answer|call|choice|default)\ (?:here\ )?is\b
    | \bI\ think\ (?:we|you)\ should\b
    | \bproposed\b\s*:
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass
class Turn:
    role: str
    text: str
    tools: list[str] = field(default_factory=list[str])
    tokens: int = 0
    duration_ms: int = 0
    cost_usd: float = 0.0


@dataclass
class Transcript:
    eval_name: str
    arm: str
    model: str
    persona_model: str
    stop_reason: str
    turns: list[Turn] = field(default_factory=list[Turn])

    def assistant_turns(self) -> list[Turn]:
        return [t for t in self.turns if t.role == "assistant"]

    def to_json(self) -> Json:
        return cast("Json", asdict(self))

    def to_markdown(self) -> str:
        lines = [f"# {self.eval_name} — {self.arm}", ""]
        lines.append(f"_model: {self.model} · stop: {self.stop_reason}_")
        lines.append("")
        n = 0
        for turn in self.turns:
            if turn.role == "assistant":
                n += 1
                lines.append(f"## Interviewer — turn {n}")
            else:
                lines.append("## User")
            lines.append("")
            if turn.tools:
                lines.append("_looked at: " + ", ".join(f"`{t}`" for t in turn.tools) + "_")
                lines.append("")
            lines.append(turn.text.strip())
            lines.append("")
        return "\n".join(lines)

    @classmethod
    def load(cls, path: Path) -> Transcript:
        raw = cast("Json", json.loads(path.read_text()))
        turns: list[Turn] = []
        for item in cast("list[object]", raw["turns"]):
            t = cast("Json", item)
            turns.append(
                Turn(
                    role=str(t["role"]),
                    text=str(t["text"]),
                    tools=[str(x) for x in cast("list[object]", t.get("tools", []))],
                    tokens=int(cast("int", t.get("tokens", 0))),
                    duration_ms=int(cast("int", t.get("duration_ms", 0))),
                    cost_usd=float(cast("float", t.get("cost_usd", 0.0))),
                )
            )
        return cls(
            eval_name=str(raw["eval_name"]),
            arm=str(raw["arm"]),
            model=str(raw["model"]),
            persona_model=str(raw["persona_model"]),
            stop_reason=str(raw["stop_reason"]),
            turns=turns,
        )


def prose(text: str) -> str:
    """Text with code stripped, so a `?` inside a snippet is not read as a question."""
    return _INLINE_CODE.sub(" ", _FENCED.sub(" ", text))


def question_sentences(text: str) -> list[str]:
    """Sentences ending in a question mark, outside code.

    A proxy, not a parser: a rhetorical "Why? Because…" counts as a question here.
    Every check built on this reports the sentences it matched so a human can see
    what tripped it.
    """
    return [m.group(0).strip() for m in _QUESTION.finditer(prose(text)) if m.group(0).strip()]


def has_recommendation(text: str) -> bool:
    return _RECOMMENDATION.search(prose(text)) is not None


def word_count(text: str) -> int:
    return len(prose(text).split())


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


def _tool_summary(name: str, tool_input: Json, root: Path) -> str:
    for key in ("file_path", "path", "pattern"):
        value = tool_input.get(key)
        if isinstance(value, str):
            target = Path(value)
            if target.is_absolute() and target.is_relative_to(root):
                value = str(target.relative_to(root))
            return f"{name} {value}"
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
    allow_tools: bool = False,
    timeout: int = 600,
) -> CliResult:
    """One CLI turn. Returns the assistant's text plus what it cost to get it."""
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
        *BLOCKED_TOOLS,
    ]
    if allow_tools:
        argv += ["--allowed-tools", *READ_ONLY_TOOLS]
    if system_prompt:
        argv += ["--append-system-prompt", system_prompt]
    if session_id:
        argv += ["--resume", session_id]

    proc = subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
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
                        _tool_summary(str(blk.get("name")), cast("Json", blk.get("input", {})), cwd)
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
