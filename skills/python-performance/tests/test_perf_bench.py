"""Black-box subprocess tests for perf_bench.py."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import textwrap
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "perf_bench.py"

LINEAR_BENCH = """
    def setup(n):
        return list(range(n))

    def run(data):
        return sum(data)
"""


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=None if cwd is None else str(cwd),
    )


def _bench(tmp_path: Path, body: str = LINEAR_BENCH, name: str = "bench.py") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def _ok(r: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    """A successful run's JSON report."""
    assert r.returncode == 0, r.stderr
    payload: dict[str, Any] = json.loads(r.stdout)
    return payload


def _measure(tmp_path: Path, *args: str, body: str = LINEAR_BENCH) -> dict[str, Any]:
    return _ok(_run(str(_bench(tmp_path, body)), "--format", "json", "--quiet", *args))


def test_reports_a_duration_for_each_requested_size(tmp_path: Path) -> None:
    payload = _measure(tmp_path, "--sizes", "10,20,40")

    sizes = [m["size"] for m in payload["measurements"]]
    assert sizes == [10, 20, 40]
    assert all(
        isinstance(m["seconds"], float) and m["seconds"] >= 0 for m in payload["measurements"]
    )


def test_hashes_the_result_of_each_size(tmp_path: Path) -> None:
    first = _measure(tmp_path, "--sizes", "10,20")
    second = _measure(tmp_path, "--sizes", "10,20")

    digests = [m["digest"] for m in first["measurements"]]
    assert all(len(d) == 64 for d in digests)
    assert digests[0] != digests[1], "different input sizes produce different results"
    assert digests == [m["digest"] for m in second["measurements"]], "same code, same digest"


def _error(r: subprocess.CompletedProcess[str]) -> dict[str, str]:
    payload: dict[str, str] = json.loads(r.stderr.strip().splitlines()[-1])
    return payload


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("def run(data):\n    return data\n", id="no-setup"),
        pytest.param("def setup(n):\n    return n\n", id="no-run"),
        pytest.param("VALUE = 1\n", id="neither"),
    ],
)
def test_bench_module_without_setup_and_run_is_a_user_error(tmp_path: Path, body: str) -> None:
    r = _run(str(_bench(tmp_path, body)), "--format", "json")

    assert r.returncode == 1
    assert _error(r)["code"] == "BENCH_INTERFACE"
    assert "Traceback" not in r.stderr


@pytest.mark.parametrize(
    "sizes",
    [
        pytest.param("abc", id="not-a-number"),
        pytest.param("10,-5", id="negative"),
        pytest.param("10,0", id="zero"),
        pytest.param("", id="empty"),
    ],
)
def test_unusable_sizes_is_a_user_error(tmp_path: Path, sizes: str) -> None:
    r = _run(str(_bench(tmp_path)), "--sizes", sizes, "--format", "json")

    assert r.returncode == 1
    assert _error(r)["code"] == "INVALID_SIZES"
    assert "Traceback" not in r.stderr


@pytest.mark.parametrize(
    "repeat", [pytest.param("0", id="zero"), pytest.param("-1", id="negative")]
)
def test_a_repeat_below_one_is_a_user_error(tmp_path: Path, repeat: str) -> None:
    # Timing nothing leaves "seconds" unset, which used to surface as a TypeError out of the
    # curve fit — a system error, exit 2, for what is a mistyped flag.
    r = _run(str(_bench(tmp_path)), "--sizes", "10", "--repeat", repeat, "--format", "json")

    assert r.returncode == 1
    assert _error(r)["code"] == "INVALID_REPEAT"
    assert "Traceback" not in r.stderr


# Sleeping for a computed interval gives the fit a known shape without depending on how fast
# the machine running the suite happens to be.
SLEEP_BENCH = """
    import time

    def setup(n):
        return n

    def run(data):
        time.sleep(data ** {exponent} * {factor})
"""


