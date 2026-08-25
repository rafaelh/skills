#!/usr/bin/env python3
"""Stage a workspace for one round of the az evals.

    prepare.py <workspace> [--iteration N] [--runs K] [--arms a,b,c]

Builds the standard layout — `<workspace>/iteration-<n>/eval-<id>-<name>/<arm>/run-<k>/`
— and gives each run its own Azure: a copy of the fake CLI at `az-cli/az`, the tenant
scenario beside it, an empty `work/` to run in, and the `eval_metadata.json` that
`grade.py` later reads. Prints the staged run directories as JSON.

Two staging decisions are worth knowing about:

* The fake CLI's shebang is rewritten to the interpreter running this script, because
  it imports jmespath to evaluate `--query` and the run's own `python3` may not have it.
* Help packs are copied once per iteration and the tenant's `help_packs` rewritten to
  point there. They are 1.2 MB and identical across every run in a round; a per-run copy
  would multiply that by the number of cells for no gain.

Developer harness, not something an agent calls — see README.md.
"""

# agent-tool: false

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
from typing import cast

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))

from workspace import ARMS, load_cases, run_dir, write_eval_metadata

FIXTURES = HERE / "fixtures"
TENANTS = FIXTURES / "tenants"
HELP_PACKS = FIXTURES / "help"

KNOWN_ARMS = (*ARMS, "old_skill")

Json = dict[str, object]


def emit_error(code: str, message: str, hint: str) -> None:
    print(json.dumps({"error": message, "code": code, "hint": hint}), file=sys.stderr)


def stage_help(iteration_dir: Path) -> Path:
    """One copy of the help packs per round, shared by every run in it."""
    dest = iteration_dir / "help"
    if not dest.exists():
        shutil.copytree(HELP_PACKS, dest)
    return dest


def stage_tenant(target: Path, tenant: str, help_dir: Path) -> Path:
    """The fake CLI and its scenario, ready for the run's PATH to point at."""
    source = TENANTS / f"{tenant}.json"
    if not source.is_file():
        raise FileNotFoundError(f"no tenant scenario at {source}")
    scenario = cast("Json", json.loads(source.read_text(encoding="utf-8")))
    scenario["help_packs"] = [
        str(help_dir / Path(str(ref)).name) for ref in cast("list[object]", scenario["help_packs"])
    ]

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    (target / "tenant.json").write_text(json.dumps(scenario, indent=2), encoding="utf-8")

    fake = (FIXTURES / "az").read_text(encoding="utf-8")
    fake = f"#!{sys.executable}\n" + fake.split("\n", 1)[1]
    binary = target / "az"
    binary.write_text(fake, encoding="utf-8")
    binary.chmod(0o755)
    return binary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage a round of az eval runs.")
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--iteration", type=int, default=1)
    parser.add_argument("--runs", type=int, default=1, help="Repeats per cell (default: 1).")
    parser.add_argument("--arms", default=",".join(ARMS))
    parser.add_argument("--evals", type=Path, default=HERE / "evals.json")
    parser.add_argument("--only", help="Stage one case only, by name or id.")
    args = parser.parse_args()

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arms if a not in KNOWN_ARMS]
    if unknown:
        emit_error("BAD_ARM", f"unknown arm(s): {unknown}", f"known arms: {list(KNOWN_ARMS)}")
        return 1

    _, cases = load_cases(args.evals)
    if args.only:
        cases = [c for c in cases if str(c["name"]) == args.only or str(c["id"]) == args.only]
        if not cases:
            emit_error("NO_CASE", f"no eval matching {args.only!r}", "see evals.json")
            return 1

    iteration_dir = args.workspace / f"iteration-{args.iteration}"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    help_dir = stage_help(iteration_dir)

    staged: list[str] = []
    for case in cases:
        for arm in arms:
            for run in range(1, args.runs + 1):
                target = run_dir(args.workspace, case, arm, iteration=args.iteration, run=run)
                target.mkdir(parents=True, exist_ok=True)
                (target / "outputs").mkdir(exist_ok=True)
                (target / "work").mkdir(exist_ok=True)
                stage_tenant(target / "az-cli", str(case["fixture"]), help_dir)
                write_eval_metadata(target, case, arm, {"judgement": case.get("judgement", [])})
                staged.append(str(target))

    print(json.dumps({"staged": staged, "count": len(staged)}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
