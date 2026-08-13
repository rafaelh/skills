"""Score one plan-skill eval run against its assertions.

    grade.py <run-dir> [--mechanical-only] [--grader-model sonnet]

Reads `<run-dir>/transcript.json` and writes `<run-dir>/grading.json` in the shape the
skill-creator eval viewer expects. Two kinds of check:

- **Mechanical** — computed here from the transcript. Cheap, deterministic, rerunnable.
  They are proxies (see `question_sentences`), so every one reports what it matched.
- **Judgement** — the per-eval statements in `evals.json`, sent to a grader model with
  the transcript and no clue which arm produced it.

Developer harness, not something an agent calls — see README.md.
"""

# agent-tool: false

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
from typing import cast

from transcript_lib import (
    Json,
    Transcript,
    extract_json_array,
    has_recommendation,
    prose,
    question_sentences,
    run_claude,
    word_count,
)

HERE = Path(__file__).resolve().parent

# An unaided model answering "help me plan X" tends to reply with the plan. The budget is
# set well above a recommendation-plus-question turn and well below a plan document.
# Calibrated on round 1's first turns: unaided runs came in at 516, 632 and 667 words, the
# skill at 165-292. Raised from 350 for round 2, because the skill now opens by stating the
# calls it made itself before asking, which is longer by design — an unmodified 350 would have
# failed it at 351 words for doing the thing it was told to do. Still clears every dump.
OPENING_WORD_BUDGET = 450

# Two thirds rather than all of them: the recommendation regex is a keyword match and will
# miss valid phrasings, so a clean sweep would measure vocabulary, not behaviour.
RECOMMENDATION_MAJORITY = 2 / 3

# A run that answers with a finished plan and asks nothing also stops without hitting the
# turn cap, and would otherwise score as a completed interview. Every persona here holds at
# least four open decisions, so no honest interview settles them in fewer turns than this.
MIN_INTERVIEW_TURNS = 3

# Half rather than two thirds: this phrasing set is narrower than the recommendation one, so a
# higher bar would measure how many ways the harness knows to say "or something else".
OPEN_DOOR_MAJORITY = 1 / 2
OPEN_DOOR = re.compile(
    r"""
      or\ something\ (else|different)
    | or\ (is\ there|do\ you\ have|would\ you\ (rather|prefer))
    | or\ (a\ )?(third|another|some\ other)\ (option|answer|approach)
    | if\ (neither|none\ of|that'?s\ not|it'?s\ neither)
    | (push\ back|redirect\ me|tell\ me\ if|let\ me\ know\ if|say\ so)
    | (something|an\ option)\ I\ (haven'?t|have\ not)\ (listed|thought)
    | (shout|flag\ it)\ if
    | if\ you\ have\ (a\ )?(different|another|other)
    """,
    re.IGNORECASE | re.VERBOSE,
)

TDD_OFFER = re.compile(r"(?i)(/tdd\b|\btdd\b|test.driven development)")
BUILD_HANDOFF = re.compile(
    r"(?i)(/tdd\b|\btdd\b|test.driven"
    r"|drive the implementation|start (implementing|building|coding)"
    r"|want me to (write|build|implement|code)"
    r"|shall i (write|build|implement|code))"
)
# Anchored on an actual file, not on "write it up" — in a postmortem interview that phrase means
# writing the postmortem, and it was passing this check for both arms.
PLAN_FILE_OFFER = re.compile(
    r"(?i)((write|save|drop|put|dump)[^.?!\n]{0,40}\b(to|into|as|in)\s+(an?|the)\s+"
    r"(markdown\s+|\.md\s+|separate\s+)*(file|doc\w*)"
    r"|markdown file|plan (file|document)\b|(file|doc\w*)[^.?!\n]{0,40}fresh context)"
)

SHARED_JUDGEMENT = [
    "Every question put to the user is a real decision — none where one option is clearly right "
    "and the listed alternatives are strawmen",
    "Where a turn asks about more than one decision, those decisions are independent of each "
    "other rather than one depending on the answer to another in the same turn",
    "Every question states a recommended answer and a short rationale before asking the user "
    "to confirm or redirect it",
    "Choices are framed by what they change for the user, not by the name of the mechanism, so "
    "the impact is legible to someone who does not know the jargon",
    "Questions are asked in a way that accepts an answer the interviewer did not list, rather "
    "than forcing the user to pick from a closed menu",
    "Questions pin down a specific choice rather than inviting open-ended description",
    "The first question addresses a decision that constrains later ones, not a leaf detail",
    "Decisions opened up by the user's answers are picked up later rather than dropped",
    "Where two options both work, the recommendation favours the one leaving less to maintain, "
    "and says what that option gives up",
    "The plan is one the user agreed to decision by decision, not one handed to them",
]

