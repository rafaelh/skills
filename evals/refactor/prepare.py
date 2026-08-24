#!/usr/bin/env python3
"""Stage a workspace for one round of the refactor evals.

    prepare.py <workspace> [--iteration N] [--runs K] [--arms a,b,c]

Builds the standard layout — `<workspace>/iteration-<n>/eval-<id>-<name>/<arm>/run-<k>/`
— with a git-initialised copy of each fixture under `repo/`, an empty `outputs/`, and the
`eval_metadata.json` that `grade.py` later reads. Prints the staged run directories as JSON.

Developer harness, not something an agent calls — see README.md.
"""

# agent-tool: false

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import cast

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))

from workspace import ARMS, load_cases, run_dir, stage_fixture, write_eval_metadata

FIXTURES = HERE / "fixtures"

# The arms run_case.py knows how to drive; `old_skill` takes its body from --skill.
KNOWN_ARMS = (*ARMS, "old_skill")

GIT_ID = ("-c", "user.name=eval", "-c", "user.email=eval@local")


def emit_error(code: str, message: str, hint: str) -> None:
    print(json.dumps({"error": message, "code": code, "hint": hint}), file=sys.stderr)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def split_history(repo: Path, recent: list[str], messages: list[str]) -> None:
    """Commit the fixture in two, so `git log` can say which files landed last.

    Scope-to-what-changed is the one principle a run cannot apply without history:
    told to tidy "the last thing I committed", it has to look the answer up rather
    than guess from how ugly a file is. `recent` lands in the second commit and
    everything else in the first.

    The messages come from the case, because they are part of what a run reads: a
    subject line that describes someone else's fixture is a signal pointing the
    wrong way.
    """
    git(repo, "init", "-q")
    git(repo, "add", "-A", "--", *(f":!{path}" for path in recent))
    git(repo, *GIT_ID, "commit", "-qm", messages[0])
    git(repo, "add", "-A")
    git(repo, *GIT_ID, "commit", "-qm", messages[1])


def stage(workspace: Path, iteration: int, runs: int, arms: tuple[str, ...], quiet: bool) -> int:
    _, cases = load_cases(HERE / "evals.json")
    staged: list[str] = []
    for case in cases:
        recent = [str(p) for p in cast("list[object]", case.get("recent_files", []))]
        messages = [str(m) for m in cast("list[object]", case.get("history_messages", []))]
        if recent and len(messages) != 2:
            raise ValueError(
                f"case '{case['name']}' sets recent_files, so it needs exactly two "
                f"history_messages; got {len(messages)}"
            )
        for arm in arms:
            for run in range(1, runs + 1):
                target = run_dir(workspace, case, arm, iteration=iteration, run=run)
                (target / "outputs").mkdir(parents=True, exist_ok=True)
                # Fixtures ship without their .git — an embedded repo inside this one
                # would be committed as a gitlink and the files would never land. A run
                # is told to read the history, and grade.py diffs against HEAD.
                repo = stage_fixture(
                    FIXTURES / str(case["fixture"]), target / "repo", git=not recent
                )
                if recent:
                    split_history(repo, recent, messages)
                write_eval_metadata(target, case, arm, {"target": case.get("target")})
                staged.append(str(target))
                if not quiet:
                    print(str(target), file=sys.stderr)
    print(
        json.dumps(
            {
                "workspace": str(workspace / f"iteration-{iteration}"),
                "evals": len(cases),
                "arms": list(arms),
                "runs": staged,
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage fixture copies for one refactor eval round.",
        epilog="example:  prepare.py /tmp/refactor-ws --iteration 2",
    )
    parser.add_argument("workspace", type=Path, help="Directory to build the round under.")
    parser.add_argument("--iteration", type=int, default=1, help="Round number (default: 1).")
    parser.add_argument("--runs", type=int, default=1, help="Repeats of each cell (default: 1).")
    # shared/workspace.ARMS is the two-arm default every suite starts from. A third arm is
    # this suite's business — an ablation of the skill measured against the whole file —
    # so it is a flag here rather than a change to the shared layout.
    parser.add_argument(
        "--arms",
        default=",".join(ARMS),
        help=f"Comma-separated arms to stage (default: {','.join(ARMS)}).",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress informational stderr.")
    args = parser.parse_args()

    arms = tuple(a.strip() for a in str(args.arms).split(",") if a.strip())
    unknown = [a for a in arms if a not in KNOWN_ARMS]
    if not arms or unknown:
        emit_error(
            "prepare.arms.invalid",
            f"unknown arm(s): {', '.join(unknown) or '(none given)'}",
            f"pick from {', '.join(KNOWN_ARMS)}",
        )
        return 1

    try:
        return stage(
            args.workspace.expanduser().resolve(), args.iteration, args.runs, arms, args.quiet
        )
    except FileNotFoundError as exc:
        emit_error("prepare.fixture.missing", str(exc), f"expected it under {FIXTURES}")
        return 1
    except ValueError as exc:
        emit_error("prepare.case.invalid", str(exc), "fix the case in evals.json")
        return 1
    except (OSError, subprocess.CalledProcessError) as exc:
        emit_error("prepare.stage.failed", str(exc), "check the workspace path is writable")
        return 2


if __name__ == "__main__":
    sys.exit(main())
