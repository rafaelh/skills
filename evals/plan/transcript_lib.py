"""How the plan harness reads an interview transcript: turns, questions, recommendations.

`drive_interview.py` records into these types and `grade.py` grades out of them. The
CLI plumbing they both also need is generic, and lives in `../shared/claude_cli.py`.

Developer harness, not something an agent calls — see README.md.
"""

# agent-tool: false

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pathlib import Path

Json = dict[str, object]

_FENCED = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_QUESTION = re.compile(r"[^.?!\n]*\?")

# Phrasings that mark an answer the user is being asked to confirm rather than supply.
# Deliberately generous: a miss here understates the skill, so the threshold that
# consumes this is a two-thirds majority rather than a clean sweep.
#
# "I'd <verb>" is taken as a lead whatever the verb, because a closed verb list turned out to
# measure the harness's vocabulary rather than the interview — round 3's transcripts led with
# "my call:", "I'd fix", "I'd reach for", "I'd leave", none of which the list knew. The
# exclusions are the phrasings where "I'd" asks for something instead of offering something.
_RECOMMENDATION = re.compile(
    r"""
    \bI(?:'d|\ would)\ (?!need|like|want|prefer\ to\ know|have\ to\ know)\w+
    | \bI\ (?:recommend|suggest|propose)\b
    | \bmy\ (?:recommendation|suggestion|take|instinct|vote|call|read|default|preference)\b
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
