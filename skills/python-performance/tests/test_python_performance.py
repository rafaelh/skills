"""Black-box subprocess tests for perf_check.py."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys
import textwrap
from typing import Any

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "perf_check.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def _analyze(tmp_path: Path, name: str, body: str) -> dict[str, Any]:
    """Write a fixture file, check it, and return the parsed JSON report."""
    fixture = _write(tmp_path, name, body)
    r = _run(str(fixture), "--format", "json", "--quiet")
    assert r.returncode == 0, r.stderr
    payload: dict[str, Any] = json.loads(r.stdout)
    return payload


def _issues(payload: dict[str, Any], category: str) -> list[dict[str, Any]]:
    return [issue for issue in payload["static"] if issue["category"] == category]


def _lines(payload: dict[str, Any], category: str) -> list[int]:
    return [issue["line"] for issue in _issues(payload, category)]


def _categories(payload: dict[str, Any]) -> set[str]:
    return {issue["category"] for issue in payload["static"]}


def test_help_exits_zero() -> None:
    r = _run("--help")
    assert r.returncode == 0
    assert "examples:" in r.stdout.lower()


def test_no_args_exits_1() -> None:
    r = _run()
    assert r.returncode == 1


def test_missing_path_emits_structured_error() -> None:
    r = _run("/nowhere/missing.py", "--format", "json")
    assert r.returncode == 1
    err = json.loads(r.stderr.splitlines()[-1])
    assert err["code"] == "PATH_NOT_FOUND"


def test_clean_file_returns_no_issues(tmp_path: Path) -> None:
    payload = _analyze(
        tmp_path,
        "clean.py",
        """\
        def main():
            return 0
        """,
    )
    assert payload["meta"]["issues_high"] == 0
    assert payload["meta"]["files_analyzed"] == 1


def test_string_concat_loop_flagged(tmp_path: Path) -> None:
    payload = _analyze(
        tmp_path,
        "concat.py",
        """\
        def build():
            out = ""
            for i in range(100):
                out += "x"
            return out
        """,
    )
    assert "string-concat-loop" in _categories(payload)


def test_concat_of_variable_into_str_buffer_flagged(tmp_path: Path) -> None:
    """The FAQ's core case: accumulating a variable, not a literal."""
    payload = _analyze(
        tmp_path,
        "buffer.py",
        """\
        def build(chunks):
            out = ""
            for s in chunks:
                out += s
            return out
        """,
    )
    assert "string-concat-loop" in _categories(payload)


def test_rebinding_concat_flagged(tmp_path: Path) -> None:
    """'out = out + s' and 'out = s + out' are quadratic just like '+='."""
    payload = _analyze(
        tmp_path,
        "rebind.py",
        """\
        def build(chunks):
            head = ""
            tail = ""
            for s in chunks:
                head = head + s
                tail = s + tail
            return head, tail
        """,
    )
    assert _lines(payload, "string-concat-loop") == [5, 6]


def test_bytes_concat_flagged_separately(tmp_path: Path) -> None:
    payload = _analyze(
        tmp_path,
        "raw.py",
        """\
        def build(chunks):
            out = b""
            for b in chunks:
                out += b
            return out
        """,
    )
    issues = _issues(payload, "bytes-concat-loop")
    assert len(issues) == 1
    assert "bytearray" in issues[0]["fix"]


def test_faq_recommended_idioms_not_flagged(tmp_path: Path) -> None:
    """bytearray +=, StringIO, list+join and numeric += are the fixes, not the bug."""
    payload = _analyze(
        tmp_path,
        "clean_accum.py",
        """\
        import io

        def build(chunks):
            buf = bytearray()
            sio = io.StringIO()
            parts = []
            total = 0
            for c in chunks:
                buf += c
                sio.write(str(c))
                total += len(c)
            return b"".join([bytes(buf)]), "".join(parts), sio.getvalue(), total
        """,
    )
    cats = _categories(payload)
    assert "string-concat-loop" not in cats
    assert "bytes-concat-loop" not in cats


def test_buffer_tracking_does_not_leak_across_functions(tmp_path: Path) -> None:
    """'out' is a str buffer in one function; a list in the next."""
    payload = _analyze(
        tmp_path,
        "scoped.py",
        """\
        def a(chunks):
            out = ""
            return out

        def b(chunks):
            out = []
            for c in chunks:
                out += [c]
            return out
        """,
    )
    assert "string-concat-loop" not in _categories(payload)


