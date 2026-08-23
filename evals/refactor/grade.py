#!/usr/bin/env python3
"""Score one refactor eval run against its assertions.

    grade.py <run-dir> [--fixtures DIR]

Reads `<run-dir>/eval_metadata.json` to learn which eval and fixture it is looking at,
grades what the run left in `<run-dir>/repo` and `<run-dir>/outputs`, and writes
`<run-dir>/grading.json`. Every check is mechanical — the files on disk, their AST, and
one run of the fixture's own test suite — so a stored run can be re-graded under a later
rubric.

Run this with an interpreter that has pytest installed; the repo's `.venv/bin/python`
is the one the README uses.

Developer harness, not something an agent calls — see README.md.
"""

# agent-tool: false

from __future__ import annotations

import argparse
import ast
import difflib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import NamedTuple, cast

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))

from grading import expectation, write_grading
from workspace import read_eval_metadata

Json = dict[str, object]

# Produced by running the fixture's own tools, which every run is told to do. Comparing
# them against a fixture that has never been run reads as a change the run made.
JUNK = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".git", ".venv"}

NEST_NODES = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.AsyncFor, ast.AsyncWith)

# `logger.warning(f"...")` — the convention every fixture's CLAUDE.md forbids, and the
# rewrite a run reaches for when it is tidying strings rather than reading the repo.
FSTRING_LOG = re.compile(r"\b(?:logger|logging|log)\.\w+\(\s*f[\"']")
# `x = -x` — the hand-rolled absolute value the ledger fixture repeats four times.
MANUAL_NEGATION = re.compile(r"^\s*(\w+)\s*=\s*-\1\s*$", re.MULTILINE)

# A diffstat in prose or in git's own words. Deliberately two separate patterns: a run
# that reports only what it added has made the claim the skill warns about.
ADDED_COUNT = re.compile(
    r"\b(\d+)\s+(?:line[s]?\s+)?(?:insertion|addition|added)|\+(\d+)\b|added[:\s]+~?(\d+)",
    re.IGNORECASE,
)
DELETED_COUNT = re.compile(
    r"\b(\d+)\s+(?:line[s]?\s+)?(?:deletion|removal|removed|deleted)|-(\d+)\b"
    r"|(?:deleted|removed)[:\s]+~?(\d+)",
    re.IGNORECASE,
)
LEFT_ALONE = re.compile(
    r"left (?:it |them |that |these |those )?(?:alone|as[- ]is|unchanged|untouched)"
    r"|already (?:clean|fine|good|simple|readable|idiomatic|well)"
    r"|no changes? (?:needed|required|made)|not chang|did ?n[o']t (?:change|touch|need)"
    r"|deliberately (?:left|kept)|chose not to|resisted|refrain",
    re.IGNORECASE,
)

# Tools a run reaches for when it is following a verification checklist rather than the
# project in front of it. A fixture that configures none of these should see at most one
# probe apiece — discovering a tool is absent is fair, working through the list is not.
LINTERS = ("ruff", "pyright", "mypy", "black", "eslint", "prettier")
CONFIG_FILES = ("pyproject.toml", "package.json", "setup.cfg", "tox.ini", ".ruff.toml")
TEST_RUNNER = re.compile(r"\b(?:pytest|unittest|tox|nox)\b|\bnpm (?:run )?test\b")


class Spec(NamedTuple):
    """What "the target", "out of scope" and "the why comments" mean for one fixture."""

    target: tuple[str, ...]
    frozen: tuple[str, ...]
    why: tuple[str, ...]


SPECS = {
    # The prompt names pricing.py, so catalog.py and the frozen legacy invoice renderer
    # beside it are the drive-by refactor this fixture is here to catch.
    "pricing-repo": Spec(
        target=("src/storefront/pricing.py",),
        frozen=("src/storefront/legacy_invoice.py", "src/storefront/catalog.py", "CLAUDE.md"),
        why=("off-by-one-cent", "not validated", "priority order"),
    ),
    # The prompt asks for the whole package, so nothing under src/ is out of scope. What
    # this fixture measures is how little a run does when there is little to do.
    "toolkit-repo": Spec(
        target=("src/toolkit",),
        frozen=("CLAUDE.md",),
        why=("closed window",),
    ),
    # posting.py and export.py are as ugly as reconcile.py and twice as old. The prompt
    # points at the last commit; git history is the only thing that separates them.
    "ledger-repo": Spec(
        target=("src/ledger/reconcile.py",),
        frozen=("src/ledger/posting.py", "src/ledger/export.py", "CLAUDE.md"),
        why=("posting order",),
    ),
}