@pytest.mark.parametrize(
    ("exponent", "factor", "expected"),
    [
        pytest.param(1, "1e-6", "linear", id="linear"),
        pytest.param(2, "1e-9", "quadratic", id="quadratic"),
    ],
)
def test_names_the_growth_it_measured(
    tmp_path: Path, exponent: int, factor: str, expected: str
) -> None:
    payload = _measure(
        tmp_path,
        "--sizes",
        "1000,2000,4000",
        "--repeat",
        "1",
        body=SLEEP_BENCH.format(exponent=exponent, factor=factor),
    )

    assert payload["scaling"]["growth"] == expected
    assert payload["scaling"]["slope"] == pytest.approx(exponent, abs=0.3)


def test_projects_to_an_unmeasured_size_and_marks_it_as_extrapolated(tmp_path: Path) -> None:
    payload = _measure(
        tmp_path,
        "--sizes",
        "1000,2000,4000",
        "--repeat",
        "1",
        "--project",
        "16000",
        body=SLEEP_BENCH.format(exponent=2, factor="1e-9"),
    )

    projection = payload["projection"]
    assert projection["size"] == 16000
    assert projection["seconds"] == pytest.approx(16000**2 * 1e-9, rel=0.4)
    assert projection["measured"] is False
    assert "extrapolat" in projection["basis"]


SLOW_TARGET = """
    import time

    def total(data):
        time.sleep(0.02)
        return sum(data)
"""

FAST_TARGET = """
    def total(data):
        return sum(data)
"""

TARGET_BENCH = """
    import sys

    sys.path.insert(0, ".")
    import target

    def setup(n):
        return list(range(n))

    def run(data):
        return target.total(data)
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )


def _repo_with_committed_baseline(tmp_path: Path, current: str = FAST_TARGET) -> Path:
    """A repo whose committed target is slow and whose working tree holds `current`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "target.py").write_text(textwrap.dedent(SLOW_TARGET), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "baseline")
    (repo / "target.py").write_text(textwrap.dedent(current), encoding="utf-8")
    return repo


def _against_head(tmp_path: Path, sizes: str, current: str = FAST_TARGET) -> dict[str, Any]:
    """Measure a repo's working tree against its committed version."""
    repo = _repo_with_committed_baseline(tmp_path, current)
    bench = _bench(tmp_path, TARGET_BENCH)
    return _ok(
        _run(
            str(bench),
            "--sizes",
            sizes,
            "--repeat",
            "1",
            "--baseline",
            "git:HEAD",
            "--format",
            "json",
            "--quiet",
            cwd=repo,
        )
    )


def test_baseline_times_the_committed_version_against_the_working_tree(tmp_path: Path) -> None:
    payload = _against_head(tmp_path, "100,200")

    comparison = payload["comparison"]
    assert [c["size"] for c in comparison] == [100, 200]
    for c in comparison:
        assert c["baseline_seconds"] > c["current_seconds"]
        assert c["speedup"] > 5


WRONG_TARGET = """
    def total(data):
        return sum(data) + 1
"""


@pytest.mark.parametrize(
    ("current", "equivalent"),
    [
        pytest.param(FAST_TARGET, True, id="same-answer"),
        pytest.param(WRONG_TARGET, False, id="faster-wrong-answer"),
    ],
)
def test_baseline_reports_whether_the_answers_still_match(
    tmp_path: Path, current: str, equivalent: bool
) -> None:
    # A faster wrong answer is a finding, not a crash: _against_head asserts exit 0 either way,
    # so the caller has to read the report to learn the rewrite broke.
    payload = _against_head(tmp_path, "100,200", current)

    assert payload["equivalent"] is equivalent
    assert all(c["same_output"] is equivalent for c in payload["comparison"])


def test_unusable_baseline_is_a_user_error_and_leaves_the_tree_alone(tmp_path: Path) -> None:
    repo = _repo_with_committed_baseline(tmp_path)
    before = (repo / "target.py").read_text(encoding="utf-8")
    bench = _bench(tmp_path, TARGET_BENCH)

    r = _run(
        str(bench),
        "--sizes",
        "100",
        "--repeat",
        "1",
        "--baseline",
        "git:no-such-ref",
        "--format",
        "json",
        cwd=repo,
    )

    assert r.returncode == 1
    assert _error(r)["code"] == "BASELINE_UNAVAILABLE"
    assert "Traceback" not in r.stderr
    assert (repo / "target.py").read_text(encoding="utf-8") == before
    stash = subprocess.run(
        ["git", "stash", "list"], cwd=str(repo), capture_output=True, text=True, check=True
    )
    assert stash.stdout == "", "the baseline must never stash the user's work"


