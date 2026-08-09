#!/usr/bin/env python3
"""Stage a workspace for one eval iteration of create-agents-for-repo.

Builds `<workspace>/iteration-<n>/eval-<id>-<name>/{with_skill,without_skill}/`
with a fresh git-initialised copy of each fixture, ready for the runs.

Developer harness, not something an agent calls — see evals/README.md.
"""

# agent-tool: false

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
ARMS = ("with_skill", "without_skill")

# Fixtures ship without their .git — an embedded repo inside this one would be
# committed as a gitlink and the files would never land. scan_delegation_targets.py
# shells out to git, so each copy needs to be a repo before a run starts.
IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".venv", ".coverage"
)


def emit_error(code: str, message: str, hint: str) -> None:
    print(json.dumps({"error": message, "code": code, "hint": hint}), file=sys.stderr)


def git_init(repo: Path) -> None:
    for cmd in (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "-c", "user.name=eval", "-c", "user.email=eval@local", "commit", "-qm", "fixture"],
    ):
        subprocess.run(cmd, cwd=repo, check=True, capture_output=True)


def stage(workspace: Path, iteration: int, quiet: bool) -> int:
    evals = json.loads((HERE / "evals.json").read_text(encoding="utf-8"))["evals"]
    root = workspace / f"iteration-{iteration}"
    for e in evals:
        name = f"eval-{e['id']}-{e['name']}"
        fixture = FIXTURES / e["fixture"]
        if not fixture.is_dir():
            emit_error(
                "prepare.fixture.missing",
                f"fixture {e['fixture']} not found",
                f"expected it at {fixture}",
            )
            return 3
        d = root / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "eval_metadata.json").write_text(
            json.dumps(
                {
                    "eval_id": e["id"],
                    "eval_name": e["name"],
                    "prompt": e["prompt"],
                    "assertions": e["assertions"],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        for arm in ARMS:
            run = d / arm
            (run / "outputs").mkdir(parents=True, exist_ok=True)
            repo = run / "repo"
            if repo.exists():
                shutil.rmtree(repo)
            shutil.copytree(fixture, repo, ignore=IGNORE)
            git_init(repo)
            if not quiet:
                print(f"{name}/{arm}", file=sys.stderr)
    print(json.dumps({"workspace": str(root), "evals": len(evals), "arms": list(ARMS)}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage fixture copies for one eval iteration.",
        epilog="example:  prepare.py /tmp/cafr-ws --iteration 3",
    )
    parser.add_argument("workspace", type=Path, help="Directory to build the iteration under.")
    parser.add_argument("--iteration", type=int, default=1, help="Iteration number (default: 1).")
    parser.add_argument("--format", choices=["json", "text"], default="json", help="Output format.")
    parser.add_argument("--json", action="store_true", help="Alias for --format json.")
    parser.add_argument("--quiet", action="store_true", help="Suppress informational stderr.")
    args = parser.parse_args()

    try:
        return stage(args.workspace.expanduser().resolve(), args.iteration, args.quiet)
    except (OSError, subprocess.CalledProcessError) as exc:
        emit_error("prepare.stage.failed", str(exc), "check the workspace path is writable")
        return 2


if __name__ == "__main__":
    sys.exit(main())
