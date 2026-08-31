#!/usr/bin/env python3
"""Score one python-performance eval run against its assertions.

    grade.py <run-dir> [--no-judgement] [--grader-model sonnet]

Reads `<run-dir>/eval_metadata.json` to learn which eval and fixture it is looking at,
grades what the run left in `<run-dir>/repo` and `<run-dir>/outputs`, and writes
`<run-dir>/grading.json`.

The mechanical half is computed from what is on disk — the files, their AST, the skill's
own static checker run over the result, and two pytest runs (the fixture's suite, and the
one it deliberately does not ship). All of it is re-runnable over a stored run under a
later rubric. The judgement half reads only the run's final summary, with no tool calls
and no arm label, and asks a grader model whether the claims in it are backed by numbers.

Run this with an interpreter that has pytest installed; the repo's `.venv/bin/python` is
the one the README uses.

Developer harness, not something an agent calls — see README.md.
"""

# agent-tool: false

from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import NamedTuple, cast

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))

from grading import expectation, judge, numbered, write_grading
from workspace import find_case, load_cases, read_eval_metadata

Json = dict[str, object]

FIXTURES = HERE / "fixtures"
HIDDEN = HERE / "hidden"
PERF_CHECK = HERE.parent.parent / "skills" / "python-performance" / "scripts" / "perf_check.py"

# Produced by running the fixture's own tools, which every run is free to do. Comparing
# them against a fixture that has never been run reads as a change the run made.
JUNK = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".git", ".venv"}

# A measurement, in whatever form the run reached for. `--profile` is the skill's own
# wrapper; the rest are what a hand-written timing harness is made of.
MEASURED = re.compile(
    r"perf_counter|process_time|cProfile|--profile\b|\btimeit\b|\bpstats\b|hyperfine"
    r"|/usr/bin/time|\btime\.time\(|\bmonotonic\b",
    re.IGNORECASE,
)
# A run that writes its timing harness to a file and then runs it shows only the path in
# the call log — and often writes it outside the repo, where the file scan below cannot
# reach it. The name is the evidence there. `perf_check.py` is deliberately not matchable:
# it is a static checker, and counting it as a measurement would hand every with_skill run
# a pass on the check that matters most.
BENCH_NAME = re.compile(
    r"^Bash\b(?=.*\b[\w./-]*(?:bench|profil|timing|timeit|measure)[\w./-]*\.py\b)"
    r"(?!.*perf_check)",
    re.IGNORECASE | re.DOTALL,
)
MUTATION = re.compile(r"^(?:Edit|Write|NotebookEdit)\b")

# A duration with a unit. Two of them, or one plus a ratio, is a before-and-after.
DURATION = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:ns|µs|μs|us|ms|sec(?:ond)?s?|s|min(?:ute)?s?|hours?|hrs?)\b"
)
RATIO = re.compile(
    r"\b\d+(?:\.\d+)?\s*[x×]\b|\b\d+(?:\.\d+)?\s*%\s*(?:faster|slower|of|less|reduction)"
    r"|\bfrom\s+[\d.]+\s*\w+\s+(?:to|down to)\s+[\d.]+",
    re.IGNORECASE,
)

# "There is nothing here worth changing", in the registers a run reaches for. Deliberately
# loose: what is graded is whether the run said the module is not the problem, not the
# wording it said it in.
NOT_THE_BOTTLENECK = re.compile(
    r"not (?:the|a|our|your) bottleneck|is ?n[o']t the bottleneck|not where the time"
    r"|no[t]? (?:the )?(?:source|cause) of|nothing (?:here )?(?:worth|to (?:fix|change|gain))"
    r"|negligible|microsecond|µs|μs|sub-?millisecond|already fast|not measurabl"
    r"|no measurable|won'?t (?:help|move|matter)|dominated by|elsewhere|not the problem"
    r"|orders? of magnitude (?:below|under|less)",
    re.IGNORECASE,
)
# The same idea, but tied to the thing the user blamed. The second form is the one runs
# actually reach for — the verdict attaches to the subject itself ("that's the cost, not
# the regex") rather than being a sentence about it.
SUBJECT_NEAR = 90
REGEX_SUBJECT = re.compile(r"regex|regexp|pattern|LINE_RE", re.IGNORECASE)
REGEX_CLEARED = re.compile(
    r"\bnot (?:the |your )?(?:regex|regexp|pattern|LINE_RE)\b"
    r"|\brather than the (?:regex|regexp|pattern)\b"
    r"|(?:regex|regexp|pattern|LINE_RE)[^.\n]{0,40}\b(?:is|was|are|were)\s*n[o']?t\b",
    re.IGNORECASE,
)


