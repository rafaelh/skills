#!/usr/bin/env python3
"""Measure a Python change: time it across input sizes, and prove it still returns the same answers.

The agent supplies the repo-specific half — a bench module defining `setup(n)` and `run(data)`.
Everything that is identical in every benchmark (the size sweep, best-of-k timing, hashing the
result, fitting the growth curve, running the pre-edit tree) lives here.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from typing import Any

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_SYSTEM_ERROR = 2
EXIT_NOT_FOUND = 3


def _parse_sizes(raw: str) -> list[int]:
    """Comma-separated positive ints; anything else raises ValueError."""
    parts = [chunk.strip() for chunk in raw.split(",") if chunk.strip()]
    if not parts:
        msg = "no sizes given"
        raise ValueError(msg)
    sizes = [int(chunk) for chunk in parts]  # ValueError on non-numeric
    if any(n < 1 for n in sizes):
        msg = "sizes must be 1 or greater"
        raise ValueError(msg)
    return sizes


def _emit_error(error: str, code: str, hint: str = "") -> None:
    """Structured error to stderr; never to stdout."""
    payload: dict[str, str] = {"error": error, "code": code}
    if hint:
        payload["hint"] = hint
    print(json.dumps(payload), file=sys.stderr)


class BenchError(Exception):
    """The bench module could not be imported, or raised while being measured."""


class CheckerError(Exception):
    """The static re-check could not be run."""


class NothingMatchedError(Exception):
    """The re-check paths held no Python to analyse."""


class BaselineError(Exception):
    """The pre-edit tree could not be produced or measured."""


def _log(msg: str, quiet: bool) -> None:
    if not quiet:
        print(msg, file=sys.stderr)


def _load_bench(path: Path) -> Any:
    if not path.is_file():
        msg = f"{path} does not exist"
        raise BenchError(msg)
    spec = importlib.util.spec_from_file_location("perf_bench_target", path)
    if spec is None or spec.loader is None:
        msg = f"{path} is not importable as Python"
        raise BenchError(msg)
    module = importlib.util.module_from_spec(spec)
    # The bench imports the code under test, so its own directory has to be importable too.
    sys.path.insert(0, str(path.resolve().parent))
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        msg = f"{path} failed to import: {type(exc).__name__}: {exc}"
        raise BenchError(msg) from exc
    return module


def digest(result: Any) -> str:
    """Fingerprint what `run` returned, so a rewrite can be shown to return the same thing.

    Hashing the repr rather than a normalised form is deliberate: it captures ordering, and
    ordering — tie-breaks, which duplicate wins — is the behaviour a performance rewrite is
    most likely to change without any test noticing.
    """
    return hashlib.sha256(repr(result).encode("utf-8", "replace")).hexdigest()


def measure(module: Any, sizes: list[int], repeat: int) -> list[dict[str, Any]]:
    """Time `run` once per size, keeping the fastest of `repeat` attempts."""
    results: list[dict[str, Any]] = []
    for n in sizes:
        try:
            data = module.setup(n)
        except Exception as exc:
            msg = f"setup(n={n}) raised {type(exc).__name__}: {exc}"
            raise BenchError(msg) from exc
        timings: list[float] = []
        out: Any = None
        for _ in range(repeat):
            start = time.perf_counter()
            try:
                out = module.run(data)
            except Exception as exc:
                msg = f"run() raised {type(exc).__name__}: {exc} at n={n}"
                raise BenchError(msg) from exc
            timings.append(time.perf_counter() - start)
        results.append({"size": n, "seconds": min(timings), "digest": digest(out)})
    return results


# Coarse on purpose. A log-log slope over three or four points separates "grows with the input"
# from "grows faster than the input", which is the distinction that decides whether a rewrite is
# worth doing; it cannot honestly tell n log n from n, so it does not claim to.
_GROWTH = ((0.35, "constant"), (1.35, "linear"), (1.75, "superlinear"), (2.5, "quadratic"))


def _fit(measurements: list[dict[str, Any]]) -> tuple[float, float, int] | None:
    """Least-squares (slope, intercept) of log(seconds) against log(size), plus the point count."""
    points = [
        (math.log(m["size"]), math.log(m["seconds"]))
        for m in measurements
        if m["size"] > 0 and m["seconds"] > 0
    ]
    if len(points) < 2:
        return None
    mx = sum(x for x, _ in points) / len(points)
    my = sum(y for _, y in points) / len(points)
    denominator = sum((x - mx) ** 2 for x, _ in points)
    if denominator == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in points) / denominator
    return slope, my - slope * mx, len(points)


def fit_growth(measurements: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Name the exponent of the growth the measurements describe."""
    fit = _fit(measurements)
    if fit is None:
        return None
    slope, _, count = fit
    growth = next((name for limit, name in _GROWTH if slope < limit), "worse than quadratic")
    return {"slope": round(slope, 2), "growth": growth, "points": count}


