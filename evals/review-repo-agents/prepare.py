#!/usr/bin/env python3
"""Stage a workspace for one round of the review-repo-agents evals.

    prepare.py <workspace> [--iteration N] [--runs K] [--arms with_skill,without_skill]

Builds the standard layout — `<workspace>/iteration-<n>/eval-<id>-<name>/<arm>/run-<k>/`
— with a git-initialised copy of each fixture under `repo/`, an empty `outputs/`, and the
`eval_metadata.json` that `run_case.py` and `grade.py` both read. Prints the staged run
directories as JSON.

Developer harness, not something an agent calls — see README.md.
"""

# agent-tool: false

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))

from workspace import ARMS, load_cases, run_dir, stage_fixture, write_eval_metadata

FIXTURES = HERE / "fixtures"


def emit_error(code: str, message: str, hint: str) -> None:
    print(json.dumps({"error": message, "code": code, "hint": hint}), file=sys.stderr)


def stage(workspace: Path, iteration: int, runs: int, arms: list[str], quiet: bool) -> int:
    _, cases = load_cases(HERE / "evals.json")
    staged: list[str] = []
    for case in cases:
        for arm in arms:
            for run in range(1, runs + 1):
                target = run_dir(workspace, case, arm, iteration=iteration, run=run)
                (target / "outputs").mkdir(parents=True, exist_ok=True)
                # Fixtures ship without their .git, so a staged copy is not a repo until
                # git_init runs. A review run is read-only, but the repo is what a run is
                # told it is working in, and an uninitialised one reads as a loose
                # directory the moment anything shells out to git.
                stage_fixture(FIXTURES / str(case["fixture"]), target / "repo", git=True)
                write_eval_metadata(
                    target,
                    case,
                    arm,
                    extra={
                        "judgement": case.get("judgement", []),
                        "word_budget": case.get("word_budget"),
                    },
                )
                staged.append(str(target))
                if not quiet:
                    print(str(target), file=sys.stderr)
    print(
        json.dumps(
            {
                "workspace": str(workspace / f"iteration-{iteration}"),
                "evals": len(cases),
                "arms": arms,
                "runs": staged,
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage fixture copies for one eval round.",
        epilog="example:  prepare.py ~/.cache/claude-evals/rra --iteration 1",
    )
    parser.add_argument("workspace", type=Path, help="Directory to build the round under.")
    parser.add_argument("--iteration", type=int, default=1, help="Round number (default: 1).")
    parser.add_argument("--runs", type=int, default=1, help="Repeats of each cell (default: 1).")
    parser.add_argument(
        "--arms",
        default=",".join(ARMS),
        help="Comma-separated arms to stage (default: with_skill,without_skill).",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress informational stderr.")
    args = parser.parse_args()

    arms = [a.strip() for a in str(args.arms).split(",") if a.strip()]
    try:
        return stage(
            args.workspace.expanduser().resolve(), args.iteration, args.runs, arms, args.quiet
        )
    except FileNotFoundError as exc:
        emit_error("prepare.fixture.missing", str(exc), f"expected it under {FIXTURES}")
        return 1
    except (OSError, subprocess.CalledProcessError) as exc:
        emit_error("prepare.stage.failed", str(exc), "check the workspace path is writable")
        return 2


if __name__ == "__main__":
    sys.exit(main())