class Spec(NamedTuple):
    """What "the target", "out of scope" and "the why comments" mean for one fixture.

    `why` anchors on the load-bearing phrase of each comment rather than the whole
    sentence, so a faithful reword still counts as preserved.
    """

    target: str
    frozen: tuple[str, ...]
    why: tuple[str, ...]


SPECS = {
    # exports.py trips four LOW findings and is not on the hot path: rewriting it is the
    # drive-by tidy this case is here to catch. sample_data.py is neither target nor
    # frozen — extending the generator to measure at scale is a fair thing to do.
    "report-repo": Spec(
        target="src/nightly/report.py",
        frozen=("src/nightly/exports.py", "CLAUDE.md"),
        why=("first event of the night", "tie order"),
    ),
    # textutil.py is on the hot path and cheap. It is frozen because "optimise the thing
    # that looks expensive" is exactly the instinct a measurement is supposed to replace.
    "ingest-repo": Spec(
        target="src/ingest/importer.py",
        frozen=("src/ingest/textutil.py", "CLAUDE.md"),
        why=("first match wins", "superseded"),
    ),
    "tidy-repo": Spec(
        target="src/checkout/summarize.py",
        frozen=("src/checkout/pricing_client.py", "CLAUDE.md"),
        why=("counts the promotions",),
    ),
    # rules.json is frozen because shrinking the input is a way to make the number move
    # without making the program faster.
    "logscan-repo": Spec(
        target="src/logscan/scanner.py",
        frozen=("config/rules.json", "CLAUDE.md"),
        why=("pre-2021",),
    ),
}


def emit_error(code: str, message: str, hint: str) -> None:
    print(json.dumps({"error": message, "code": code, "hint": hint}), file=sys.stderr)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def file_digests(root: Path) -> dict[str, str]:
    """Every file under `root`, by content hash.

    Hashes rather than bytes: a run measuring `logscan` writes itself a synthetic log of
    a few hundred megabytes, and holding the tree in memory to answer "did this file
    change" is a needless way to make grading the expensive half of a round.
    """
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or JUNK & set(path.parts):
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        out[str(path.relative_to(root))] = digest.hexdigest()
    return out


def tool_calls(run_dir: Path) -> list[str]:
    return [line for line in read(run_dir / "outputs" / "tool-calls.txt").splitlines() if line]


def first_mutation(tools: list[str]) -> int:
    for i, line in enumerate(tools):
        if MUTATION.match(line):
            return i
    return len(tools)


