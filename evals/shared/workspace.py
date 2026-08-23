"""The run-directory layout every suite stages into, and the two files it must leave.

    <workspace>/iteration-<n>/eval-<id>-<name>/<arm>/run-<k>/

Every level earns its place: the iteration is what a benchmark round is compared
across, the eval and arm are the experiment, and the run level is where repeats of the
same cell go — one run per cell is a single observation, and the aggregator globs for
this depth whether or not a suite currently repeats.

Developer harness, not something an agent calls — see ../eval-approach.md.
"""

# agent-tool: false

from __future__ import annotations

import json
import shutil
import subprocess
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

Json = dict[str, object]

ARMS = ("with_skill", "without_skill")

# Caches and virtualenvs are produced by running the fixture's own tools, which a run
# is free to do. Copying them in makes a staged repo differ from the fixture before
# the run starts, and every diff-based check reads that as a change the run made.
IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".venv", ".coverage"
)


def load_cases(evals_path: Path) -> tuple[str, list[Json]]:
    """The skill name and the case list from an `evals.json`."""
    data = cast("Json", json.loads(evals_path.read_text(encoding="utf-8")))
    cases = [cast("Json", c) for c in cast("list[object]", data["evals"])]
    return str(data["skill_name"]), cases


def find_case(cases: Sequence[Json], key: str) -> Json:
    """Look a case up by `name` or by `id`, the two things a caller has to hand."""
    for case in cases:
        if str(case["name"]) == key or str(case["id"]) == key:
            return case
    available = ", ".join(f"{c['id']}:{c['name']}" for c in cases)
    raise KeyError(f"no eval matching {key!r}. available: {available}")


def case_slug(case: Json) -> str:
    return f"eval-{case['id']}-{case['name']}"


def run_dir(workspace: Path, case: Json, arm: str, *, iteration: int = 1, run: int = 1) -> Path:
    return workspace / f"iteration-{iteration}" / case_slug(case) / arm / f"run-{run}"


def git_init(repo: Path) -> None:
    """A staged copy is not a repo until this runs; skill scripts that shell out to git need it."""
    for cmd in (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "-c", "user.name=eval", "-c", "user.email=eval@local", "commit", "-qm", "fixture"],
    ):
        subprocess.run(cmd, cwd=repo, check=True, capture_output=True)


def stage_fixture(fixture: Path | None, dest: Path, *, git: bool = False) -> Path:
    """Give a run its own copy of the fixture, so no run can mutate what it is measured against.

    `None` stages an empty directory — the case has no repo, and the run still needs
    somewhere to be.
    """
    if dest.exists():
        shutil.rmtree(dest)
    if fixture is None:
        dest.mkdir(parents=True)
        return dest
    if not fixture.is_dir():
        raise FileNotFoundError(f"fixture not found: {fixture}")
    shutil.copytree(fixture, dest, ignore=IGNORE)
    if git:
        git_init(dest)
    return dest


def write_eval_metadata(target: Path, case: Json, arm: str, extra: Json | None = None) -> Json:
    """`eval_metadata.json` — what the viewer reads, and what lets a run dir explain itself.

    `eval_id` and `prompt` are the viewer's; the rest is so a stored run can be
    re-graded years later without the `evals.json` that produced it.
    """
    payload: Json = {
        "eval_id": case["id"],
        "eval_name": case["name"],
        "arm": arm,
        "prompt": case["prompt"],
        "fixture": case.get("fixture"),
        "assertions": case.get("assertions", case.get("judgement", [])),
    }
    if extra:
        payload.update(extra)
    (target / "eval_metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def read_eval_metadata(target: Path) -> Json:
    return cast("Json", json.loads((target / "eval_metadata.json").read_text(encoding="utf-8")))


def write_timing(
    target: Path,
    *,
    total_tokens: int,
    duration_ms: int,
    cost_usd: float = 0.0,
    extra: Json | None = None,
) -> Json:
    """`timing.json` — the cost of the thing under test, and only that.

    Harness overhead (a simulated user, a grader) goes in `extra` under its own keys
    so it cannot flatter or inflate a round.
    """
    payload: Json = {
        "total_tokens": total_tokens,
        "duration_ms": duration_ms,
        "total_duration_seconds": round(duration_ms / 1000, 1),
        "cost_usd": round(cost_usd, 4),
    }
    if extra:
        payload.update(extra)
    (target / "timing.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