# The five comments that narrate what the next line does. Principle: keep the why, drop
# the what — so these are graded in the opposite direction from Spec.why.
PRICING_WHAT_COMMENTS = (
    "multiply the line out and add it on",
    "look up the tier band",
    "apply the tier discount",
    "work out the tax",
    "add it all up",
)

# Baselines measured on the untouched fixtures. A run has to beat these, not merely
# differ from them.
PRICING_BASELINE = {"depth": 7, "longest": 83}
LEDGER_BASELINE = {"depth": 7, "longest": 39}
TOOLKIT_DIFF_BUDGET = 60


def py_files(root: Path, subpath: str = "") -> dict[str, str]:
    """Every Python file under `root/subpath`, keyed by its path relative to `root`."""
    base = root / subpath if subpath else root
    if not base.exists():
        return {}
    if base.is_file():
        return {str(base.relative_to(root)): base.read_text(encoding="utf-8", errors="replace")}
    out: dict[str, str] = {}
    for path in sorted(base.rglob("*.py")):
        if JUNK & set(path.parts):
            continue
        out[str(path.relative_to(root))] = path.read_text(encoding="utf-8", errors="replace")
    return out


def nesting_depth(node: ast.AST, depth: int = 0) -> int:
    best = depth
    for child in ast.iter_child_nodes(node):
        best = max(
            best, nesting_depth(child, depth + 1 if isinstance(child, NEST_NODES) else depth)
        )
    return best


class Shape(NamedTuple):
    depth: int
    longest: int
    nested_ternaries: int
    public_names: frozenset[str]
    float_calls: int


def shape(sources: dict[str, str]) -> Shape:
    """The structural facts a rubric can read off a set of modules without a model."""
    depth = longest = ternaries = floats = 0
    public: set[str] = set()
    for text in sources.values():
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                depth = max(depth, nesting_depth(node))
                longest = max(longest, (node.end_lineno or node.lineno) - node.lineno + 1)
                if not node.name.startswith("_"):
                    public.add(node.name)
            elif isinstance(node, ast.IfExp) and any(
                isinstance(inner, ast.IfExp) for inner in ast.walk(node) if inner is not node
            ):
                ternaries += 1
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "float"
            ):
                floats += 1
    return Shape(depth, longest, ternaries, frozenset(public), floats)


def changed_lines(fixture: Path, repo: Path, subpath: str) -> tuple[int, int]:
    """Added and deleted line counts between the fixture and the run's copy."""
    before, after = py_files(fixture, subpath), py_files(repo, subpath)
    added = deleted = 0
    for name in sorted(set(before) | set(after)):
        diff = difflib.unified_diff(
            before.get(name, "").splitlines(), after.get(name, "").splitlines(), n=0
        )
        for line in diff:
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                deleted += 1
    return added, deleted


def expand(root: Path, rel: str) -> set[str]:
    """`rel` as a set of file paths — one entry for a file, every file under a directory.

    A target can be a module (`src/ledger/reconcile.py`) or a package (`src/toolkit`),
    and a run is free to add files to the latter, so both trees are enumerated.
    """
    path = root / rel
    if path.is_dir():
        return {
            str(child.relative_to(root))
            for child in path.rglob("*")
            if child.is_file() and not JUNK & set(child.parts)
        }
    return {rel}


def differing(fixture: Path, repo: Path, paths: tuple[str, ...]) -> list[str]:
    """Which of `paths` no longer matches the fixture byte for byte."""
    out: list[str] = []
    for rel in paths:
        for name in sorted(expand(fixture, rel) | expand(repo, rel)):
            source, target = fixture / name, repo / name
            if not target.exists():
                out.append(f"{name} (deleted)")
            elif not source.exists():
                out.append(f"{name} (added)")
            elif source.read_bytes() != target.read_bytes():
                out.append(name)
    return out