def run_pytest(repo: Path, args: list[str] | None = None) -> tuple[bool, str]:
    """The fixture's own suite in a throwaway copy, so grading never mutates a stored run."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "repo"
        shutil.copytree(repo, work, ignore=shutil.ignore_patterns(*JUNK))
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *(args or [])],
            cwd=work,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        tail = (proc.stdout or proc.stderr).strip().splitlines()
        return proc.returncode == 0, tail[-1] if tail else "no output"


def run_hidden(repo: Path, fixture: str) -> tuple[bool, str]:
    """The suite the fixture deliberately does not ship, in a copy of the run's repo.

    Never staged into the fixture: a run that can read it has been handed the answer, and
    "the program still does what it did" stops being the thing under test.
    """
    hidden_dir = HIDDEN / fixture
    files = sorted(hidden_dir.glob("test_*.py")) if hidden_dir.is_dir() else []
    if not files:
        return False, f"no hidden suite for {fixture}"
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "repo"
        shutil.copytree(repo, work, ignore=shutil.ignore_patterns(*JUNK))
        names: list[str] = []
        for src in files:
            shutil.copy(src, work / "tests" / src.name)
            names.append(f"tests/{src.name}")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *names],
            cwd=work,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        lines = (proc.stdout or proc.stderr).strip().splitlines()
        failures = [ln for ln in lines if ln.startswith("FAILED") or "Error" in ln][:3]
        summary = lines[-1] if lines else "no output"
        return proc.returncode == 0, "; ".join([summary, *failures])


def perf_findings(path: Path) -> list[Json]:
    """The skill's own static checker over one file, as JSON."""
    proc = subprocess.run(
        [sys.executable, str(PERF_CHECK), str(path), "--format", "json", "--quiet"],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    start = proc.stdout.find("{")
    if start == -1:
        return []
    data = cast("Json", json.loads(proc.stdout[start:]))
    return [cast("Json", i) for i in cast("list[object]", data.get("static", []))]


def categories(findings: list[Json]) -> list[str]:
    return [str(f["category"]) for f in findings]


def parse(source: str) -> ast.Module | None:
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def function_named(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def calls_in(node: ast.AST, name: str) -> int:
    return sum(
        1
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and (
            (isinstance(child.func, ast.Name) and child.func.id == name)
            or (isinstance(child.func, ast.Attribute) and child.func.attr == name)
        )
    )


def calls_inside_loops(tree: ast.Module, names: set[str]) -> list[tuple[str, int]]:
    """Where `names` are called from inside a loop — the shape "read it once" removes."""
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.For | ast.While | ast.AsyncFor):
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            label = (
                child.func.id
                if isinstance(child.func, ast.Name)
                else child.func.attr
                if isinstance(child.func, ast.Attribute)
                else ""
            )
            if label in names:
                found.append((label, child.lineno))
    return found


def assignment_source(source: str, name: str) -> str | None:
    """The source of `name = ...` at module scope, for comparing a literal across runs."""
    tree = parse(source)
    if tree is None:
        return None
    for node in tree.body:
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target]
            if isinstance(node, ast.AnnAssign)
            else []
        )
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.get_source_segment(source, node)
    return None


def changed_lines(before: str, after: str) -> int:
    diff = difflib.unified_diff(before.splitlines(), after.splitlines(), n=0)
    return sum(1 for line in diff if line[:1] in "+-" and not line.startswith(("+++", "---")))


def near(text: str, subject: re.Pattern[str], claim: re.Pattern[str]) -> str | None:
    """A claim made about a particular subject, within `SUBJECT_NEAR` characters of it."""
    for match in subject.finditer(text):
        window = text[max(0, match.start() - SUBJECT_NEAR) : match.end() + SUBJECT_NEAR]
        hit = claim.search(window)
        if hit:
            return window.replace("\n", " ").strip()
    return None


# --- shared checks -----------------------------------------------------------------


def check_tests(repo: Path) -> Json:
    passed, tail = run_pytest(repo)
    return expectation("The repo's own test suite still passes", passed, tail)


def check_tests_untouched(repo: Path, fixture: Path) -> Json:
    before, after = file_digests(fixture), file_digests(repo)
    touched = [
        name
        for name, digest in before.items()
        if name.startswith("tests/") and after.get(name, "") != digest
    ]
    return expectation(
        "No test file was modified",
        not touched,
        f"modified: {', '.join(touched)}" if touched else "every shipped test file is unchanged",
    )


def check_checker_first(tools: list[str]) -> Json:
    edit = first_mutation(tools)
    hits = [line for i, line in enumerate(tools) if "perf_check" in line and i < edit]
    return expectation(
        "perf_check.py was run before the first edit",
        bool(hits),
        hits[0][:160] if hits else f"no perf_check call in the {edit} calls before the first edit",
    )


def measurement_calls(tools: list[str], repo: Path, fixture: Path) -> list[tuple[int, str]]:
    """Every call that is a measurement, by position in the log.

    A run that writes a timing script and runs it shows only the file name, so files the
    run added are read too and attributed to the call that ran them.
    """
    found = [
        (i, line)
        for i, line in enumerate(tools)
        if MEASURED.search(line) or BENCH_NAME.search(line)
    ]
    shipped = set(file_digests(fixture))
    added = [
        path
        for path in (repo / n for n in file_digests(repo) if n not in shipped)
        if path.suffix == ".py" and MEASURED.search(read(path))
    ]
    if added:
        names = {p.name for p in added}
        for i, line in enumerate(tools):
            if any(name in line for name in names):
                found.append((i, f"{line[:120]} (harness: {', '.join(sorted(names))})"))
                break
    return sorted(set(found))


def check_measured(tools: list[str], repo: Path, fixture: Path) -> Json:
    hits = measurement_calls(tools, repo, fixture)
    return expectation(
        "A measurement was actually executed, not just reasoned about",
        bool(hits),
        hits[0][1][:200] if hits else f"nothing timed or profiled across {len(tools)} tool calls",
    )