def test_baseline_outside_a_git_repo_is_a_user_error(tmp_path: Path) -> None:
    loose = tmp_path / "loose"
    loose.mkdir()
    bench = _bench(tmp_path, LINEAR_BENCH)

    r = _run(
        str(bench),
        "--sizes",
        "10",
        "--repeat",
        "1",
        "--baseline",
        "git:HEAD",
        "--format",
        "json",
        cwd=loose,
    )

    assert r.returncode == 1
    assert _error(r)["code"] == "BASELINE_UNAVAILABLE"
    assert "Traceback" not in r.stderr


CONCAT_TARGET = """
    def total(data):
        out = ""
        for x in data:
            out += str(x)
        return out
"""


@pytest.mark.parametrize(
    ("target", "categories"),
    [
        pytest.param(CONCAT_TARGET, ["string-concat-loop"], id="finding-remains"),
        pytest.param(FAST_TARGET, [], id="clean"),
    ],
)
def test_recheck_folds_static_findings_into_the_same_report(
    tmp_path: Path, target: str, categories: list[str]
) -> None:
    repo = _repo_with_committed_baseline(tmp_path, target)
    bench = _bench(tmp_path, TARGET_BENCH)

    payload = _ok(
        _run(
            str(bench),
            "--sizes",
            "10",
            "--repeat",
            "1",
            "--recheck",
            "target.py",
            "--format",
            "json",
            "--quiet",
            cwd=repo,
        )
    )

    assert [i["category"] for i in payload["static"]] == categories


def test_text_output_states_the_numbers_and_flags_extrapolation(tmp_path: Path) -> None:
    bench = _bench(tmp_path, SLEEP_BENCH.format(exponent=2, factor="1e-9"))

    r = _run(
        str(bench), "--sizes", "1000,2000,4000", "--repeat", "1", "--project", "16000", "--quiet"
    )

    assert r.returncode == 0, r.stderr
    assert "n=1000" in r.stdout and "n=4000" in r.stdout
    assert "quadratic" in r.stdout
    assert "EXTRAPOLATED" in r.stdout
    with pytest.raises(json.JSONDecodeError):
        json.loads(r.stdout)


def test_quiet_silences_progress_but_never_errors(tmp_path: Path) -> None:
    bench = _bench(tmp_path)

    loud = _run(str(bench), "--sizes", "10", "--repeat", "1", "--format", "json")
    quiet = _run(str(bench), "--sizes", "10", "--repeat", "1", "--format", "json", "--quiet")
    assert loud.stderr.strip() != ""
    assert quiet.stderr == ""

    failed = _run(str(bench), "--sizes", "nope", "--format", "json", "--quiet")
    assert failed.returncode == 1
    assert _error(failed)["code"] == "INVALID_SIZES"


@pytest.mark.parametrize(
    ("body", "mentions"),
    [
        pytest.param("import nosuchmodule\n", "nosuchmodule", id="import-time"),
        pytest.param(
            "def setup(n):\n    raise ValueError('too big')\n\ndef run(data):\n    return data\n",
            "n=10",
            id="setup-raises",
        ),
        pytest.param(
            "def setup(n):\n    return n\n\ndef run(data):\n    raise KeyError('missing')\n",
            "n=10",
            id="run-raises",
        ),
    ],
)
def test_a_bench_that_blows_up_is_reported_not_dumped(
    tmp_path: Path, body: str, mentions: str
) -> None:
    r = _run(str(_bench(tmp_path, body)), "--sizes", "10", "--repeat", "1", "--format", "json")

    assert r.returncode == 1
    err = _error(r)
    assert err["code"] == "BENCH_FAILED"
    assert mentions in err["error"]
    assert "Traceback" not in r.stderr