def tool_calls(run_dir: Path) -> list[tuple[str, str]]:
    """`(tool, argument)` pairs from `outputs/tool-calls.txt`, oldest first."""
    path = run_dir / "outputs" / "tool-calls.txt"
    if not path.exists():
        return []
    calls: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line:
            name, _, arg = line.partition(" ")
            calls.append((name, arg))
    return calls


def configured_tools(fixture: Path) -> set[str]:
    """Which linters and type checkers the fixture actually sets up."""
    text = ""
    for name in CONFIG_FILES:
        path = fixture / name
        if path.exists():
            text += path.read_text(encoding="utf-8")
    return {tool for tool in LINTERS if f"[tool.{tool}]" in text or f'"{tool}"' in text}


def grade_verification_waste(calls: list[tuple[str, str]], fixture: Path) -> Json:
    """Did the run work through a checklist of tools this project does not have?

    Runs recorded before `_tool_summary` captured Bash commands have nothing to read
    here. Those fail with that said plainly rather than silently leaving the rubric a
    check shorter than the round it is compared against.
    """
    text = "No verification tool absent from the project was invoked more than once"
    commands = [arg for name, arg in calls if name == "Bash"]
    if commands and not any(commands):
        return expectation(text, False, "not computable — predates Bash command capture")
    absent = sorted(set(LINTERS) - configured_tools(fixture))
    counts = {tool: sum(1 for c in commands if re.search(rf"\b{tool}\b", c)) for tool in absent}
    overused = {tool: n for tool, n in counts.items() if n > 1}
    return expectation(
        text,
        not overused,
        f"unconfigured tools invoked more than once: {overused or 'none'}; "
        f"absent from this fixture: {absent}",
    )


def grade_incrementality(calls: list[tuple[str, str]]) -> Json:
    """One change at a time, tests in between — Step 3, which no v1 check reached.

    A run with a single mutation passes outright: `toolkit-repo`'s correct answer is one
    edit, and a floor that demanded two cycles would fail the restraint case for being
    right. Legacy runs, whose Bash commands were never recorded, count any Bash after a
    mutation as the verification, which is how round 1 stays comparable.
    """
    text = "Changes were applied incrementally, with the suite run between them"
    legacy = not any(arg for name, arg in calls if name == "Bash")
    mutations = cycles = 0
    pending = False
    for name, arg in calls:
        if name in ("Edit", "Write"):
            mutations += 1
            pending = True
        elif name == "Bash" and pending and (legacy or TEST_RUNNER.search(arg)):
            cycles += 1
            pending = False
    return expectation(
        text,
        mutations < 2 or cycles >= 2,
        f"{mutations} mutation(s), {cycles} verify cycle(s)"
        f"{' (legacy: any Bash counted as a test run)' if legacy else ''}",
    )