def check_measured_first(tools: list[str], repo: Path, fixture: Path) -> Json:
    edit = first_mutation(tools)
    hits = [(i, line) for i, line in measurement_calls(tools, repo, fixture) if i < edit]
    return expectation(
        "The measurement came before the first edit",
        bool(hits),
        hits[0][1][:200] if hits else f"first measurement falls after call {edit}, the first edit",
    )


def check_before_after(summary: str) -> Json:
    durations = DURATION.findall(summary)
    ratio = RATIO.search(summary)
    passed = len(durations) >= 2 or (bool(durations) and ratio is not None)
    evidence = f"durations: {', '.join(durations[:6]) or 'none'}"
    if ratio:
        evidence += f"; ratio: {ratio.group(0)}"
    return expectation("The summary reports a before and an after measurement", passed, evidence)


def check_scope(repo: Path, fixture: Path, spec: Spec) -> Json:
    before, after = file_digests(fixture), file_digests(repo)
    moved = [name for name in spec.frozen if after.get(name, "") != before.get(name, "")]
    return expectation(
        "Files outside the stated scope are byte-identical",
        not moved,
        f"changed: {', '.join(moved)}" if moved else f"unchanged: {', '.join(spec.frozen)}",
    )


def check_why_comments(source: str, spec: Spec) -> Json:
    lowered = source.lower()
    missing = [anchor for anchor in spec.why if anchor.lower() not in lowered]
    return expectation(
        "Every 'why' comment in the target module survives",
        not missing,
        f"gone: {', '.join(missing)}" if missing else f"kept: {', '.join(spec.why)}",
    )


def check_target_changed(source: str, original: str) -> Json:
    return expectation(
        "The target module actually changed",
        source.strip() != original.strip(),
        f"{changed_lines(original, source)} changed line(s) in the target",
    )


# --- per-fixture checks ------------------------------------------------------------


def report_checks(source: str, target: Path, repo: Path) -> dict[str, Json]:
    findings = perf_findings(target)
    found = categories(findings)
    high = [str(f["category"]) for f in findings if f["severity"] == "HIGH"]
    joined = re.search(r"\.join\(|StringIO|writelines", source)
    front = re.search(r"\.pop\(\s*0\s*\)|\.insert\(\s*0\s*,|del\s+\w+\[\s*0\s*\]", source)
    as_set = re.search(r"\{[^}\n]*[\"']deploy[\"']|frozenset\(", source)
    hidden_ok, hidden_note = run_hidden(repo, "report-repo")
    return {
        "No HIGH-severity finding remains in the target module": expectation(
            "No HIGH-severity finding remains in the target module",
            not high,
            f"HIGH: {', '.join(high)}"
            if high
            else f"remaining findings: {', '.join(found) or 'none'}",
        ),
        "The digest is joined once rather than accumulated with +=": expectation(
            "The digest is joined once rather than accumulated with +=",
            bool(joined) and "string-concat-loop" not in found,
            f"{joined.group(0) if joined else 'no join/StringIO'}; "
            f"concat finding {'still present' if 'string-concat-loop' in found else 'gone'}",
        ),
        "The event list is no longer drained from the front": expectation(
            "The event list is no longer drained from the front",
            front is None,
            f"found {front.group(0)}" if front else "no pop(0), insert(0, ...) or del seq[0]",
        ),
        "The kind check is a set membership test, not a scan of a list literal": expectation(
            "The kind check is a set membership test, not a scan of a list literal",
            bool(as_set) and "membership-seq" not in found,
            f"{as_set.group(0)[:60] if as_set else 'no set literal or frozenset'}; "
            f"membership finding {'still present' if 'membership-seq' in found else 'gone'}",
        ),
        "The hidden behaviour suite passes": expectation(
            "The hidden behaviour suite passes", hidden_ok, hidden_note
        ),
    }


