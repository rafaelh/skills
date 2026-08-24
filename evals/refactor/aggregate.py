#!/usr/bin/env python3
"""Roll a graded refactor round up into the tables a benchmark entry is written from.

    aggregate.py <iteration-dir> [--all-checks] [--format text|json]

Reads every `grading.json` under the directory, groups the runs by eval and arm, and
emits three things: the per-eval pass rate by arm, the per-check arm comparison, and the
cost block. Output is markdown, so a round can be pasted into `benchmark.md` rather than
transcribed.

A round is one model. Two models are two workspaces and two invocations — the model is
recorded in `timing.json` and reported, not aggregated across.

Developer harness, not something an agent calls — see README.md.
"""

# agent-tool: false

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import cast

Json = dict[str, object]
EvalCells = dict[tuple[int, str], dict[str, "Cell"]]
Checks = dict[str, dict[str, "Cell"]]

# Reported in this order when present; anything else follows, sorted.
ARM_ORDER = ("with_skill", "old_skill", "without_skill")


def emit_error(code: str, message: str, hint: str) -> None:
    print(json.dumps({"error": message, "code": code, "hint": hint}), file=sys.stderr)


def read_json(path: Path) -> Json:
    return cast("Json", json.loads(path.read_text(encoding="utf-8")))


class Cell:
    """One (eval, arm) cell: the runs in it, summed."""

    def __init__(self) -> None:
        self.passed = 0
        self.total = 0
        self.runs = 0
        self.tokens = 0
        self.duration_ms = 0
        self.tool_calls = 0
        self.cost_usd = 0.0

    @property
    def rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def add_grading(self, grading: Json) -> None:
        summary = cast("Json", grading["summary"])
        self.passed += int(cast("int", summary["passed"]))
        self.total += int(cast("int", summary["total"]))
        self.runs += 1

    def add_timing(self, timing: Json) -> None:
        self.tokens += int(cast("int", timing.get("total_tokens", 0)))
        self.duration_ms += int(cast("int", timing.get("duration_ms", 0)))
        self.tool_calls += int(cast("int", timing.get("tool_calls", 0)))
        self.cost_usd += float(cast("float", timing.get("cost_usd", 0.0)))


def score(cell: Cell, digits: int = 0) -> str:
    """A cell as `pass% (passed/total)`. The mean carries a decimal; a cell does not.

    Per-eval rates move in whole checks, so a decimal there is false precision. The
    round's mean is compared across rounds at a 2pp threshold and needs the digit.
    """
    return f"{cell.rate:.{digits}%} ({cell.passed}/{cell.total})" if cell.total else "—"


def collect(root: Path) -> tuple[EvalCells, dict[str, Cell], Json]:
    """Per-eval cells, per-arm totals, and what the runs say about themselves."""
    evals: EvalCells = defaultdict(lambda: defaultdict(Cell))
    arms: dict[str, Cell] = defaultdict(Cell)
    checks: Checks = defaultdict(lambda: defaultdict(Cell))
    models: set[str] = set()
    run_count = 0

    for grading_path in sorted(root.rglob("grading.json")):
        run = grading_path.parent
        metadata = read_json(run / "eval_metadata.json")
        arm = str(metadata["arm"])
        key = (int(cast("int", metadata["eval_id"])), str(metadata["eval_name"]))
        grading = read_json(grading_path)
        evals[key][arm].add_grading(grading)
        arms[arm].add_grading(grading)
        run_count += 1

        for record in cast("list[Json]", grading["expectations"]):
            cell = checks[str(record["text"])][arm]
            cell.passed += 1 if record["passed"] else 0
            cell.total += 1

        timing_path = run / "timing.json"
        if timing_path.is_file():
            timing = read_json(timing_path)
            evals[key][arm].add_timing(timing)
            arms[arm].add_timing(timing)
            models.add(str(timing.get("model", "unrecorded")))

    context: Json = {"runs": run_count, "models": sorted(models), "checks": checks}
    return evals, arms, context


def arm_names(arms: dict[str, Cell]) -> list[str]:
    known = [a for a in ARM_ORDER if a in arms]
    return known + sorted(a for a in arms if a not in ARM_ORDER)