def project(measurements: list[dict[str, Any]], size: int) -> dict[str, Any] | None:
    """Estimate the time at a size that was never run.

    Marked `measured: false` and carries its own basis string, because the failure this exists to
    prevent is a projected number being written up as if it had been timed.
    """
    for m in measurements:
        if m["size"] == size:
            return {"size": size, "seconds": m["seconds"], "measured": True, "basis": "measured"}
    fit = _fit(measurements)
    if fit is None:
        return None
    slope, intercept, count = fit
    return {
        "size": size,
        "seconds": math.exp(intercept + slope * math.log(size)),
        "measured": False,
        "basis": f"extrapolated from slope {slope:.2f} over {count} measured points",
    }


def recheck(paths: list[str]) -> list[dict[str, Any]]:
    """Re-run the static checker on the edited files, so one call covers timing and findings.

    Runs are otherwise inclined to spend a whole extra turn on perf_check.py after editing, which
    at this transcript length is the most expensive line item in the whole workflow.
    """
    checker = Path(__file__).resolve().parent / "perf_check.py"
    done = subprocess.run(
        [sys.executable, str(checker), *paths, "--format", "json", "--quiet"],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode == EXIT_NOT_FOUND:
        raise NothingMatchedError(done.stderr.strip() or "no Python files matched")
    if done.returncode != 0:
        raise CheckerError(done.stderr.strip() or "perf_check.py failed")
    payload: dict[str, Any] = json.loads(done.stdout)
    findings: list[dict[str, Any]] = payload.get("static", [])
    return findings


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise BaselineError(done.stderr.strip() or f"git {' '.join(args)} failed")
    return done.stdout.strip()


def measure_baseline(ref: str, bench: Path, sizes: list[int], repeat: int) -> list[dict[str, Any]]:
    """Measure `bench` against the tree at `ref`, in a throwaway worktree.

    A detached worktree, never `git stash` — the baseline must not touch the tree the user is
    working in, and a stash that fails to pop loses their work.
    """
    root = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel"))
    tmp = Path(tempfile.mkdtemp(prefix="perf-bench-baseline-"))
    checkout = tmp / "tree"
    try:
        _git(root, "worktree", "add", "--detach", str(checkout), ref)
        done = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                str(bench.resolve()),
                "--sizes",
                ",".join(str(n) for n in sizes),
                "--repeat",
                str(repeat),
                "--format",
                "json",
                "--quiet",
            ],
            cwd=str(checkout),
            capture_output=True,
            text=True,
            check=False,
        )
        if done.returncode != 0:
            raise BaselineError(done.stderr.strip() or f"bench failed at {ref}")
        payload: dict[str, Any] = json.loads(done.stdout)
        return payload["measurements"]
    finally:
        if checkout.exists():
            # Best-effort: a cleanup failure must not mask why the measurement failed.
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(checkout)],
                cwd=str(root),
                capture_output=True,
                text=True,
                check=False,
            )
        shutil.rmtree(tmp, ignore_errors=True)