def ingest_checks(source: str, repo: Path) -> dict[str, Json]:
    tree = parse(source)
    indexed = re.search(
        r"\{[^{}\n]*\[[\"']ref[\"']\][^{}\n]*\bfor\b[^{}\n]*\bin\b"  # dict comprehension
        r"|\w+\[[^\]\n]*\[[\"']ref[\"']\]\s*\]\s*="  # index[c["ref"]] = c
        r"|setdefault\(\s*\w+\[[\"']ref[\"']\]",
        source,
    )
    importer = function_named(tree, "import_rows") if tree else None
    scans = calls_in(importer, "find_customer") if importer else -1
    hidden_ok, hidden_note = run_hidden(repo, "ingest-repo")
    return {
        "The customer export is indexed once instead of scanned per row": expectation(
            "The customer export is indexed once instead of scanned per row",
            bool(indexed),
            indexed.group(0)[:120] if indexed else "no dict keyed on the customer ref",
        ),
        "import_rows no longer calls the per-row scan": expectation(
            "import_rows no longer calls the per-row scan",
            scans == 0,
            "import_rows is gone" if scans < 0 else f"{scans} find_customer call(s) in import_rows",
        ),
        "The hidden behaviour suite passes": expectation(
            "The hidden behaviour suite passes", hidden_ok, hidden_note
        ),
    }


def tidy_checks(repo: Path, fixture: Path, summary: str) -> dict[str, Json]:
    before, after = file_digests(fixture), file_digests(repo)
    churn = sum(
        changed_lines(read(fixture / name), read(repo / name))
        for name in before
        if name.startswith("src/")
    )
    new_modules = [
        name
        for name in after
        if name.startswith("src/") and name.endswith(".py") and name not in before
    ]
    verdict = NOT_THE_BOTTLENECK.search(summary)
    duration = DURATION.search(summary)
    return {
        "The diff stays small — at most 15 changed lines across src/": expectation(
            "The diff stays small — at most 15 changed lines across src/",
            churn <= 15,
            f"{churn} changed line(s) across src/",
        ),
        "The summary says this module is not where the time goes": expectation(
            "The summary says this module is not where the time goes",
            verdict is not None,
            f"matched {verdict.group(0)!r}" if verdict else "no such statement in the summary",
        ),
        "The summary quotes a concrete measured runtime": expectation(
            "The summary quotes a concrete measured runtime",
            duration is not None,
            f"matched {duration.group(0)!r}" if duration else "no timing figure in the summary",
        ),
        "No new module was added under src/": expectation(
            "No new module was added under src/",
            not new_modules,
            f"added: {', '.join(new_modules)}" if new_modules else "no new module under src/",
        ),
    }


def logscan_checks(source: str, original: str, repo: Path, summary: str) -> dict[str, Json]:
    tree = parse(source)
    in_loop = calls_inside_loops(tree, {"open", "load", "loads", "read_text"}) if tree else []
    pattern = assignment_source(source, "LINE_RE")
    was = assignment_source(original, "LINE_RE")
    cleared = REGEX_CLEARED.search(summary)
    exonerated = (
        near(summary, REGEX_SUBJECT, NOT_THE_BOTTLENECK)
        or near(summary, NOT_THE_BOTTLENECK, REGEX_SUBJECT)
        or (cleared.group(0) if cleared else None)
    )
    hidden_ok, hidden_note = run_hidden(repo, "logscan-repo")
    return {
        "The rules file is read once rather than per line": expectation(
            "The rules file is read once rather than per line",
            not in_loop,
            f"in a loop: {', '.join(f'{n}() line {ln}' for n, ln in in_loop)}"
            if in_loop
            else "no open/json.load inside a loop",
        ),
        "The LINE_RE pattern is unchanged": expectation(
            "The LINE_RE pattern is unchanged",
            pattern is not None and pattern == was,
            "identical" if pattern == was else f"LINE_RE {'gone' if pattern is None else 'edited'}",
        ),
        "The summary says the regex is not where the time goes": expectation(
            "The summary says the regex is not where the time goes",
            exonerated is not None,
            f"...{exonerated[:180]}..." if exonerated else "the summary never clears the regex",
        ),
        "The hidden behaviour suite passes": expectation(
            "The hidden behaviour suite passes", hidden_ok, hidden_note
        ),
    }


# --- judgement ---------------------------------------------------------------------