def test_import_in_loop_flagged_but_lazy_function_import_is_not(tmp_path: Path) -> None:
    """Lazy imports at function top are a deliberate startup optimisation for agent tools."""
    payload = _analyze(
        tmp_path,
        "imports.py",
        """\
        def lazy(records):
            import csv
            return csv, records

        def eager(records):
            for r in records:
                import statistics
                statistics.mean(r)
            for r in records:
                from math import sqrt
                sqrt(r)
        """,
    )
    assert _lines(payload, "import-in-loop") == [7, 10]


def test_dict_init_idioms_flagged(tmp_path: Path) -> None:
    payload = _analyze(
        tmp_path,
        "dicts.py",
        """\
        def tally(records):
            groups = {}
            counts = {}
            for r in records:
                groups.setdefault(r.key, []).append(r)
                counts[r.key] = counts.get(r.key, 0) + 1
            return groups, counts
        """,
    )
    assert _lines(payload, "dict-init-idiom") == [5, 6]


def test_defaultdict_and_scalar_setdefault_not_flagged(tmp_path: Path) -> None:
    """defaultdict is the fix; a scalar setdefault builds nothing per call."""
    payload = _analyze(
        tmp_path,
        "clean_dicts.py",
        """\
        from collections import defaultdict

        def tally(records):
            grouped = defaultdict(list)
            cfg = {}
            for r in records:
                grouped[r.key].append(r)
                cfg.setdefault(r.key, 0)
            return grouped, cfg
        """,
    )
    assert "dict-init-idiom" not in _categories(payload)


def test_cmp_to_key_flagged_outside_loops(tmp_path: Path) -> None:
    payload = _analyze(
        tmp_path,
        "sorting.py",
        """\
        from functools import cmp_to_key

        def order(rows):
            fast = sorted(rows, key=lambda r: r.score)
            slow = sorted(rows, key=cmp_to_key(lambda a, b: (a > b) - (a < b)))
            return fast, slow
        """,
    )
    assert _lines(payload, "cmp-to-key") == [5]


def test_materialize_then_slice_flagged(tmp_path: Path) -> None:
    payload = _analyze(
        tmp_path,
        "slicing.py",
        """\
        def head(rows, path):
            a = list(rows)[:10]
            with open(path) as fh:
                b = fh.readlines()[:5]
            c = rows[:10]
            return a, b, c
        """,
    )
    assert _lines(payload, "materialize-then-slice") == [2, 4]


def test_sort_then_slice_picks_the_right_replacement(tmp_path: Path) -> None:
    """reverse= flips nsmallest/nlargest and min/max."""
    payload = _analyze(
        tmp_path,
        "sorting.py",
        """\
        def pick(rows):
            return (
                sorted(rows)[:10],
                sorted(rows, reverse=True)[:3],
                sorted(rows)[0],
                sorted(rows)[-1],
                sorted(rows, reverse=True)[0],
                sorted(rows)[3],
            )
        """,
    )
    fixes = [issue["fix"] for issue in _issues(payload, "sort-then-slice")]
    assert len(fixes) == 5, "sorted(rows)[3] is neither a head slice nor an endpoint"
    assert "nsmallest" in fixes[0]
    assert "nlargest" in fixes[1]
    assert fixes[2].startswith("Use min(")
    assert fixes[3].startswith("Use max(")
    assert fixes[4].startswith("Use max("), "reverse=True flips [0] to max"


def test_pairwise_and_flatten_flagged(tmp_path: Path) -> None:
    payload = _analyze(
        tmp_path,
        "iterating.py",
        """\
        def walk(seq, nested):
            pairs = []
            for i in range(len(seq) - 1):
                pairs.append((seq[i], seq[i + 1]))
            flat = []
            for sub in nested:
                for x in sub:
                    flat.append(x)
            return pairs, flat
        """,
    )
    range_len = _issues(payload, "range-len")[0]
    assert "pairwise" in range_len["fix"]
    assert range_len["severity"] == "MEDIUM"
    assert _lines(payload, "manual-flatten") == [6]