GRADER_PROMPT = """You are grading a transcript of a planning interview. Someone was asked
to help a user plan a piece of work, and did it by interviewing them.

Judge each numbered assertion below against the transcript, and nothing else.

- Decide on what the transcript shows, not on what the interviewer seemed to intend.
- Evidence must quote the specific turn that settles it. Say which turn.
- If the interview never went far enough to demonstrate an assertion, it fails, and the
  evidence should say so.
- An assertion about "every question" fails if any single question breaks it.

## Assertions

{assertions}

## Transcript

{transcript}

Return only a JSON array, one object per assertion, in order:
[{{"index": 1, "passed": true, "evidence": "Turn 2 says ..."}}]
"""


def expectation(text: str, passed: bool, evidence: str) -> Json:
    return {"text": text, "passed": passed, "evidence": evidence}


def check_opening(transcript: Transcript) -> Json:
    turns = transcript.assistant_turns()
    text = "Opens by asking something rather than by delivering a finished plan"
    if not turns:
        return expectation(text, False, "The interviewer never replied.")
    first = turns[0]
    words = word_count(first.text)
    questions = question_sentences(first.text)
    passed = words <= OPENING_WORD_BUDGET and bool(questions)
    return expectation(
        text,
        passed,
        f"First turn is {words} words (budget {OPENING_WORD_BUDGET}) and contains "
        f"{len(questions)} question(s)."
        + (f" First: {questions[0]!r}" if questions else " It asked nothing."),
    )


def check_open_door(transcript: Transcript) -> Json:
    """Bundling is fine when the decisions are real; a closed menu of options is not.

    Replaces a one-question-per-turn check, which measured the wrong thing — see benchmark.md.
    """
    text = "Questions leave room for an answer the interviewer did not list"
    asking = [t for t in transcript.assistant_turns() if question_sentences(t.text)]
    if not asking:
        return expectation(text, False, "No turn asked a question.")
    open_turns = [i for i, t in enumerate(asking, start=1) if OPEN_DOOR.search(prose(t.text))]
    ratio = len(open_turns) / len(asking)
    return expectation(
        text,
        ratio >= OPEN_DOOR_MAJORITY,
        f"{len(open_turns)} of {len(asking)} question turns invite an unlisted answer "
        f"({ratio:.0%}; threshold {OPEN_DOOR_MAJORITY:.0%}).",
    )


def check_recommendation(transcript: Transcript) -> Json:
    text = "Question turns carry an explicit recommendation rather than a bare question"
    asking = [t for t in transcript.assistant_turns() if question_sentences(t.text)]
    if not asking:
        return expectation(text, False, "No turn asked a question.")
    led = [i for i, t in enumerate(asking, start=1) if has_recommendation(t.text)]
    ratio = len(led) / len(asking)
    return expectation(
        text,
        ratio >= RECOMMENDATION_MAJORITY,
        f"{len(led)} of {len(asking)} question turns state a recommendation "
        f"({ratio:.0%}; threshold {RECOMMENDATION_MAJORITY:.0%}). "
        f"Turns without one: {[i for i in range(1, len(asking) + 1) if i not in led] or 'none'}.",
    )


def check_termination(transcript: Transcript) -> Json:
    text = "Holds a real interview and reaches its own stopping point"
    turns = len(transcript.assistant_turns())
    passed = transcript.stop_reason == "no_question" and turns >= MIN_INTERVIEW_TURNS
    return expectation(
        text,
        passed,
        f"Stopped after {turns} turns (minimum {MIN_INTERVIEW_TURNS}), reason "
        f"{transcript.stop_reason!r}.",
    )


def check_read_first(transcript: Transcript) -> Json:
    text = "Reads the repository before asking its first question"
    turns = transcript.assistant_turns()
    if not turns:
        return expectation(text, False, "The interviewer never replied.")
    tools = turns[0].tools
    return expectation(
        text,
        bool(tools),
        f"First turn used {len(tools)} read tool call(s): {tools[:6] or 'none'}.",
    )


def check_repo_answers(transcript: Transcript, case: Json) -> Json:
    text = "Asks nothing the repository already answers"
    answers = [cast("Json", a) for a in cast("list[object]", case.get("repo_answers", []))]
    # A run that barely asks anything cannot ask a bad question, and was passing this for free.
    if len(transcript.assistant_turns()) < MIN_INTERVIEW_TURNS:
        return expectation(
            text,
            False,
            f"Only {len(transcript.assistant_turns())} turns — never held an interview, so "
            "there was nothing to get right here.",
        )
    violations: list[str] = []
    for i, turn in enumerate(transcript.assistant_turns(), start=1):
        asked = " ".join(question_sentences(turn.text))
        for answer in answers:
            match = re.search(str(answer["pattern"]), asked)
            if match:
                violations.append(f"turn {i} asked about {answer['label']}: {match.group(0)!r}")
    if violations:
        return expectation(text, False, "; ".join(violations[:4]))
    return expectation(
        text,
        True,
        f"None of the {len(answers)} repo-answerable topics were put to the user as questions.",
    )


