#!/usr/bin/env python3
"""Score one review-repo-agents run, and write its `grading.json`.

    grade.py <run-dir> [--model sonnet] [--no-judge]

The artifact here is prose — `outputs/report.md` — so the rubric leans on its judgement
half. The mechanical checks below grade the report's *shape*: whether it covered every
agent on disk, reached a verdict on each, opened the files it is judging, quoted them
rather than paraphrasing, and stayed within the budget the case allows. What it actually
found is left to a grader model, blind to which arm it is reading.

Every mechanical check reports what it matched, pass or fail, because every one is a
proxy — a verdict verb near an agent's name is not a verdict.

Developer harness, not something an agent calls — see README.md.
"""

# agent-tool: false

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import TYPE_CHECKING, cast

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))

from grading import expectation, judge, numbered, write_grading
from workspace import read_eval_metadata

if TYPE_CHECKING:
    from collections.abc import Sequence

Json = dict[str, object]

# The vocabulary a recommendation lands in. Deliberately wide: the skill asks for
# "improve or remove", and a run that says "fold this into build-green" has reached a
# verdict as squarely as one that says "delete it".
VERDICT = re.compile(
    r"\b(keep|keeping|retain\w*|leave\s+(?:it|this|as|in\s+place)|remove\w*|delete\w*|drop\w*"
    r"|deprecat\w*|retire\w*|merge\w*|consolidat\w*|fold\w*|replac\w*|rewrit\w*|rework\w*"
    r"|improv\w*|fix(?:es|ed)?\b|revis\w*|tighten\w*|downgrad\w*|upgrad\w*|switch\w*|re-?point\w*)",
    re.IGNORECASE,
)

# A figure with a unit attached. The skill's whole demand is that a recommendation be
# measurable, and a run that never writes a number has not met it.
QUANTITY = re.compile(
    r"(?:[$£€]\s?\d)"
    r"|\b\d[\d,._]*\s*(?:%|k\b|x\b|\u00d7|tokens?|lines?|words?|chars?|characters?"
    r"|seconds?|secs?|s\b|minutes?|mins?|ms\b|hours?|dollars?|usd|cents?|calls?|turns?)",
    re.IGNORECASE,
)

HEADING = re.compile(r"^(#{1,6})\s")
BACKTICKED = re.compile(r"`([^`\n]{4,120})`")

# A report that names the skill tells the grader which arm it is reading, and blinding is
# the point of the judgement half.
SKILL_TELL = re.compile(r"(?i)\b(?:the\s+)?(?:review-repo-agents\s+)?skill(?:'s)?\b")

MIN_VERBATIM_QUOTES = 3

# Every agent's frontmatter lists tools, and every fixture has these files at its root, so
# quoting one of them is evidence of nothing. The check wants the strings only a reader of
# the file could produce — `mypy src/`, `model: claude-3-opus-20240229`, `No drift found.`
CHEAP_QUOTES = frozenset(
    {
        "read",
        "write",
        "edit",
        "bash",
        "glob",
        "grep",
        "tools",
        "model",
        "name",
        "description",
        "claude.md",
        "readme.md",
        "changelog.md",
        ".claude/agents",
        ".claude/agents/",
    }
)


class Run:
    """One staged run directory, and the three things a check reads from it."""

    def __init__(self, run_dir: Path) -> None:
        self.dir = run_dir
        self.metadata = read_eval_metadata(run_dir)
        self.report = (run_dir / "outputs" / "report.md").read_text(encoding="utf-8")
        tool_log = run_dir / "outputs" / "tool-calls.txt"
        self.tools = tool_log.read_text(encoding="utf-8") if tool_log.is_file() else ""
        self.agents_dir = run_dir / "repo" / ".claude" / "agents"

    @property
    def agent_files(self) -> list[Path]:
        return sorted(self.agents_dir.glob("*.md"))

    def aliases(self, path: Path) -> list[str]:
        """What a report may reasonably call this agent: its filename stem and its `name:`.

        They differ where a fixture plants a mismatch, and a report is not wrong for
        using either one.
        """
        names = [path.stem]
        match = re.search(r"^name:\s*(\S+)", path.read_text(encoding="utf-8"), re.MULTILINE)
        if match and match.group(1) not in names:
            names.append(match.group(1))
        return names

    @property
    def corpus(self) -> str:
        return "\n".join(p.read_text(encoding="utf-8") for p in self.agent_files)