def test_itertools_idioms_and_near_misses_not_flagged(tmp_path: Path) -> None:
    payload = _analyze(
        tmp_path,
        "clean_iter.py",
        """\
        import heapq
        import itertools

        def walk(rows, nested, seq):
            out = []
            for sub in nested:
                for x in sub:
                    out.append(x * 2)
            windows = [seq[i : i + 3] for i in range(len(seq) - 3)]
            return (
                list(itertools.islice(rows, 10)),
                heapq.nsmallest(10, rows),
                list(itertools.chain.from_iterable(nested)),
                list(itertools.pairwise(seq)),
                out,
                windows,
            )
        """,
    )
    cats = _categories(payload)
    assert not cats & {"materialize-then-slice", "sort-then-slice", "manual-flatten"}
    assert "range-len" not in cats, "offset of 3 is a window, not pairwise"


def test_append_in_loop_only_fires_on_a_convertible_body(tmp_path: Path) -> None:
    """Only a loop whose entire body is one append maps to a comprehension."""
    payload = _analyze(
        tmp_path,
        "appends.py",
        """\
        def collect(rows, other):
            a = []
            for r in rows:
                a.append(r.name)
            d = []
            for r in rows:
                key = r.name.strip()
                d.append(key)
            e = []
            for r in rows:
                if r.ok:
                    e.append(r)
            f = []
            for r in rows:
                f.append(r)
                other.notify(r)
            g = []
            i = 0
            while i < len(rows):
                g.append(rows[i])
                i += 1
            return a, d, e, f, g
        """,
    )
    assert _lines(payload, "append-in-loop") == [3]


def test_flatten_does_not_double_report_its_inner_append(tmp_path: Path) -> None:
    payload = _analyze(
        tmp_path,
        "flatten.py",
        """\
        def walk(nested):
            c = []
            for sub in nested:
                for x in sub:
                    c.append(x)
            return c
        """,
    )
    assert [issue["category"] for issue in payload["static"]] == ["manual-flatten"]


def test_list_as_queue_flagged(tmp_path: Path) -> None:
    payload = _analyze(
        tmp_path,
        "queueing.py",
        """\
        from collections import deque

        def drain(items):
            queue = list(items)
            while queue:
                head = queue.pop(0)
                queue.insert(0, head)
                del queue[0]
            dq = deque(items)
            while dq:
                dq.popleft()
            return queue.pop()
        """,
    )
    issues = _issues(payload, "list-as-queue")
    assert [issue["line"] for issue in issues] == [6, 7, 8]
    assert all(issue["severity"] == "HIGH" for issue in issues)


def test_deepcopy_and_subprocess_in_loop_flagged(tmp_path: Path) -> None:
    payload = _analyze(
        tmp_path,
        "spawning.py",
        """\
        import copy
        import os
        import subprocess

        def work(items, tpl, paths):
            for i in items:
                copy.deepcopy(tpl)
            for p in paths:
                subprocess.run(["file", p], check=False)
                os.system("stat " + p)
            return copy.deepcopy(tpl)
        """,
    )
    assert _lines(payload, "deepcopy-in-loop") == [7], "the deepcopy on line 11 is outside any loop"
    assert _lines(payload, "subprocess-in-loop") == [9, 10]


def test_spawn_found_through_alias_and_from_import(tmp_path: Path) -> None:
    payload = _analyze(
        tmp_path,
        "aliased.py",
        """\
        import subprocess as sp
        from subprocess import check_output, run as launch

        def work(items):
            for i in items:
                sp.run(["worker", i], check=False)
                launch(["worker", i], check=False)
                check_output(["worker", i])
                subprocess.getoutput("worker " + i)
        """,
    )
    assert _lines(payload, "subprocess-in-loop") == [6, 7, 8, 9]


def test_spawn_in_a_helper_called_per_iteration_flagged(tmp_path: Path) -> None:
    """The spawn is one call away from the loop, which costs exactly the same."""
    payload = _analyze(
        tmp_path,
        "indirect.py",
        """\
        import subprocess

        def render(item):
            return subprocess.run(["python", "worker.py", item], check=False)

        def via(item):
            return render(item)

        def work(items):
            for i in items:
                via(i)
            return [render(i) for i in items]

        def unrelated(items):
            for i in items:
                print(i)
        """,
    )
    issues = _issues(payload, "subprocess-in-loop")
    assert [issue["line"] for issue in issues] == [11, 12], "the chain via() -> render() resolves"
    assert issues[0]["message"].startswith("via() reaches subprocess.run()"), (
        "the message names the call the loop makes, and the spawn it ends at"
    )