def check_plan_file_offer(transcript: Transcript) -> Json:
    """Every settled plan, code-bearing or not, is worth more in a fresh context window."""
    body = prose("\n".join(t.text for t in transcript.assistant_turns()))
    match = PLAN_FILE_OFFER.search(body)
    return expectation(
        "Offers to write the settled plan out to a file",
        match is not None,
        f"Found {match.group(0)!r}." if match else "Never offered to write the plan out.",
    )


def check_tdd_handoff(transcript: Transcript, case: Json) -> Json:
    body = "\n".join(t.text for t in transcript.assistant_turns())
    if bool(case["code_bearing"]):
        match = TDD_OFFER.search(body)
        return expectation(
            "Offers the TDD handoff once the plan is settled",
            match is not None,
            f"Found {match.group(0)!r}." if match else "No TDD handoff anywhere in the interview.",
        )
    match = BUILD_HANDOFF.search(body)
    return expectation(
        "Offers no implementation or TDD handoff for a plan that produces no code",
        match is None,
        f"Offered to build something: {match.group(0)!r}."
        if match
        else "No implementation handoff offered.",
    )


def mechanical(transcript: Transcript, case: Json) -> list[Json]:
    checks = [
        check_opening(transcript),
        check_open_door(transcript),
        check_recommendation(transcript),
        check_termination(transcript),
        check_plan_file_offer(transcript),
        check_tdd_handoff(transcript, case),
    ]
    if case.get("fixture"):
        checks.append(check_read_first(transcript))
        checks.append(check_repo_answers(transcript, case))
    return checks


def blind_transcript(transcript: Transcript) -> str:
    """The conversation with the arm label and tool noise removed, so grading stays blind."""
    lines: list[str] = []
    n = 0
    for turn in transcript.turns:
        if turn.role == "assistant":
            n += 1
            lines.append(f"### Interviewer, turn {n}\n\n{turn.text.strip()}\n")
        else:
            lines.append(f"### User\n\n{turn.text.strip()}\n")
    return "\n".join(lines)


def judgement(transcript: Transcript, case: Json, model: str, cwd: Path) -> list[Json]:
    statements = SHARED_JUDGEMENT + [
        str(j) for j in cast("list[object]", case.get("judgement", []))
    ]
    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(statements, start=1))
    prompt = GRADER_PROMPT.format(assertions=numbered, transcript=blind_transcript(transcript))
    result = run_claude(prompt, cwd=cwd, model=model, allow_tools=False, timeout=600)
    verdicts = extract_json_array(result.text)
    by_index = {int(cast("int", v["index"])): v for v in verdicts if "index" in v}

    out: list[Json] = []
    for i, statement in enumerate(statements, start=1):
        verdict = by_index.get(i)
        if verdict is None:
            out.append(expectation(statement, False, "The grader returned no verdict."))
            continue
        out.append(
            expectation(statement, bool(verdict.get("passed")), str(verdict.get("evidence", "")))
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    parser.add_argument("--evals", default=str(HERE / "evals.json"))
    parser.add_argument("--grader-model", default="sonnet")
    parser.add_argument(
        "--mechanical-only", action="store_true", help="skip the model-graded assertions"
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    transcript_path = run_dir / "transcript.json"
    if not transcript_path.exists():
        print(f"error: no transcript at {transcript_path}", file=sys.stderr)
        return 1
    transcript = Transcript.load(transcript_path)

    data = cast("Json", json.loads(Path(args.evals).read_text()))
    cases = [cast("Json", c) for c in cast("list[object]", data["evals"])]
    case = next((c for c in cases if str(c["name"]) == transcript.eval_name), None)
    if case is None:
        print(f"error: {transcript.eval_name!r} is not in {args.evals}", file=sys.stderr)
        return 1

    expectations = mechanical(transcript, case)
    if not args.mechanical_only:
        expectations += judgement(transcript, case, args.grader_model, run_dir)

    passed = sum(1 for e in expectations if e["passed"])
    total = len(expectations)
    tool_calls = Counter(t.split()[0] for turn in transcript.assistant_turns() for t in turn.tools)

    # No timing block here on purpose: skill-creator's aggregator only falls through to
    # the run's timing.json — the one place token counts live — when grading.json has none.
    grading: Json = {
        "expectations": expectations,
        "summary": {
            "passed": passed,
            "failed": total - passed,
            "total": total,
            "pass_rate": round(passed / total, 3) if total else 0.0,
        },
        "execution_metrics": {
            "tool_calls": dict(tool_calls),
            "total_tool_calls": sum(tool_calls.values()),
            "total_steps": len(transcript.assistant_turns()),
            "errors_encountered": 0,
            "output_chars": sum(len(t.text) for t in transcript.assistant_turns()),
        },
    }
    (run_dir / "grading.json").write_text(json.dumps(grading, indent=2))
    print(f"{transcript.eval_name}/{transcript.arm}: {passed}/{total} passed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
