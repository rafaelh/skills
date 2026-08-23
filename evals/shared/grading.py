"""The `grading.json` every suite writes, and the model-graded half of a rubric.

A rubric has two halves. **Mechanical** checks are computed by the suite's own
`grade.py` from what the run left on disk — deterministic, free to rerun, and every
one a proxy, so each reports what it matched. **Judgement** checks are statements
sent to a grader model with the arm label stripped, for the behaviour no regex
reaches. Both arrive here as the same `{text, passed, evidence}` record.

Developer harness, not something an agent calls — see ../eval-approach.md.
"""

# agent-tool: false

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from claude_cli import extract_json_array, run_claude

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

Json = dict[str, object]


def expectation(text: str, passed: bool, evidence: str) -> Json:
    """One graded assertion. `evidence` says what was matched, pass or fail."""
    return {"text": text, "passed": bool(passed), "evidence": evidence}


def numbered(statements: Sequence[str]) -> str:
    """Statements as a 1-based numbered list, matching the indices `judge` aligns on."""
    return "\n".join(f"{i}. {s}" for i, s in enumerate(statements, start=1))


def judge(
    statements: Sequence[str],
    prompt: str,
    *,
    model: str,
    cwd: Path,
    timeout: int = 600,
) -> list[Json]:
    """Grade `statements` with a model, given a prompt the suite has already built.

    The prompt stays with the suite because it has to describe what the grader is
    reading. What is shared is the alignment: verdicts come back keyed by index, and
    a statement the grader skipped fails rather than silently vanishing from the
    denominator.
    """
    result = run_claude(prompt, cwd=cwd, model=model, timeout=timeout)
    by_index = {
        int(cast("int", v["index"])): v for v in extract_json_array(result.text) if "index" in v
    }
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


def write_grading(
    run_dir: Path,
    expectations: Sequence[Json],
    *,
    execution_metrics: Json | None = None,
) -> Json:
    """Write `<run-dir>/grading.json` in the shape the eval viewer reads, and return it.

    Counts live under `summary` and nowhere else — a second copy at the top level is
    a second thing to keep in step. `execution_metrics` is omitted rather than faked
    by suites that cannot see how the run was produced.
    """
    passed = sum(1 for e in expectations if e["passed"])
    total = len(expectations)
    grading: Json = {
        "expectations": list(expectations),
        "summary": {
            "passed": passed,
            "failed": total - passed,
            "total": total,
            "pass_rate": round(passed / total, 3) if total else 0.0,
        },
    }
    if execution_metrics is not None:
        grading["execution_metrics"] = execution_metrics
    (run_dir / "grading.json").write_text(json.dumps(grading, indent=2), encoding="utf-8")
    return grading