def table(header: str, rows: list[list[str]], columns: list[str]) -> list[str]:
    out = [header, "", "| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    out += ["| " + " | ".join(row) + " |" for row in rows]
    return [*out, ""]


def eval_table(evals: EvalCells, names: list[str]) -> list[str]:
    rows: list[list[str]] = []
    for (eval_id, eval_name), cells in sorted(evals.items()):
        rows.append([f"{eval_id} {eval_name}", *(score(cells[arm]) for arm in names)])
    return table("### Per eval", rows, ["Eval", *names])


def mean_row(arms: dict[str, Cell], names: list[str]) -> list[str]:
    return ["**Mean**", *(f"**{score(arms[arm], digits=1)}**" for arm in names)]


def check_table(checks: Checks, names: list[str], *, all_checks: bool) -> list[str]:
    """Per-check pass counts by arm. Checks that move nothing are hidden by default.

    A check at the same rate in every arm has stopped discriminating — it is a
    regression floor, and listing forty of them buries the six that separated.
    """
    rows: list[list[str]] = []
    for text, cells in sorted(checks.items()):
        rates = [cells[arm].rate for arm in names if cells[arm].total]
        if not all_checks and (not rates or max(rates) - min(rates) < 1e-9):
            continue
        counts = (
            f"{cells[arm].passed}/{cells[arm].total}" if cells[arm].total else "—" for arm in names
        )
        rows.append([text, *counts])
    heading = "### Every check" if all_checks else "### Checks that separated the arms"
    if not rows:
        return [heading, "", "No check differs between arms.", ""]
    return table(heading, rows, ["Check", *names])


def cost_table(arms: dict[str, Cell], names: list[str]) -> list[str]:
    def per_run(arm: str, value: float, digits: int = 0) -> str:
        cell = arms[arm]
        return f"{value / cell.runs:,.{digits}f}" if cell.runs else "—"

    rows = [
        ["Runs", *(str(arms[a].runs) for a in names)],
        ["Tokens, total", *(f"{arms[a].tokens:,}" for a in names)],
        ["Tokens, mean", *(per_run(a, arms[a].tokens) for a in names)],
        ["Wall clock, mean", *(f"{per_run(a, arms[a].duration_ms / 1000)}s" for a in names)],
        ["Tool calls, mean", *(per_run(a, arms[a].tool_calls, 1) for a in names)],
        ["Cost", *(f"${arms[a].cost_usd:.2f}" for a in names)],
    ]
    return table("### Cost", rows, ["", *names])


def render(root: Path, evals: EvalCells, arms: dict[str, Cell], context: Json) -> str:
    names = arm_names(arms)
    checks = cast("Checks", context["checks"])
    models = ", ".join(cast("list[str]", context["models"])) or "unrecorded"
    lines = [
        f"## {root.name} — {context['runs']} runs, model: {models}",
        "",
        *eval_table(evals, names)[:-1],
        "| " + " | ".join(mean_row(arms, names)) + " |",
        "",
        *check_table(checks, names, all_checks=bool(context["all_checks"])),
        *cost_table(arms, names),
    ]
    return "\n".join(lines)


def as_json(evals: EvalCells, arms: dict[str, Cell], context: Json) -> Json:
    names = arm_names(arms)
    checks = cast("Checks", context["checks"])
    return {
        "runs": context["runs"],
        "models": context["models"],
        "arms": {
            arm: {
                "passed": arms[arm].passed,
                "total": arms[arm].total,
                "pass_rate": round(arms[arm].rate, 4),
                "runs": arms[arm].runs,
                "tokens": arms[arm].tokens,
                "cost_usd": round(arms[arm].cost_usd, 4),
            }
            for arm in names
        },
        "evals": [
            {
                "eval_id": eval_id,
                "eval_name": eval_name,
                "arms": {
                    arm: {"passed": c[arm].passed, "total": c[arm].total, "runs": c[arm].runs}
                    for arm in names
                },
            }
            for (eval_id, eval_name), c in sorted(evals.items())
        ],
        "checks": [
            {
                "text": text,
                "arms": {
                    arm: {"passed": cells[arm].passed, "total": cells[arm].total} for arm in names
                },
            }
            for text, cells in sorted(checks.items())
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate a graded refactor round into benchmark tables.",
        epilog="example:  aggregate.py ~/.cache/claude-evals/refactor/iteration-4",
    )
    parser.add_argument("root", type=Path, help="Iteration directory holding the graded runs.")
    parser.add_argument(
        "--all-checks", action="store_true", help="List every check, not only the ones that moved."
    )
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--json", action="store_true", help="Shorthand for --format json.")
    args = parser.parse_args()

    root: Path = args.root.expanduser().resolve()
    if not root.is_dir():
        emit_error("aggregate.root.missing", f"no such directory: {root}", "stage a round first")
        return 1

    try:
        evals, arms, context = collect(root)
    except (OSError, KeyError, ValueError) as exc:
        emit_error("aggregate.read.failed", str(exc), "re-grade the round with grade.py")
        return 2

    if not evals:
        emit_error(
            "aggregate.runs.empty",
            f"no grading.json under {root}",
            "run grade.py over the run directories first",
        )
        return 3

    context["all_checks"] = args.all_checks
    if args.json or args.format == "json":
        print(json.dumps(as_json(evals, arms, context), indent=2))
    else:
        print(render(root, evals, arms, context))
    return 0


if __name__ == "__main__":
    sys.exit(main())