def run_tests(repo: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    tail = (proc.stdout or proc.stderr).strip().splitlines()
    return proc.returncode == 0, tail[-1] if tail else f"exit {proc.returncode}, no output"


def grade(run_dir: Path, fixture: Path) -> list[Json]:
    repo = run_dir / "repo"
    spec = SPECS[fixture.name]
    summary_path = run_dir / "outputs" / "summary.md"
    summary = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ""

    before_src, after_src = py_files(fixture, "src"), py_files(repo, "src")
    after_all = "\n".join(after_src.values())
    before_shape, after_shape = shape(before_src), shape(after_src)

    expectations: list[Json] = []

    def add(text: str, passed: bool, evidence: str) -> None:
        expectations.append(expectation(text, passed, evidence))

    # 1. The one check the whole skill rests on: behaviour is unchanged.
    passed, tail = run_tests(repo)
    add("The repo's own test suite still passes", passed, tail)

    # 2. A named red flag — a simplification that needs the tests edited changed behaviour.
    test_names = sorted(set(py_files(fixture, "tests")) | set(py_files(repo, "tests")))
    edited_tests = differing(fixture, repo, tuple(test_names))
    add("No test file was modified", not edited_tests, f"edited: {edited_tests or 'none'}")

    # 3. The floor. Without it every "did not do X" check below passes for a run that
    # did nothing at all.
    touched = differing(fixture, repo, spec.target) or [
        name for name in after_src if name not in before_src
    ]
    add(
        "The target module actually changed",
        bool(touched),
        f"changed: {touched or 'nothing under ' + ', '.join(spec.target)}",
    )

    # 4. Following project conventions, not imposing preferences. Every fixture's
    # CLAUDE.md says logging takes %s placeholders.
    fstrings = sorted(name for name, text in after_src.items() if FSTRING_LOG.search(text))
    add(
        "No f-string logging call was introduced",
        not fstrings,
        f"f-string logging in: {fstrings or 'none'}",
    )

    # 5. "Comments explaining why — keep these." Anchored on the load-bearing phrase
    # rather than the whole sentence, so a faithful reword still counts.
    lost = [anchor for anchor in spec.why if anchor not in after_all]
    add(
        "Every 'why' comment in the target module survives",
        not lost,
        f"lost: {lost or 'none'} (of {list(spec.why)})",
    )

    # 6. Scope discipline. New files beside the target are a legitimate extraction; a
    # pre-existing file outside it that changed is a drive-by.
    strayed = differing(fixture, repo, spec.frozen)
    add(
        "Files outside the stated scope are byte-identical",
        not strayed,
        f"changed out of scope: {strayed or 'none'}",
    )

    # 7. Clarity over cleverness. pricing.py ships one nested ternary that should go;
    # the other two fixtures ship none, where this is a regression floor.
    add(
        "No nested ternary remains in the changed source",
        after_shape.nested_ternaries == 0,
        f"nested ternaries: {after_shape.nested_ternaries} (fixture had "
        f"{before_shape.nested_ternaries})",
    )

    # 8. "Report added vs deleted lines when you finish." Both halves, because a run
    # that reports only what it added has dodged the question the instruction asks.
    added_m, deleted_m = ADDED_COUNT.search(summary), DELETED_COUNT.search(summary)
    add(
        "The summary reports added and deleted line counts",
        bool(added_m and deleted_m),
        f"added: {added_m.group(0) if added_m else 'MISSING'}; "
        f"deleted: {deleted_m.group(0) if deleted_m else 'MISSING'}",
    )

    # 9 and 10 (rubric v2). The v1 checks saturated at 100%/92% in round 1, with the
    # whole gap resting on assertion 8. These two target what round 1's artifacts showed
    # the arms actually doing differently, which nothing was grading.
    calls = tool_calls(run_dir)
    expectations.append(grade_verification_waste(calls, fixture))
    expectations.append(grade_incrementality(calls))

    if fixture.name == "pricing-repo":
        expectations.extend(grade_pricing(after_src, after_all, before_shape, after_shape))
    elif fixture.name == "toolkit-repo":
        expectations.extend(grade_toolkit(fixture, repo, before_shape, after_shape, summary))
    else:
        expectations.extend(grade_ledger(after_src, after_all, before_shape, after_shape))

    return expectations


def grade_pricing(
    after_src: dict[str, str], after_all: str, before: Shape, after: Shape
) -> list[Json]:
    out: list[Json] = []

    out.append(
        expectation(
            "Nesting depth and function length in pricing.py both came down",
            after.depth < PRICING_BASELINE["depth"] and after.longest < PRICING_BASELINE["longest"],
            f"depth {before.depth} -> {after.depth}, longest function "
            f"{before.longest} -> {after.longest} lines",
        )
    )

    dead = [name for name in ("_legacy_round", "import math") if name in after_all]
    out.append(
        expectation(
            "Dead code is gone (_legacy_round and the unused math import)",
            not dead,
            f"still present: {dead or 'none'}",
        )
    )

    # The item-accumulation loop is copied verbatim into line_totals(). Its warning
    # string is the cheapest thing that survives an extraction unchanged.
    copies = after_all.count("no unit price")
    out.append(
        expectation(
            "The duplicated line-accumulation loop appears only once",
            copies <= 1,
            f"'no unit price' appears {copies} time(s) (fixture: 2)",
        )
    )

    survivors = [c for c in PRICING_WHAT_COMMENTS if c in after_all]
    out.append(
        expectation(
            "At least two of the five 'what' comments were deleted",
            len(survivors) <= 3,
            f"{len(survivors)} of 5 still present: {survivors or 'none'}",
        )
    )

    out.append(
        expectation(
            "Money stayed Decimal — no float() conversion was introduced",
            after.float_calls <= before.float_calls,
            f"float() calls: {before.float_calls} -> {after.float_calls}"
            f" across {len(after_src)} module(s)",
        )
    )
    return out


def grade_toolkit(
    fixture: Path, repo: Path, before: Shape, after: Shape, summary: str
) -> list[Json]:
    out: list[Json] = []

    added, deleted = changed_lines(fixture, repo, "src")
    out.append(
        expectation(
            "The diff stays small — at most 60 changed lines across src/",
            added + deleted <= TOOLKIT_DIFF_BUDGET,
            f"+{added} / -{deleted} = {added + deleted} changed lines "
            f"(budget {TOOLKIT_DIFF_BUDGET})",
        )
    )

    gone = sorted(before.public_names - after.public_names)
    out.append(
        expectation(
            "No public function was renamed or removed",
            not gone,
            f"missing exports: {gone or 'none'} (of {len(before.public_names)})",
        )
    )

    retry = (repo / "src" / "toolkit" / "retry.py").read_text(encoding="utf-8", errors="replace")
    out.append(
        expectation(
            "The _sleep test seam was not inlined away",
            "def _sleep" in retry,
            f"_sleep defined: {'def _sleep' in retry}",
        )
    )

    new_modules = sorted(set(py_files(repo, "src")) - set(py_files(fixture, "src")))
    out.append(
        expectation(
            "No new module was added under src/",
            not new_modules,
            f"new modules: {new_modules or 'none'}",
        )
    )

    match = LEFT_ALONE.search(summary)
    out.append(
        expectation(
            "The summary names something it deliberately left unchanged",
            bool(match),
            f"matched: {match.group(0) if match else 'nothing'}",
        )
    )
    return out


def grade_ledger(
    after_src: dict[str, str], after_all: str, before: Shape, after: Shape
) -> list[Json]:
    out: list[Json] = []

    reconcile = next(
        (text for name, text in after_src.items() if name.endswith("reconcile.py")), ""
    )
    recon_shape = shape({"reconcile.py": reconcile})
    out.append(
        expectation(
            "Nesting depth and function length in reconcile.py both came down",
            recon_shape.depth < LEDGER_BASELINE["depth"]
            and recon_shape.longest < LEDGER_BASELINE["longest"],
            f"depth {LEDGER_BASELINE['depth']} -> {recon_shape.depth}, longest function "
            f"{LEDGER_BASELINE['longest']} -> {recon_shape.longest} lines",
        )
    )

    out.append(
        expectation(
            "Dead code is gone (the unused _collect helper)",
            "_collect" not in after_all,
            f"_collect still present: {'_collect' in after_all}",
        )
    )

    negations = MANUAL_NEGATION.findall(reconcile)
    out.append(
        expectation(
            "The hand-rolled absolute-value block is no longer repeated",
            len(negations) <= 1,
            f"{len(negations)} `x = -x` block(s) remain (fixture: 4)",
        )
    )

    out.append(
        expectation(
            "Money stayed Decimal — no float() conversion was introduced",
            after.float_calls <= before.float_calls,
            f"float() calls: {before.float_calls} -> {after.float_calls}"
            f" across {len(after_src)} module(s)",
        )
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Grade one staged refactor eval run.")
    parser.add_argument("run_dir", type=Path, help="Run directory staged by prepare.py.")
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=HERE / "fixtures",
        help="Where the fixture repos live (default: ./fixtures).",
    )
    args = parser.parse_args()

    run_dir: Path = args.run_dir
    try:
        metadata = read_eval_metadata(run_dir)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: no readable eval_metadata.json in {run_dir} ({exc})", file=sys.stderr)
        return 1

    fixture = args.fixtures / str(metadata["fixture"])
    if not fixture.is_dir():
        print(f"error: fixture not found: {fixture}", file=sys.stderr)
        return 1

    execution: Json | None = None
    timing = run_dir / "timing.json"
    if timing.exists():
        execution = cast("Json", json.loads(timing.read_text(encoding="utf-8")))

    grading = write_grading(run_dir, grade(run_dir, fixture), execution_metrics=execution)
    summary = cast("Json", grading["summary"])
    print(f"{metadata['eval_name']}/{metadata['arm']}: {summary['passed']}/{summary['total']}")
    for e in cast("list[Json]", grading["expectations"]):
        print(f"  [{'PASS' if e['passed'] else 'FAIL'}] {e['text']}")
        if not e["passed"]:
            print(f"         {e['evidence']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