def compare(baseline: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pair the two runs by size and state the speedup at each."""
    by_size = {m["size"]: m for m in baseline}
    rows: list[dict[str, Any]] = []
    for now in current:
        was = by_size.get(now["size"])
        if was is None:
            continue
        before, after = was["seconds"], now["seconds"]
        rows.append(
            {
                "size": now["size"],
                "baseline_seconds": before,
                "current_seconds": after,
                "speedup": (before / after) if after > 0 else None,
                "same_output": was["digest"] == now["digest"],
            }
        )
    return rows


def _seconds(value: float) -> str:
    return f"{value:.4f}s" if value < 1 else f"{value:.2f}s"


def print_report(payload: dict[str, Any]) -> None:
    """The same content as --format json, laid out for someone reading the terminal."""
    print("\nMeasured")
    for m in payload["measurements"]:
        print(f"  n={m['size']:<12} {_seconds(m['seconds']):>10}   sha {m['digest'][:12]}")

    scaling = payload.get("scaling")
    if scaling:
        print(
            f"\nGrowth: slope {scaling['slope']:.2f} over "
            f"{scaling['points']} points — {scaling['growth']}"
        )

    projection = payload.get("projection")
    if projection:
        label = "measured" if projection["measured"] else "EXTRAPOLATED — not measured"
        print(f"Projected at {projection['size']}: {_seconds(projection['seconds'])}  ({label})")

    comparison = payload.get("comparison")
    if comparison:
        ref = payload.get("baseline", {}).get("ref", "baseline")
        print(f"\nAgainst {ref}")
        for row in comparison:
            speedup = "n/a" if row["speedup"] is None else f"{row['speedup']:.1f}x"
            match = "same output" if row["same_output"] else "OUTPUT DIFFERS"
            print(
                f"  n={row['size']:<12} {_seconds(row['baseline_seconds']):>10} -> "
                f"{_seconds(row['current_seconds']):>10}   {speedup:>8}   {match}"
            )
        verdict = (
            "identical at every size measured"
            if payload["equivalent"]
            else "DIFFERENT — the rewrite does not return the same answers"
        )
        print(f"Output equivalence: {verdict}")

    if "static" in payload:
        findings = payload["static"]
        if not findings:
            print("\nStatic re-check: no findings")
        else:
            print(f"\nStatic re-check — {len(findings)} finding(s)")
            for i in findings:
                print(f"  {i['severity']:<6} {i['category']:<24} {i['file']}:{i['line']}")
    print()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="perf_bench.py",
        description="Time a change across input sizes and check it returns the same answers.",
        epilog=textwrap.dedent("""\
            The bench module is yours to write and is the only repo-specific part:

              # bench.py
              import sys; sys.path.insert(0, "src")
              from nightly import report

              def setup(n):     # build the input; not timed
                  return [make_event(i) for i in range(n)]

              def run(data):    # the code under test; timed, and its result is hashed
                  return report.build_report(data)

            examples:
              perf_bench.py bench.py --baseline git:HEAD          # before, after and the speed-up
              perf_bench.py bench.py --baseline git:HEAD --recheck src/nightly/report.py
              perf_bench.py bench.py --sizes 5000,20000,40000     # growth curve, nothing to compare
              perf_bench.py bench.py --sizes 5000,20000 --project 400000
              perf_bench.py bench.py --format json                # machine-readable output
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("bench", metavar="BENCH", help="module defining setup(n) and run(data)")
    p.add_argument("--sizes", default="1000,4000,16000", help="comma-separated input sizes")
    p.add_argument("--repeat", type=int, default=3, help="attempts per size, fastest wins")
    p.add_argument(
        "--project",
        type=int,
        metavar="N",
        help="estimate the time at input size N; reported as extrapolated, never as measured",
    )
    p.add_argument(
        "--recheck",
        nargs="+",
        metavar="PATH",
        help="re-run perf_check.py over these paths and fold the findings into this report",
    )
    p.add_argument(
        "--baseline",
        metavar="REF",
        help="also measure the tree at a git ref, e.g. --baseline git:HEAD, and compare",
    )
    p.add_argument("--format", choices=["json", "text"], default="text")
    p.add_argument("--json", action="store_true", help="Alias for --format json.")
    p.add_argument("--quiet", action="store_true", help="Suppress informational stderr.")
    return p


def _dispatch(argv: list[str] | None) -> int:
    args = _build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        sizes = _parse_sizes(args.sizes)
    except ValueError as exc:
        _emit_error(
            f"--sizes {args.sizes!r}: {exc}",
            "INVALID_SIZES",
            hint="Pass a comma-separated list of positive integers, e.g. --sizes 5000,20000,40000",
        )
        return EXIT_USER_ERROR

    if args.repeat < 1:
        _emit_error(
            f"--repeat must be 1 or greater, got {args.repeat}",
            "INVALID_REPEAT",
            hint="Pass a positive count, e.g. --repeat 3",
        )
        return EXIT_USER_ERROR

    try:
        module = _load_bench(Path(args.bench))
    except BenchError as exc:
        _emit_error(
            str(exc),
            "BENCH_FAILED",
            hint="A bench module defines setup(n) -> input and run(data) -> result, "
            "and imports the code under test relative to the current directory.",
        )
        return EXIT_USER_ERROR

    missing = [name for name in ("setup", "run") if not callable(getattr(module, name, None))]
    if missing:
        _emit_error(
            f"{args.bench} does not define {' and '.join(missing)}",
            "BENCH_INTERFACE",
            hint="A bench module defines setup(n) -> input and run(data) -> result; "
            "only run() is timed.",
        )
        return EXIT_USER_ERROR

    _log(f"Timing {len(sizes)} size(s), best of {args.repeat}...", quiet=args.quiet)
    try:
        measurements = measure(module, sizes, args.repeat)
    except BenchError as exc:
        _emit_error(
            str(exc),
            "BENCH_FAILED",
            hint="Fix the bench module, or drop to a size the code under test can handle.",
        )
        return EXIT_USER_ERROR
    payload: dict[str, Any] = {"measurements": measurements}
    scaling = fit_growth(measurements)
    if scaling is not None:
        payload["scaling"] = scaling
    if args.project is not None:
        projection = project(measurements, args.project)
        if projection is not None:
            payload["projection"] = projection
    if args.baseline:
        ref = args.baseline.removeprefix("git:")
        try:
            baseline = measure_baseline(ref, Path(args.bench), sizes, args.repeat)
        except BaselineError as exc:
            _emit_error(
                f"cannot measure the tree at {ref}: {exc}",
                "BASELINE_UNAVAILABLE",
                hint="Run from inside a git repository and pass a ref that resolves, "
                "e.g. --baseline git:HEAD.",
            )
            return EXIT_USER_ERROR
        payload["baseline"] = {"ref": ref, "measurements": baseline}
        rows = compare(baseline, measurements)
        payload["comparison"] = rows
        # Reported, not raised: a faster wrong answer is a finding the caller has to read, and
        # perf_check.py likewise never turns a finding into an exit code.
        payload["equivalent"] = all(row["same_output"] for row in rows)

    if args.recheck:
        try:
            payload["static"] = recheck(args.recheck)
        except NothingMatchedError as exc:
            _emit_error(
                f"nothing to re-check: {exc}",
                "RECHECK_EMPTY",
                hint="Pass a .py file, or a directory holding one.",
            )
            return EXIT_NOT_FOUND
        except CheckerError as exc:
            _emit_error(
                f"static re-check failed: {exc}",
                "RECHECK_FAILED",
                hint="Pass paths that exist relative to the current directory.",
            )
            return EXIT_USER_ERROR

    if args.json or args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        print_report(payload)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    try:
        return _dispatch(argv)
    except KeyboardInterrupt:
        _emit_error("interrupted", "INTERRUPTED")
        return EXIT_SYSTEM_ERROR
    except Exception as exc:
        _emit_error(
            f"{type(exc).__name__}: {exc}",
            "UNEXPECTED_ERROR",
            hint="Re-run with --format json to capture the full report, "
            "or with fewer sizes to isolate the failure.",
        )
        return EXIT_SYSTEM_ERROR


if __name__ == "__main__":
    sys.exit(main())
