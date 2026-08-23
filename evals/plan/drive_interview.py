"""Run one plan-skill eval: an interviewer talks to a scripted user until the plan is settled.

    drive_interview.py <eval-name-or-id> --arm with_skill|without_skill --out <run-dir>

The interviewer is a Claude CLI session with read-only access to a copy of the eval's
fixture repo. The user is a second, stateless CLI call given the eval's persona brief and
the conversation so far. The two arms differ in exactly one thing: whether the plan
skill's body is appended to the interviewer's system prompt.

Writes `<run-dir>/transcript.json`, `<run-dir>/outputs/transcript.md`,
`<run-dir>/eval_metadata.json` and `<run-dir>/timing.json`. Grade it with `grade.py <run-dir>`.

Developer harness, not something an agent calls — see README.md.
"""

# agent-tool: false

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import cast

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))

from claude_cli import READ_ONLY_TOOLS, run_claude
from transcript_lib import Transcript, Turn, question_sentences
from workspace import find_case, load_cases, stage_fixture, write_eval_metadata, write_timing

DEFAULT_SKILL = HERE.parent.parent / "skills" / "plan" / "SKILL.md"

# Given to both arms. The interviewer has to know it is in a conversation and cannot
# reach for a shell, or it burns turns trying to run things and being denied. Identical
# either way, so the only variable between arms stays the skill body itself.
SITUATION = """You are in a text conversation with a user about work they are planning.
You cannot run commands, write files, or edit anything in this conversation — replies and
read-only inspection are all you have. Reply as you would in a chat: no file output, no
tool-shaped deliverables."""

REPO_SITUATION = """Your working directory holds the codebase the user is talking about.
You can read it with Read, Grep and Glob."""

SKILL_FRAME = """The following skill is active for this conversation. Follow it.

---
"""

PERSONA_RULES = """You are role-playing the user in a planning conversation. Stay in
character the whole time.

How to reply:
- Answer only what you were actually asked. Do not volunteer the rest of your situation.
- One to three sentences. You are typing into a chat box, not writing a document.
- If you are given a recommendation you have no strong view on, take it, briefly.
- If you are asked something your brief does not cover, invent something small and
  consistent with the brief rather than stalling.
- If you are asked whether to start implementing, write code, or write tests, decline —
  you only want the plan settled for now.
- If the last message asked you nothing, reply with a short acknowledgement.
- Never mention that you are role-playing, never quote or describe your brief, and never
  write stage directions or narration. Output only what you say.
"""


def skill_body(skill_md: Path) -> str:
    """SKILL.md with its YAML frontmatter removed — the part a triggered skill contributes."""
    text = skill_md.read_text()
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4 :]
    return text.strip()


def persona_reply(brief: str, transcript: Transcript, model: str, cwd: Path) -> Turn:
    history = "\n\n".join(
        f"{'THEM' if t.role == 'assistant' else 'YOU'}: {t.text.strip()}" for t in transcript.turns
    )
    prompt = (
        f"{PERSONA_RULES}\n\n## Your brief\n\n{brief}\n\n"
        f"## The conversation so far\n\n{history}\n\n"
        "Reply now, as the user, in your own words."
    )
    result = run_claude(prompt, cwd=cwd, model=model, timeout=300)
    return Turn(
        role="user",
        text=result.text.strip().strip('"'),
        tokens=result.tokens,
        duration_ms=result.duration_ms,
        cost_usd=result.cost_usd,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eval", help="eval name or id from evals.json")
    parser.add_argument(
        "--arm",
        choices=["with_skill", "without_skill", "old_skill"],
        required=True,
        help="every arm but without_skill gets --skill appended to its system prompt",
    )
    parser.add_argument("--out", required=True, help="run directory to write into")
    parser.add_argument("--evals", default=str(HERE / "evals.json"))
    parser.add_argument(
        "--skill",
        default=str(DEFAULT_SKILL),
        help="SKILL.md to test; point old_skill at a snapshot",
    )
    parser.add_argument("--model", default="sonnet", help="model under test")
    parser.add_argument("--persona-model", default="sonnet")
    parser.add_argument("--max-turns", type=int, default=12)
    args = parser.parse_args()

    _, cases = load_cases(Path(args.evals))
    case = find_case(cases, args.eval)
    out_dir = Path(args.out)
    (out_dir / "outputs").mkdir(parents=True, exist_ok=True)

    fixture = cast("str | None", case.get("fixture"))
    repo = stage_fixture(HERE / "fixtures" / fixture if fixture else None, out_dir / "repo")
    scratch = out_dir / "persona"
    scratch.mkdir(exist_ok=True)

    system = SITUATION + ("\n\n" + REPO_SITUATION if fixture else "")
    if args.arm != "without_skill":
        system += "\n\n" + SKILL_FRAME + skill_body(Path(args.skill))

    brief = (HERE / "personas" / str(case["persona"])).read_text()

    transcript = Transcript(
        eval_name=str(case["name"]),
        arm=args.arm,
        model=args.model,
        persona_model=args.persona_model,
        stop_reason="max_turns",
    )
    transcript.turns.append(Turn(role="user", text=str(case["prompt"])))

    session_id: str | None = None
    message = str(case["prompt"])

    for turn_no in range(1, args.max_turns + 1):
        result = run_claude(
            message,
            cwd=repo,
            model=args.model,
            system_prompt=system,
            session_id=session_id,
            allowed_tools=READ_ONLY_TOOLS,
            timeout=900,
        )
        session_id = result.session_id or session_id
        transcript.turns.append(
            Turn(
                role="assistant",
                text=result.text,
                tools=result.tools,
                tokens=result.tokens,
                duration_ms=result.duration_ms,
                cost_usd=result.cost_usd,
            )
        )
        print(f"[{case['name']}/{args.arm}] turn {turn_no}: {len(result.text)} chars", flush=True)

        # An interviewer with nothing left to ask is an interviewer that has finished.
        if not question_sentences(result.text):
            transcript.stop_reason = "no_question"
            break

        reply = persona_reply(brief, transcript, args.persona_model, scratch)
        transcript.turns.append(reply)
        message = reply.text

    interviewer = transcript.assistant_turns()
    persona_turns = [t for t in transcript.turns if t.role == "user" and t.tokens]

    (out_dir / "transcript.json").write_text(json.dumps(transcript.to_json(), indent=2))
    (out_dir / "outputs" / "transcript.md").write_text(transcript.to_markdown())
    write_eval_metadata(
        out_dir,
        case,
        args.arm,
        {
            "code_bearing": case["code_bearing"],
            "model": args.model,
            "stop_reason": transcript.stop_reason,
            "interviewer_turns": len(interviewer),
        },
    )
    write_timing(
        out_dir,
        total_tokens=sum(t.tokens for t in interviewer),
        duration_ms=sum(t.duration_ms for t in interviewer),
        cost_usd=sum(t.cost_usd for t in interviewer),
        extra={
            # The simulated user is harness overhead, not the skill's cost, so it is
            # recorded beside the run's own figures rather than added to them.
            "persona_tokens": sum(t.tokens for t in persona_turns),
            "persona_cost_usd": round(sum(t.cost_usd for t in persona_turns), 4),
        },
    )
    print(
        f"[{case['name']}/{args.arm}] done: {len(interviewer)} turns, "
        f"stop={transcript.stop_reason}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
