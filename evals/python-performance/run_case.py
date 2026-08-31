#!/usr/bin/env python3
"""Drive one python-performance eval run to completion inside a staged run directory.

    run_case.py <run-dir> [--arm ...] [--model sonnet]

The run directory comes from `prepare.py`, which has already put a git-initialised copy of
the fixture in `repo/` and written `eval_metadata.json`. This gives a Claude CLI session
write access to that copy and the eval's prompt, then records what it left:
`outputs/summary.md` (the run's own narration), `outputs/tool-calls.txt`, and `timing.json`.
Grade it with `grade.py <run-dir>`.

The two arms differ in exactly one thing: whether the skill's body is appended to the
system prompt. Everything else — model, tools, fixture, prompt, preamble — is identical,
and the preamble says nothing about checking, profiling or proving a fix, because those
are the behaviours under test.

Developer harness, not something an agent calls — see README.md.
"""

# agent-tool: false

from __future__ import annotations

import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))

from claude_cli import EDITING_TOOLS, ISOLATION_BLOCKED_TOOLS, run_claude
from workspace import find_case, load_cases, read_eval_metadata, write_timing

SKILL_DIR = HERE.parent.parent / "skills" / "python-performance"
DEFAULT_SKILL = SKILL_DIR / "SKILL.md"

# Given to both arms verbatim. It says where the run is and how to run the tests, and
# stops there. Anything more — "measure first", "report the numbers" — would hand the
# without_skill arm the behaviour the skill is being measured on.
SITUATION = """You are working in a checkout of this repository at {cwd}. The checkout is
yours alone for this task: nothing else depends on it, and there is nobody available to
answer questions, so make the judgement calls yourself and carry the work through to the
end rather than stopping to ask.

The repository has no virtualenv of its own. Use this interpreter for anything you run:

    {python}

Its test suite runs with `{python} -m pytest -q` from the repository root.

When you have finished, write a short summary of the work as your final message."""

SKILL_FRAME = """The following skill is active for this conversation. Follow it.

---
"""


def skill_body(skill_md: Path, skill_dir: Path) -> str:
    """SKILL.md with its frontmatter removed and `${SKILL_DIR}` resolved.

    A triggered skill contributes the body, and Claude Code resolves the directory
    notation from `${CLAUDE_SKILL_DIR}` before the model sees it. Leaving the literal in
    would measure the arm's ability to guess a path rather than its use of the tool.
    """
    text = skill_md.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4 :]
    return text.strip().replace("${SKILL_DIR}", str(skill_dir))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one staged python-performance eval to completion."
    )
    parser.add_argument("run_dir", type=Path, help="Run directory staged by prepare.py.")
    parser.add_argument(
        "--arm",
        choices=["with_skill", "without_skill", "old_skill"],
        help="Defaults to the arm recorded in eval_metadata.json.",
    )
    parser.add_argument("--evals", type=Path, default=HERE / "evals.json")
    parser.add_argument(
        "--skill",
        type=Path,
        default=DEFAULT_SKILL,
        help="SKILL.md to test; point old_skill at a snapshot.",
    )
    parser.add_argument(
        "--skill-dir",
        type=Path,
        default=SKILL_DIR,
        help="What `${SKILL_DIR}` resolves to — the directory holding scripts/.",
    )
    parser.add_argument("--model", default="sonnet", help="Model under test (default: sonnet).")
    parser.add_argument("--timeout", type=int, default=2400, help="Seconds (default: 2400).")
    args = parser.parse_args()

    run_dir: Path = args.run_dir
    metadata = read_eval_metadata(run_dir)
    arm = args.arm or str(metadata["arm"])
    _, cases = load_cases(args.evals)
    case = find_case(cases, str(metadata["eval_name"]))

    repo = run_dir / "repo"
    if not repo.is_dir():
        print(f"error: no staged repo at {repo} — run prepare.py first", file=sys.stderr)
        return 1
    (run_dir / "outputs").mkdir(exist_ok=True)

    system = SITUATION.format(cwd=repo, python=sys.executable)
    if arm != "without_skill":
        system += "\n\n" + SKILL_FRAME + skill_body(args.skill, args.skill_dir)

    result = run_claude(
        str(case["prompt"]),
        cwd=repo,
        model=args.model,
        system_prompt=system,
        allowed_tools=EDITING_TOOLS,
        disallowed_tools=ISOLATION_BLOCKED_TOOLS,
        # No one is at the terminal to approve an edit; without this the run stalls on
        # its first Edit until the timeout and leaves an untouched repo to grade.
        permission_mode="acceptEdits",
        timeout=args.timeout,
        # A timing command is typically a `cd` into the workspace followed by an inline
        # script; at the default 200 characters the log stops before the part that says
        # whether anything was measured, which is what this suite grades.
        tool_summary_chars=1000,
    )

    (run_dir / "outputs" / "summary.md").write_text(result.text, encoding="utf-8")
    (run_dir / "outputs" / "tool-calls.txt").write_text(
        "\n".join(result.tools) + "\n", encoding="utf-8"
    )
    write_timing(
        run_dir,
        total_tokens=result.tokens,
        duration_ms=result.duration_ms,
        cost_usd=result.cost_usd,
        extra={"tool_calls": len(result.tools), "model": args.model},
    )
    print(
        f"[{case['name']}/{arm}] done: {len(result.tools)} tool calls, "
        f"{result.tokens} tokens, {round(result.duration_ms / 1000)}s",
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