def windows_naming(report: str, aliases: Sequence[str]) -> str:
    """The parts of the report that are about one agent.

    A heading that names it scopes everything under it until the next heading at the same
    depth or shallower; a bare mention scopes the lines immediately around it, which is
    where a table row or a bullet keeps its verdict.
    """
    lines = report.splitlines()
    named = [i for i, line in enumerate(lines) if any(a.lower() in line.lower() for a in aliases)]
    taken: set[int] = set()
    for i in named:
        taken.update(range(max(0, i - 1), min(len(lines), i + 7)))
        heading = HEADING.match(lines[i])
        if not heading:
            continue
        depth = len(heading.group(1))
        for j in range(i + 1, len(lines)):
            nxt = HEADING.match(lines[j])
            if nxt and len(nxt.group(1)) <= depth:
                break
            taken.add(j)
    return "\n".join(lines[i] for i in sorted(taken))


def check_names_every_agent(run: Run) -> Json:
    lowered = run.report.lower()
    missing = [
        p.stem for p in run.agent_files if not any(a.lower() in lowered for a in run.aliases(p))
    ]
    return expectation(
        "Every agent in .claude/agents/ is named in the report",
        not missing,
        f"named all {len(run.agent_files)}"
        if not missing
        else f"never named: {', '.join(missing)}",
    )


def check_read_every_agent(run: Run) -> Json:
    if not run.tools.strip():
        return expectation(
            "Every agent definition file was read before the report was written",
            False,
            "no tool-call log for this run — not computable",
        )
    unread = [p.name for p in run.agent_files if p.name not in run.tools]
    return expectation(
        "Every agent definition file was read before the report was written",
        not unread,
        f"all {len(run.agent_files)} appear in the tool log"
        if not unread
        else f"never opened: {', '.join(unread)}",
    )


def check_verdict_per_agent(run: Run) -> Json:
    undecided: list[str] = []
    for path in run.agent_files:
        window = windows_naming(run.report, run.aliases(path))
        if not VERDICT.search(window):
            undecided.append(path.stem)
    return expectation(
        "The report reaches an explicit keep / improve / remove verdict for every agent",
        not undecided,
        f"a verdict verb sits beside all {len(run.agent_files)} names"
        if not undecided
        else f"no verdict near: {', '.join(undecided)}",
    )


def check_quantity(run: Run) -> Json:
    hits = QUANTITY.findall(run.report)
    found = QUANTITY.search(run.report)
    return expectation(
        "At least one recommendation is backed by a quantity — a token, line, percentage, "
        "time or cost figure",
        bool(found),
        f"{len(hits)} figures, first: {found.group(0).strip()!r}"
        if found
        else "the report carries no figure with a unit",
    )


def check_verbatim_quotes(run: Run) -> Json:
    corpus = run.corpus.lower()
    trivial = {a.lower() for p in run.agent_files for a in run.aliases(p)}
    trivial |= {p.name.lower() for p in run.agent_files} | CHEAP_QUOTES
    quoted = {
        span.strip()
        for span in BACKTICKED.findall(run.report)
        if span.strip().lower() in corpus and span.strip().lower() not in trivial
    }
    sample = ", ".join(sorted(quoted)[:4])
    return expectation(
        "The report quotes at least three strings that appear verbatim in the agent files",
        len(quoted) >= MIN_VERBATIM_QUOTES,
        f"{len(quoted)} verbatim quotes ({sample})"
        if quoted
        else "nothing backticked in the report appears in the agent files",
    )


def check_word_budget(run: Run, budget: int) -> Json:
    words = len(run.report.split())
    return expectation(
        f"The report is at most {budget} words, because the setup it found is sound",
        words <= budget,
        f"{words} words against a {budget}-word budget",
    )


JUDGE_PROMPT = """You are grading one report written by an assistant that was asked to
review the custom subagent definitions in somebody's repository. Judge only what is in
front of you; you are not told which version of the assistant produced it, and guessing
is not the task.

The user asked:
{prompt}

These are the agent definitions the assistant was reviewing, verbatim:
---
{agents}
---

This is the repository's CLAUDE.md, verbatim:
---
{claude_md}
---

Facts about this repository that you know and the assistant had to work out:
{ground_truth}

This is what the assistant told the user:
---
{report}
---

Decide each statement below. A statement is true only if the report plainly supports it —
not if it could be read that way charitably, and not because the assistant gestured at the
topic without reaching the point.

{statements}

Reply with a JSON array and nothing else: one object per statement, with keys "index"
(1-based, matching the numbering above), "passed" (boolean), and "evidence" (one sentence
quoting or naming what decided it)."""

