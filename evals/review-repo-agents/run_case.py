#!/usr/bin/env python3
"""Drive one review-repo-agents eval run to completion inside a staged run directory.

    run_case.py <run-dir> [--arm ...] [--model sonnet]

The run directory comes from `prepare.py`, which has already put a git-initialised copy of
the fixture in `repo/` and written `eval_metadata.json`. This gives a Claude CLI session
read-only access to that copy and the eval's prompt, then records what it left:
`outputs/report.md` (the review itself, which is the whole artifact here),
`outputs/tool-calls.txt`, and `timing.json`. Grade it with `grade.py <run-dir>`.

Runs get `Read`, `Grep` and `Glob` and nothing else. A review authors no files, and the
rubric asks nothing a shell answers, so granting `Bash` would buy variance and tokens
without buying signal.

The two arms differ in exactly one thing: whether the skill's body is appended to the
system prompt. The preamble below says where the run is and stops — naming agents, models,
cost or usefulness in it would hand the without_skill arm the behaviour under test.

Developer harness, not something an agent calls — see README.md.
"""

# agent-tool: false

from __future__ import annotations

import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))

from claude_cli import READ_ONLY_TOOLS, run_claude
from workspace import find_case, load_cases, read_eval_metadata, write_timing

DEFAULT_SKILL = HERE.parent.parent / "skills" / "review-repo-agents" / "SKILL.md"

SITUATION = """You are working in a checkout of this repository at {cwd}. Nothing else
depends on this checkout and there is nobody available to answer questions, so make the
judgement calls yourself and carry the work through to the end rather than stopping to ask.

You have read-only access: Read, Grep and Glob. Write your answer to the user as your final
message."""

SKILL_FRAME = """The following skill is active for this conversation. Follow it.

---
"""


def skill_body(skill_md: Path) -> str:
    """SKILL.md with its YAML frontmatter removed — the part a triggered skill contributes."""
    text = skill_md.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4 :]
    return text.strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one staged review-repo-agents eval to completion."
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
    parser.add_argument("--model", default="sonnet", help="Model under test (default: sonnet).")
    parser.add_argument("--timeout", type=int, default=1800, help="Seconds (default: 1800).")
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

    system = SITUATION.format(cwd=repo)
    if arm != "without_skill":
        system += "\n\n" + SKILL_FRAME + skill_body(args.skill)

    result = run_claude(
        str(case["prompt"]),
        cwd=repo,
        model=args.model,
        system_prompt=system,
        allowed_tools=READ_ONLY_TOOLS,
        timeout=args.timeout,
    )

    (run_dir / "outputs" / "report.md").write_text(result.text, encoding="utf-8")
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