def test_spawn_findings_are_high(tmp_path: Path) -> None:
    payload = _analyze(
        tmp_path,
        "spawning_severity.py",
        """\
        import subprocess

        def work(items):
            for i in items:
                subprocess.run(["worker", i], check=False)
        """,
    )
    assert [issue["severity"] for issue in _issues(payload, "subprocess-in-loop")] == ["HIGH"]


def test_heavy_import_used_by_one_function_flagged(tmp_path: Path) -> None:
    payload = _analyze(
        tmp_path,
        "importing.py",
        """\
        import json
        import logging
        import urllib.request

        def fetch(urls):
            return [urllib.request.urlopen(u) for u in urls]

        def render(msg):
            logging.warning(msg)

        def dump(obj):
            return json.dumps(obj)
        """,
    )
    mods = sorted(issue["message"].split("'")[1] for issue in _issues(payload, "heavy-import"))
    assert mods == ["logging", "urllib.request"], "json is cheap and must not be flagged"


def test_heavy_import_not_flagged_when_module_scope_needs_it(tmp_path: Path) -> None:
    """Deferring is unsafe if module level, a class body, or a second function uses it."""
    payload = _analyze(
        tmp_path,
        "shared_import.py",
        """\
        import logging
        import urllib.request

        LOG = logging.getLogger(__name__)

        def fetch(urls):
            return [urllib.request.urlopen(u) for u in urls]

        def head(url):
            return urllib.request.urlopen(url).status
        """,
    )
    assert _issues(payload, "heavy-import") == []


def test_directory_walks_recursively(tmp_path: Path) -> None:
    """The previous version crashed with IsADirectoryError on directory input."""
    sub = tmp_path / "nested"
    sub.mkdir()
    _write(
        sub,
        "a.py",
        """\
        def f():
            out = ""
            for i in range(3):
                out += "y"
        """,
    )
    _write(tmp_path, "b.py", "def g(): pass\n")
    r = _run(str(tmp_path), "--format", "json", "--quiet")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["meta"]["files_analyzed"] == 2
    assert "string-concat-loop" in _categories(payload)