GRADER_PROMPT = """You are grading the write-up a developer left after being asked to make
some Python faster. You can see what they said they did, and nothing else — no diff, no
tool calls. Judge the write-up on its own terms.

The task they were given was:

{prompt}

Judge each numbered assertion below against the write-up, and nothing else.

- Decide on what the write-up shows, not on what its author seemed to intend.
- A number counts as a measurement only if the write-up says what was measured and at what
  input size. "Roughly 100x faster" with nothing behind it is a claim, not evidence.
- Evidence must quote the specific sentence that settles it.
- If the write-up never goes far enough to demonstrate an assertion, it fails, and the
  evidence should say so.

## Assertions

{assertions}

## The write-up

{summary}

Return only a JSON array, one object per assertion, in order:
[{{"index": 1, "passed": true, "evidence": "The write-up says ..."}}]
"""


def judgement(case: Json, summary: str, model: str, cwd: Path) -> list[Json]:
    statements = [str(s) for s in cast("list[object]", case.get("judgement", []))]
    if not statements:
        return []
    prompt = GRADER_PROMPT.format(
        prompt=case["prompt"], assertions=numbered(statements), summary=summary or "(nothing)"
    )
    return judge(statements, prompt, model=model, cwd=cwd)


# --- assembly ----------------------------------------------------------------------


def grade(run_dir: Path, *, with_judgement: bool, grader_model: str) -> Json:
    metadata = read_eval_metadata(run_dir)
    _, cases = load_cases(HERE / "evals.json")
    case = find_case(cases, str(metadata["eval_name"]))
    fixture_name = str(case["fixture"])
    spec = SPECS[fixture_name]

    repo = run_dir / "repo"
    fixture = FIXTURES / fixture_name
    target = repo / spec.target
    source = read(target)
    original = read(fixture / spec.target)
    summary = read(run_dir / "outputs" / "summary.md")
    tools = tool_calls(run_dir)

    shared = (
        check_tests(repo),
        check_tests_untouched(repo, fixture),
        check_checker_first(tools),
        check_measured(tools, repo, fixture),
        check_measured_first(tools, repo, fixture),
        check_before_after(summary),
        check_scope(repo, fixture, spec),
        check_why_comments(source, spec),
        check_target_changed(source, original),
    )
    # Keyed by the assertion's own text, so a case takes the checks it names in
    # evals.json and a rubric that has drifted from the code fails loudly below rather
    # than quietly grading something else. Checks a case does not name go uncomputed.
    computed: dict[str, Json] = {str(check["text"]): check for check in shared}
    per_fixture = {
        "report-repo": lambda: report_checks(source, target, repo),
        "ingest-repo": lambda: ingest_checks(source, repo),
        "tidy-repo": lambda: tidy_checks(repo, fixture, summary),
        "logscan-repo": lambda: logscan_checks(source, original, repo, summary),
    }[fixture_name]()
    computed.update(per_fixture)

    wanted = [str(a) for a in cast("list[object]", case["assertions"])]
    unknown = [text for text in wanted if text not in computed]
    if unknown:
        raise KeyError(
            "no check computes: " + "; ".join(unknown) + " — evals.json and grade.py have drifted"
        )
    expectations = [computed[text] for text in wanted]
    if with_judgement:
        expectations += judgement(case, summary, grader_model, run_dir)

    metrics: Json = {
        "tool_calls": len(tools),
        "edits": sum(1 for line in tools if MUTATION.match(line)),
        "measurements": len(measurement_calls(tools, repo, fixture)),
        "checker_calls": sum(1 for line in tools if "perf_check" in line),
    }
    return write_grading(run_dir, expectations, execution_metrics=metrics)


def main() -> int:
    parser = argparse.ArgumentParser(description="Grade one python-performance eval run.")
    parser.add_argument("run_dir", type=Path, help="Run directory written by run_case.py.")
    parser.add_argument(
        "--no-judgement",
        action="store_true",
        help="Mechanical checks only — no grader model, fully deterministic.",
    )
    parser.add_argument("--grader-model", default="sonnet", help="Grader (default: sonnet).")
    args = parser.parse_args()

    try:
        grading = grade(
            args.run_dir,
            with_judgement=not args.no_judgement,
            grader_model=str(args.grader_model),
        )
    except FileNotFoundError as exc:
        emit_error("grade.run.missing", str(exc), "point at a run directory from run_case.py")
        return 1
    except KeyError as exc:
        emit_error("grade.rubric.drift", str(exc), "align evals.json with grade.py")
        return 1
    summary = cast("Json", grading["summary"])
    print(
        f"{args.run_dir}: {summary['passed']}/{summary['total']} "
        f"({round(float(cast('float', summary['pass_rate'])) * 100)}%)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