GROUND_TRUTH = {
    "defective-agent-set": (
        "This repository builds and tests with uv, pytest, ruff and pyright; it uses neither "
        "black nor mypy. Five agents are on disk. `test-runner` runs one pytest command and "
        "returns a verdict, on opus. `unit-test-runner` runs the same suite for the same "
        "purpose, on sonnet, and its description overlaps test-runner's almost exactly. "
        "`deep-reviewer` weighs architectural trade-offs and returns an accept/reject "
        "recommendation, on haiku. `lint-fixer.md` carries `name: lint-fix` (which matches "
        "neither its filename nor anything that routes to it), no description at all, "
        "`model: claude-3-opus-20240229` (not a model alias this harness accepts), tools as a "
        "comma-separated string rather than a list, and no return contract. `commit-msg` runs "
        "`black --check .` and `mypy src/`, neither of which is configured here, and declares "
        "no tools despite needing Bash. CLAUDE.md's Delegation section routes to `test-runner` "
        "only; the other four are reachable from nowhere."
    ),
    "sound-agent-set-restraint": (
        "This setup is deliberately sound and the correct review finds little to change. "
        "Three agents: `build-green` runs the three documented commands on haiku and returns "
        "GREEN or a capped RED, `docs-drift` compares docs against code on sonnet and caps at "
        "ten findings, `harmonic-review` judges changes to the tide-prediction maths on opus "
        "and returns a verdict with reasoning. Every command they run matches CLAUDE.md. All "
        "three are routed from CLAUDE.md's Delegation table with a stated reason, their "
        "triggers do not overlap, each declares a tool allowlist and a return contract, and "
        "the model tiering is defensible in each case — including opus for harmonic-review, "
        "which CLAUDE.md justifies as the part of the repo a wrong answer is expensive in. "
        "Manufacturing a finding here, or proposing a fourth agent, is the failure mode."
    ),
    "mixed-keep-and-remove": (
        "Three agents. `coverage-gate` runs `pytest --cov ... --cov-report=term-missing`, "
        "whose output runs to several hundred lines, and returns at most ten lines — it is "
        "the one that earns its place, and removing it is wrong. `changelog-reader` does "
        "nothing but read CHANGELOG.md (a 12-line file at the repository root) and hand the "
        "contents back; the delegation costs a whole extra model round-trip to save a Read "
        "the caller could do itself, so it is strictly worse than not existing. "
        "`pair-programmer` runs on opus with Read, Write, Edit, Bash, Glob and Grep, has no "
        "return contract and no bounded job, and its description duplicates what the main "
        "session already is — it narrows neither model, context nor output, so it can only "
        "add a round-trip and a second context to keep in step."
    ),
}


def mechanical(run: Run) -> list[Json]:
    checks = [
        check_names_every_agent(run),
        check_read_every_agent(run),
        check_verdict_per_agent(run),
        check_quantity(run),
        check_verbatim_quotes(run),
    ]
    budget = run.metadata.get("word_budget")
    if isinstance(budget, int):
        checks.append(check_word_budget(run, budget))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Grade one review-repo-agents eval run.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--model", default="sonnet", help="Grader model (default: sonnet).")
    parser.add_argument("--no-judge", action="store_true", help="Mechanical checks only.")
    args = parser.parse_args()

    run = Run(args.run_dir)
    name = str(run.metadata["eval_name"])
    if name not in GROUND_TRUTH:
        print(f"error: no ground truth for eval {name!r}", file=sys.stderr)
        return 1

    expectations = mechanical(run)

    statements = [str(s) for s in cast("list[object]", run.metadata.get("judgement", []))]
    if statements and not args.no_judge:
        prompt = JUDGE_PROMPT.format(
            prompt=run.metadata["prompt"],
            agents="\n\n".join(
                f"=== .claude/agents/{p.name} ===\n{p.read_text(encoding='utf-8')}"
                for p in run.agent_files
            ),
            claude_md=(run.dir / "repo" / "CLAUDE.md").read_text(encoding="utf-8"),
            ground_truth=GROUND_TRUTH[name],
            report=SKILL_TELL.sub("my instructions", run.report).strip()
            or "(the run produced no report)",
            statements=numbered(statements),
        )
        expectations += judge(statements, prompt, model=args.model, cwd=args.run_dir)

    grading = write_grading(
        args.run_dir,
        expectations,
        execution_metrics={
            "report_words": len(run.report.split()),
            "agents_on_disk": len(run.agent_files),
            "tool_calls": len([t for t in run.tools.splitlines() if t.strip()]),
        },
    )
    summary = cast("Json", grading["summary"])
    print(f"[{name}/{run.metadata['arm']}] {summary['passed']}/{summary['total']}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