def test_empty_directory_exits_3(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    r = _run(str(empty), "--format", "json", "--quiet")
    assert r.returncode == 3


def test_membership_seq_flagged(tmp_path: Path) -> None:
    payload = _analyze(
        tmp_path,
        "member.py",
        """\
        def f(x):
            for _ in range(10):
                if x in ["a", "b", "c"]:
                    return True
            return False
        """,
    )
    assert "membership-seq" in _categories(payload)


def test_list_concat_loop_flagged(tmp_path: Path) -> None:
    """'result = result + [x]' copies the whole list every iteration — O(n²)."""
    payload = _analyze(
        tmp_path,
        "list_concat.py",
        """\
        def build(items):
            result = []
            for x in items:
                result = result + [x]
            return result
        """,
    )
    assert "list-concat-loop" in _categories(payload)
    assert _lines(payload, "list-concat-loop") == [4]


def test_list_concat_both_directions_flagged(tmp_path: Path) -> None:
    """'[x] + result' is the same quadratic cost, just prepends."""
    payload = _analyze(
        tmp_path,
        "list_concat_rev.py",
        """\
        def build(items):
            result = []
            for x in items:
                result = [x] + result
            return result
        """,
    )
    assert _lines(payload, "list-concat-loop") == [4]


def test_list_iadd_not_flagged(tmp_path: Path) -> None:
    """'+=' on a list dispatches to extend — amortised O(1), not quadratic."""
    payload = _analyze(
        tmp_path,
        "list_iadd.py",
        """\
        def build(items):
            result = []
            for x in items:
                result += [x]
            return result
        """,
    )
    assert "list-concat-loop" not in _categories(payload)


def test_list_append_not_flagged_as_concat(tmp_path: Path) -> None:
    payload = _analyze(
        tmp_path,
        "list_append.py",
        """\
        def build(items):
            result = []
            for x in items:
                result.append(x)
            return result
        """,
    )
    assert "list-concat-loop" not in _categories(payload)


def test_list_remove_in_loop_flagged(tmp_path: Path) -> None:
    payload = _analyze(
        tmp_path,
        "list_remove.py",
        """\
        def clean(items, bad):
            for b in bad:
                items.remove(b)
            return items
        """,
    )
    assert "list-remove-in-loop" in _categories(payload)
    assert _lines(payload, "list-remove-in-loop") == [3]
    issue = _issues(payload, "list-remove-in-loop")[0]
    assert issue["severity"] == "HIGH"


def test_list_remove_outside_loop_not_flagged(tmp_path: Path) -> None:
    payload = _analyze(
        tmp_path,
        "list_remove_ok.py",
        """\
        def clean(items):
            items.remove("x")
            return items
        """,
    )
    assert "list-remove-in-loop" not in _categories(payload)


# --- self-explaining output -------------------------------------------------


def _explain(*args: str) -> dict[str, Any]:
    r = _run("--explain", *args, "--format", "json")
    assert r.returncode == 0, r.stderr
    payload: dict[str, Any] = json.loads(r.stdout)
    return payload


def _catalog() -> set[str]:
    return {check["category"] for check in _explain()["checks"]}


def test_every_emitted_category_is_in_the_catalog() -> None:
    """A finding with no catalog entry would print without its explanation.

    Parsed rather than imported so the test stays black-box, matching the rest
    of the suite: it reads the categories out of the _flag()/Issue() call sites.
    """
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    emitted: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else None
        index = 1 if name == "_flag" else 3 if _is_issue_ctor(node.func) else None
        if index is None or len(node.args) <= index:
            continue
        arg = node.args[index]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            emitted.add(arg.value)
    assert emitted, "found no category literals — the extraction is broken, not the code"
    assert emitted <= _catalog()


def _is_issue_ctor(func: ast.expr) -> bool:
    return isinstance(func, ast.Name) and func.id == "Issue"


def test_findings_carry_their_own_explanation(tmp_path: Path) -> None:
    payload = _analyze(
        tmp_path,
        "q.py",
        """
        def drain(items):
            while items:
                items.pop(0)
        """,
    )
    issue = _issues(payload, "list-as-queue")[0]
    assert "deque" in issue["why"]
    assert "97" in issue["why"]  # the measured figure travels with the finding
    assert issue["fix"]


def test_json_meta_carries_the_severity_policy(tmp_path: Path) -> None:
    payload = _analyze(tmp_path, "ok.py", "x = 1\n")
    assert set(payload["meta"]["severity_policy"]) == {"HIGH", "MEDIUM", "LOW"}


def test_explain_lists_every_check_and_what_is_not_flagged() -> None:
    payload = _explain()
    assert len(payload["checks"]) > 20
    assert {"list-as-queue", "string-concat-loop", "heavy-import"} <= _catalog()
    topics = " ".join(entry["topic"] for entry in payload["not_flagged"])
    assert "groupby" in topics and "tee" in topics
    for check in payload["checks"]:
        assert check["why"] and check["fix"] and check["title"]


def test_explain_one_category() -> None:
    payload = _explain("cmp-to-key")
    assert [c["category"] for c in payload["checks"]] == ["cmp-to-key"]
    assert "not_flagged" not in payload  # a single lookup, not the whole tour


def test_explain_unknown_category_is_a_user_error() -> None:
    r = _run("--explain", "not-a-check")
    assert r.returncode == 1
    assert json.loads(r.stderr)["code"] == "UNKNOWN_CATEGORY"
    assert not r.stdout


def test_text_report_groups_occurrences_under_one_explanation(tmp_path: Path) -> None:
    fixture = _write(
        tmp_path,
        "many.py",
        """
        def drain(a, b):
            while a:
                a.pop(0)
            while b:
                b.pop(0)
        """,
    )
    r = _run(str(fixture), "--quiet")
    assert r.returncode == 0
    assert r.stdout.count("(2 occurrences)") == 1
    assert r.stdout.count("Why") == 1  # explained once, not once per occurrence
    assert "What the severities mean" in r.stdout


def test_clean_report_points_at_profiling(tmp_path: Path) -> None:
    fixture = _write(tmp_path, "fine.py", "x = 1\n")
    r = _run(str(fixture), "--quiet")
    assert r.returncode == 0
    assert "No findings." in r.stdout
    assert "--profile" in r.stdout
