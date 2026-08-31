#!/usr/bin/env python3
"""perf_check.py — Static and runtime Python performance analysis.

Walks Python files (or directories, recursively) and flags patterns whose cost
grows badly with input size: quadratic string/bytes concatenation, lists used
as queues, linear-scan membership tests, work repeated inside a loop that could
be hoisted out of it, and sequences built in full only to be sliced. Also
reports import-time cost, which is paid on every process launch. Optionally
profiles a script at runtime via cProfile.

Every finding carries its own reasoning — what the pattern costs, why it costs
that, and the specific rewrite — so no companion document is needed to read the
output. `--explain` prints the same detail for every check the tool knows,
including the patterns it deliberately stays quiet about.

Usage:
    perf_check.py <path> [path ...]                # static analysis
    perf_check.py --profile <script.py> -- <args>  # runtime profile
    perf_check.py --explain [CATEGORY]             # what the checks mean
    perf_check.py <path> --format json             # machine-readable

Exit codes:
    0   Analysis ran (findings, if any, are in the report — not in this code)
    1   User/invocation error — bad args, paths not found, unknown category
    2   System/infrastructure error — unexpected exception while parsing
    3   Analysis ran; no Python files matched the inputs
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
import contextlib
import cProfile
from dataclasses import asdict, dataclass
import io
import json
from pathlib import Path
import pstats
import sys
import textwrap
from typing import Any

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_SYSTEM_ERROR = 2
EXIT_NOT_FOUND = 3

_C = {
    "HIGH": "\033[91m",
    "MEDIUM": "\033[93m",
    "LOW": "\033[94m",
    "RESET": "\033[0m",
    "BOLD": "\033[1m",
}
_SEV_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

# Fixed rather than terminal-derived: output is read as often from a pipe or a
# transcript as from a live terminal, and stable line breaks diff cleanly.
_WRAP = 88

# The AST nodes a finding can be reported against — those carrying a source line.
_Located = ast.stmt | ast.expr | ast.excepthandler

# Accumulator kinds tracked for the quadratic-concatenation checks.
_STR = "str"
_BYTES = "bytes"
_CONCAT_CATEGORY = {_STR: "string-concat-loop", _BYTES: "bytes-concat-loop"}
_CONCAT_FIX = {
    _STR: "Collect into a list, then ''.join(parts) after the loop (or write into an io.StringIO)",
    _BYTES: "Extend a bytearray in place (buf = bytearray(); buf += chunk), or b''.join(parts)",
}


def _buffer_kind(node: ast.expr) -> str | None:
    """Classify an assignment RHS as an immutable str/bytes accumulator seed.

    Returns None for anything else — notably bytearray() and io.StringIO(), the
    idioms the Python FAQ recommends, which must never be flagged.
    """
    if isinstance(node, ast.JoinedStr):
        return _STR
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            return _STR
        if isinstance(node.value, bytes):
            return _BYTES
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == "str":
            return _STR
        if node.func.id == "bytes":
            return _BYTES
    return None


def _int_index(node: ast.expr) -> int | None:
    """Extract a literal int subscript; negatives parse as UnaryOp(USub, Constant)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and node.value is not True:
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _int_index(node.operand)
        return None if inner is None else -inner
    return None


def _is_head_slice(node: ast.Subscript) -> bool:
    """True for a plain leading slice, x[:n] — no lower bound, no step."""
    s = node.slice
    return isinstance(s, ast.Slice) and s.lower is None and s.step is None and s.upper is not None


def _range_len_offset(expr: ast.expr) -> int | None:
    """For range(len(x)) return 0, for range(len(x) - k) return k, else None."""
    offset = 0
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Sub):
        k = _int_index(expr.right)
        if k is None:
            return None
        offset, expr = k, expr.left
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) and expr.func.id == "len":
        return offset
    return None


def _self_concat_operand(value: ast.expr, name: str) -> ast.expr | None:
    """For 'name + x' / 'x + name', return the other operand; else None."""
    if not isinstance(value, ast.BinOp) or not isinstance(value.op, ast.Add):
        return None
    if isinstance(value.left, ast.Name) and value.left.id == name:
        return value.right
    if isinstance(value.right, ast.Name) and value.right.id == name:
        return value.left
    return None


# Exceptions cheap enough to pre-check for, so catching them per iteration is waste.
_CONTROL_FLOW_EXCS = frozenset({"KeyError", "IndexError", "StopIteration", "AttributeError"})


def _handler_names(handler: ast.ExceptHandler) -> set[str]:
    """Exception names a handler catches; a bare 'except:' or an expression gives none."""
    if isinstance(handler.type, ast.Tuple):
        return {n.id for n in handler.type.elts if isinstance(n, ast.Name)}
    if isinstance(handler.type, ast.Name):
        return {handler.type.id}
    return set()


def _called_name(func: ast.expr) -> str:
    """The bare name of a call target — 'x' for both x(...) and obj.x(...)."""
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _colors() -> dict[str, str]:
    """ANSI codes when stdout is a terminal, empty strings when it is piped."""
    return _C if sys.stdout.isatty() else dict.fromkeys(_C, "")


def _emit_error(error: str, code: str, hint: str = "") -> None:
    """Structured error to stderr; never to stdout."""
    payload: dict[str, str] = {"error": error, "code": code}
    if hint:
        payload["hint"] = hint
    print(json.dumps(payload), file=sys.stderr)


def _log(msg: str, quiet: bool) -> None:
    if not quiet:
        print(msg, file=sys.stderr)


# Every finding carries the standing explanation for its category, so output is
# self-contained: what the pattern costs, why it costs that, and the remedy. The
# measured figures are from CPython 3.11+ microbenchmarks on the shapes below.
@dataclass(frozen=True)
class Check:
    """What a category of finding means, independent of any one occurrence."""

    title: str
    severity: str
    why: str
    fix: str

    @property
    def primary_severity(self) -> str:
        """The worse half of a context-dependent pair — what to sort and colour by."""
        return self.severity.split("/")[0]


_CHECKS: dict[str, Check] = {
    "string-concat-loop": Check(
        "Quadratic string building",
        "HIGH",
        "str is immutable, so every 's += chunk' allocates a new string and copies everything "
        "accumulated so far. Building from n chunks copies O(n²) bytes, which is the difference "
        "between milliseconds and minutes once n reaches five figures. CPython has an in-place "
        "fast path when the accumulator's refcount is exactly 1, but it stops applying the "
        "moment anything else holds a reference, so the quadratic case is the one to design for.",
        "Append the pieces to a list and join once at the end — ''.join(parts) — or write into "
        "an io.StringIO. Both are O(n) in total.",
    ),
    "bytes-concat-loop": Check(
        "Quadratic bytes building",
        "HIGH",
        "The same quadratic copy as string concatenation: bytes is immutable, so each '+=' "
        "reallocates and copies the whole buffer. It shows up most often when assembling a "
        "response body or reading fixed-size chunks off a socket or file.",
        "Use a bytearray, which resizes amortised-O(1): buf = bytearray() then buf += chunk. Or "
        "collect the chunks and b''.join(parts).",
    ),
    "list-concat-loop": Check(
        "Quadratic list building via +",
        "HIGH",
        "'result = result + [item]' creates a brand-new list and copies every element "
        "accumulated so far, plus the new one, on every iteration — the same O(n²) shape as "
        "string concatenation. Unlike '+=' on a list, which dispatches to list.extend() and is "
        "amortised O(1), the plain '+' operator always allocates a fresh list.",
        "Use result.append(item), or result += [item] (which is extend, not concat). If building "
        "from scratch, a list comprehension avoids the question entirely.",
    ),
    "list-as-queue": Check(
        "List used as a queue",
        "HIGH",
        "A list stores its elements contiguously, so removing or inserting at the front moves "
        "every remaining element one slot. Draining an n-element list with pop(0) is therefore "
        "O(n²) — measured 97-99% slower than the deque equivalent. Note that pop() and append() "
        "at the *end* are O(1) and perfectly fine; only the front is expensive.",
        "Use collections.deque, which is O(1) at both ends: popleft() instead of pop(0), "
        "appendleft(x) instead of insert(0, x).",
    ),
    "membership-seq": Check(
        "Linear-scan membership test",
        "HIGH/MEDIUM",
        "'x in [a, b, c]' walks the sequence comparing element by element; a set hashes x once "
        "and looks it up in O(1). The gap widens with both the number of candidates and the "
        "number of checks, so inside a loop this is O(n*m) where O(n) was available. 'not in' "
        "costs the same or more — it has to reach the end of the sequence before it can answer, "
        "so every miss is the worst case. A set literal costs nothing extra to write, which is "
        "why this is HIGH in a loop.",
        "Use a set literal: x in {a, b, c}. If the candidates are computed rather than literal, "
        "build the set once outside the loop (frozenset(...)) instead of rebuilding it per pass.",
    ),
    "pandas-iter": Check(
        "Row-by-row DataFrame iteration",
        "HIGH/MEDIUM",
        "iterrows() constructs a new Series for every row and forces each value through the "
        "Python interpreter, discarding the vectorised C paths that are the reason to use pandas "
        "at all. itertuples() is faster but still per-row Python. On a million-row frame this is "
        "the difference between minutes and a fraction of a second.",
        "Express the operation over whole columns (df['a'] * df['b'], df.loc[mask, 'c'] = ...), "
        "or drop to numpy via df['a'].to_numpy(). Reach for .apply() only when no vectorised "
        "form exists — it is still a Python-level loop, just a tidier one.",
    ),
    "heavy-import": Check(
        "Costly import used by one function",
        "MEDIUM",
        "Import cost is paid at startup on every process launch — irrelevant for a long-running "
        "service, dominant for a CLI or anything invoked in a loop. Against a ~20ms bare "
        "interpreter, logging adds ~30ms and urllib.request ~28ms; pandas ~400ms and torch "
        "~800ms. Flagged only when exactly one function uses the module and nothing at module "
        "scope does, which is precisely when deferring it is both safe and free.",
        "Move the import inside the one function that uses it, so calls that never reach that "
        "function do not pay for it. Keep it at module scope if anything running at import time "
        "— a decorator, a default argument, a class body, an evaluated annotation — needs it.",
    ),
    "import-in-loop": Check(
        "Import inside a loop",
        "MEDIUM",
        "After the first pass the module is cached, so this is not a re-import — but each "
        "iteration still runs the import machinery: a sys.modules lookup, the __import__ call, "
        "and the name binding. In a tight loop that has measured ~40% of total loop time. A lazy "
        "import at the top of a *function* is a different thing and is not flagged: that one "
        "deliberately trades a little per-call cost for faster startup.",
        "Hoist the import to module scope, or to the first line of the enclosing function if you "
        "are deliberately deferring it.",
    ),
    "subprocess-in-loop": Check(
        "Process spawn inside a loop",
        "HIGH",
        "Each spawn costs roughly 20ms of fork/exec, shell startup and pipe setup before the "
        "child does any work at all, and that floor is the same whether the child does something "
        "trivial or something large. When the child is itself a Python interpreter the floor is "
        "far higher — its own startup plus every import it does at module scope, routinely 50ms "
        "and often several hundred. This is a constant factor rather than a growth rate, but it "
        "is the one constant large enough to dominate a loop outright: a thousand items spawning "
        "python each is a minute spent on process management. Moving the spawn into a helper "
        "changes none of it, so a loop calling such a helper is flagged the same way.",
        "Batch the inputs into one invocation where the command accepts many arguments (git add "
        "f1 f2 f3, grep -f patterns). When the child is another Python script, import it and call "
        "its function directly — that removes the interpreter startup entirely. If the work has "
        "to stay in separate processes, start a pool once "
        "(concurrent.futures.ProcessPoolExecutor) rather than a process per item. A harness whose "
        "whole job is driving another program per case will see this finding and cannot act on "
        "it — there the cost is inherent.",
    ),
    "deepcopy-in-loop": Check(
        "deepcopy per iteration",
        "MEDIUM",
        "copy.deepcopy walks the entire object graph, allocates a replacement for every node, "
        "and maintains a memo dict so cycles and shared references survive. Copying just the "
        "handful of fields actually mutated measured ~95% faster.",
        "Copy explicitly what you need — dict(row), list(items), dataclasses.replace(obj, "
        "field=...) — or deepcopy a template once before the loop when every iteration starts "
        "from the same value.",
    ),
    "regex-recompile": Check(
        "Regex compiled from a literal in a loop",
        "MEDIUM",
        "re.match(pattern, s) is not a full recompile every call — re keeps an internal cache of "
        "up to 512 compiled patterns — but each call still hashes the pattern string and does "
        "the cache lookup, and the cache is cleared wholesale when it fills. Binding the "
        "compiled pattern once removes the lookup and any chance of a cache miss on a hot path.",
        "PATTERN = re.compile(r'...') at module scope (or before the loop), then PATTERN.match(s).",
    ),
    "open-in-loop": Check(
        "File opened inside a loop",
        "MEDIUM",
        "Each open() is a syscall plus a fresh buffer allocation, and the matching close flushes "
        "and tears it down. Reading the same config or lookup file once per record instead of "
        "once at startup multiplies that by the record count — and usually re-parses the "
        "contents each time too, which costs more than the open did.",
        "Open and parse once before the loop, then reuse the result. If each iteration genuinely "
        "reads a different file, this finding is expected and the cost is inherent.",
    ),
    "list-remove-in-loop": Check(
        "Linear removal inside a loop",
        "HIGH",
        "list.remove(x) scans from the left until it finds x, then shifts every element after "
        "it down one slot — O(n) per call. Inside a loop over the same or a related list that "
        "is O(n²), the same cost shape as pop(0). Filtering a list by removing unwanted items "
        "one at a time is the most common trigger.",
        "Build a new list with a comprehension: kept = [x for x in items if x not in unwanted]. "
        "If the removals are by value from a set of targets, 'items = [x for x in items if x "
        "not in discard_set]' does it in one O(n) pass.",
    ),
    "sort-in-loop": Check(
        "Sorting inside a loop",
        "MEDIUM",
        "A sort is O(n log n); running it once per iteration makes the surrounding loop "
        "O(n^2 log n). Almost always the result only needs to be ordered once, after the "
        "collecting is finished.",
        "Sort once after the loop. If the order has to hold at every step, bisect.insort() "
        "maintains it per insert, or keep a heapq when you only ever need the smallest element.",
    ),
    "cmp-to-key": Check(
        "cmp_to_key comparator",
        "MEDIUM",
        "functools.cmp_to_key wraps each element in an object whose __lt__ calls back into your "
        "Python comparison function, so the interpreter round-trips O(n log n) times instead of "
        "computing one key per element. Measured roughly 15x slower than the equivalent key=.",
        "Pass a key directly: key=operator.itemgetter(1), or key=lambda r: (r.dept, -r.score). "
        "Express a reversed ordering with reverse=True or by negating the key, not by comparing.",
    ),
    "materialize-then-slice": Check(
        "Whole sequence built, then sliced",
        "MEDIUM",
        "list(rows)[:10] consumes the entire source — every row read, parsed and stored — before "
        "discarding all but ten, and holds the whole thing in memory on the way. On a "
        "200k-item generator that measured ~1.3s against effectively zero for the lazy form. "
        "Anything that pages or previews results runs into this constantly.",
        "itertools.islice(iterable, n) stops pulling after n items. For a file, iterate the "
        "handle directly rather than calling .readlines() first.",
    ),
    "sort-then-slice": Check(
        "Full sort to answer a top-n question",
        "MEDIUM",
        "sorted(rows)[:n] orders every item to keep a few. heapq.nsmallest/nlargest keep only an "
        "n-element heap and measured ~90% faster on large shuffled inputs. Taking a single "
        "element — sorted(x)[0] or [-1] — is an O(n log n) way of asking an O(n) question.",
        "heapq.nsmallest(n, seq, key=...) or nlargest for a slice; min(seq, key=...) or max for "
        "one element. Below roughly n=10 out of a few hundred the difference stops mattering.",
    ),
    "range-len": Check(
        "Index-based iteration",
        "MEDIUM/LOW",
        "'for i in range(len(seq))' then seq[i] pays a subscript — bounds check and index "
        "arithmetic — per access, where direct iteration pays none. The range(len(seq) - 1) "
        "variant reading seq[i] and seq[i+1] is a sliding window: itertools.pairwise measured "
        "~60% faster and states the intent, which is why that form is MEDIUM and the plain one "
        "is LOW.",
        "'for item in seq:', or 'for i, item in enumerate(seq):' when the index is also needed. "
        "For adjacent pairs, 'for a, b in itertools.pairwise(seq):'.",
    ),
    "except-as-control-flow": Check(
        "Exception used as a loop condition",
        "MEDIUM",
        "Since 3.11 an untaken try block is free, so the whole cost sits in the raising: "
        "building the exception, capturing a traceback, unwinding — roughly a microsecond each "
        "time. That is cheap when the miss is rare and expensive when it is the common case, "
        "and catching KeyError or IndexError per iteration usually means it is the common case.",
        "Pre-check when misses are expected: 'if key in d', d.get(key, default), "
        "'if i < len(seq)'. Keep try/except where the failure really is exceptional — there it "
        "beats a check that almost always passes.",
    ),
    "manual-flatten": Check(
        "Hand-rolled flatten",
        "LOW",
        "A nested loop whose only body is out.append(x) re-enters the interpreter for every "
        "item; itertools.chain.from_iterable does the same walk in C and measured ~40% faster. "
        "Mostly a readability win with a modest speed bonus attached.",
        "out = list(itertools.chain.from_iterable(nested)).",
    ),
    "dict-init-idiom": Check(
        "Hand-rolled default or tally",
        "LOW",
        "d.setdefault(k, []) constructs the empty list on every call and throws it away whenever "
        "the key already exists — about 2x the cost of a defaultdict(list). "
        "'d[k] = d.get(k, 0) + 1' is Counter written by hand, and Counter(iterable) tallies in C "
        "at roughly 3x the speed. Neither is dramatic; both read better as the standard idiom.",
        "collections.defaultdict(list) indexed directly, or collections.Counter(items) for a "
        "tally.",
    ),
    "repeated-subscript": Check(
        "Same lookup repeated per iteration",
        "LOW",
        "Each row['name'] hashes the key and does a dict lookup, so three accesses in one loop "
        "body do that work three times per iteration. Binding a local once is faster — reading a "
        "local is an array index, not a hash — and usually clearer. A small constant factor: "
        "worth it in a hot loop, noise anywhere else.",
        "Bind at the top of the loop body: name = row['name']. Or unpack several at once from a "
        "tuple or dataclass.",
    ),
    "append-in-loop": Check(
        "Loop that is a comprehension written long-hand",
        "LOW",
        "Readability, not speed. On CPython 3.11+ the specialising interpreter closed the gap: a "
        "list comprehension measures no faster than the equivalent .append() loop, and sometimes "
        "marginally slower. This fires only when the loop body is exactly one .append(), i.e. "
        "when the rewrite is mechanical — a loop that also filters or transforms is left alone.",
        "result = [expr for item in seq] if it reads better. Leave it if it does not; there is "
        "no throughput to win here.",
    ),
    "logging-fstring": Check(
        "Eagerly formatted log message",
        "LOW",
        "An f-string is evaluated before the call, so the formatting happens even when the level "
        "suppresses the record — including any __str__ or __repr__ of the interpolated objects, "
        "which can be arbitrarily expensive. %-style arguments are only rendered if the record "
        "is actually emitted, and they keep identical messages groupable by log aggregators.",
        "Pass the values as arguments: logger.info('processed %s in %.2fs', name, elapsed). Guard "
        "a genuinely expensive computation with 'if logger.isEnabledFor(logging.DEBUG):'.",
    ),
    "globals-in-loop": Check(
        "Namespace dict rebuilt in a loop",
        "LOW",
        "Inside a function, locals() materialises a fresh snapshot dict of every local on each "
        "call (explicitly so since Python 3.13). globals() returns the real module dict without "
        "copying and is cheap — but calling either per iteration to look a name up signals that "
        "the lookup wants to be a direct reference instead.",
        "Hoist it (ns = globals()) if the dynamic lookup is genuinely needed. Better, pass the "
        "object in directly or dispatch through a dict built once.",
    ),
    "dict-keys-membership": Check(
        "Membership test through .keys()",
        "LOW",
        "'k in d' and 'k in d.keys()' are both O(1); the .keys() version merely allocates a view "
        "object and does an extra attribute lookup first. The cost is trivial — it is flagged "
        "because it usually signals the author expected a linear scan, which is worth correcting "
        "for whoever reads it next.",
        "if k in d:",
    ),
}


# Patterns this tool stays quiet about on purpose.
_NOT_FLAGGED: list[tuple[str, str]] = [
    (
        "Caching method lookups (append = out.append)",
        "Real advice on older interpreters. On CPython 3.11+ the specialising interpreter caches "
        "the attribute lookup at the call site, so hoisting the bound method now usually costs "
        "more than it saves — an extra local, a worse read, and no measurable win.",
    ),
    (
        "itertools.groupby",
        "It groups only *runs* of adjacent equal keys, so offering it as a drop-in for a "
        "grouping loop introduces a correctness bug unless the input is already sorted by that "
        "key. A defaultdict(list) is safer and, once the sort it would need is counted, faster.",
    ),
    (
        "itertools.tee",
        "It buffers everything consumed between its fastest and slowest iterator, so it "
        "routinely trades a modest time win for a much worse memory profile. Materialising a "
        "list is usually the honest version of the same trade.",
    ),
    (
        "Micro-optimisations in general",
        "No findings for local-variable tricks, while-versus-for, or operator choice. They are "
        "noise next to the complexity and constant-factor issues above, and once those are gone "
        "a profiler is the right instrument — guessing at the interpreter is not.",
    ),
]


_SEVERITY_POLICY: dict[str, str] = {
    "HIGH": "The cost grows faster than the input — an O(n²) shape where O(n) was available — or, "
    "for a process spawned per item, a constant so large it dominates the loop anyway. It may "
    "look fine on today's data and fall over on next year's. Fix it.",
    "MEDIUM": "A large constant factor, paid repeatedly. Fix unless there is a reason not to, "
    "and leave the reason in a comment where you skip it.",
    "LOW": "Idiom and readability, with little or no measurable win. Worth a glance, not worth "
    "an argument.",
}


@dataclass
class Issue:
    file: str
    line: int
    severity: str
    category: str
    message: str
    fix: str
    why: str = ""

    def __post_init__(self) -> None:
        """Attach the category's standing explanation, so a finding travels self-contained."""
        self.why = _CHECKS[self.category].why


class _SubscriptCounter(ast.NodeVisitor):
    """Collects constant-key subscript accesses in a subtree, grouped by (name, key)."""

    def __init__(self) -> None:
        self.accesses: defaultdict[tuple[str, object], list[ast.Subscript]] = defaultdict(list)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if isinstance(node.value, ast.Name) and isinstance(node.slice, ast.Constant):
            self.accesses[node.value.id, node.slice.value].append(node)
        self.generic_visit(node)


# Calls that start an OS process, by the module they live in.
_SPAWN_CALLS = {
    "subprocess": frozenset(
        {
            "run",
            "Popen",
            "call",
            "check_call",
            "check_output",
            "getoutput",
            "getstatusoutput",
        }
    ),
    "os": frozenset({"system", "popen"}),
}


def _spawn_bindings(tree: ast.Module) -> tuple[dict[str, str], dict[str, str]]:
    """Names bound by imports that lead to a process spawn.

    Returns (modules, direct). modules maps a bound name to the module it stands
    for, so 'import subprocess as sp' registers sp; direct maps a bare name to its
    label, so 'from subprocess import run' registers run. modules is seeded with
    the real module names, which keeps a spawn flagged even when the import itself
    is somewhere this pass cannot see it.
    """
    modules = {name: name for name in _SPAWN_CALLS}
    direct: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _SPAWN_CALLS and alias.asname:
                    modules[alias.asname] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module in _SPAWN_CALLS:
            for alias in node.names:
                if alias.name in _SPAWN_CALLS[node.module]:
                    direct[alias.asname or alias.name] = f"{node.module}.{alias.name}()"
    return modules, direct


def _spawn_label(func: ast.expr, modules: dict[str, str], direct: dict[str, str]) -> str | None:
    """The 'subprocess.run()' label for a call that starts a process, else None."""
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        module = modules.get(func.value.id)
        if module and func.attr in _SPAWN_CALLS[module]:
            return f"{module}.{func.attr}()"
    elif isinstance(func, ast.Name):
        return direct.get(func.id)
    return None


def _spawning_functions(
    tree: ast.Module, modules: dict[str, str], direct: dict[str, str]
) -> dict[str, str]:
    """Functions that reach a spawn, as function name -> the spawn call it reaches.

    A spawn factored out into a helper costs exactly what it cost inline, so a loop
    calling that helper per item is the same finding — and that is the shape the
    per-item work usually ends up in. Chains are followed to a fixpoint, and
    functions are keyed by bare name so methods are covered too.
    """
    spawning: dict[str, str] = {}
    calls: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        called: set[str] = set()
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            label = _spawn_label(inner.func, modules, direct)
            if label:
                spawning.setdefault(node.name, label)
            else:
                called.add(_called_name(inner.func))
        calls[node.name] = called

    changed = True
    while changed:
        changed = False
        for name, called in calls.items():
            if name in spawning:
                continue
            # sorted() so a function reaching two different spawns names the same one on every run.
            # set order would make the report unstable.
            reached = next((spawning[c] for c in sorted(called) if c in spawning), None)
            if reached is not None:
                spawning[name] = reached
                changed = True
    return spawning


class PerfVisitor(ast.NodeVisitor):
    def __init__(self, filename: str, tree: ast.Module):
        self.filename = filename
        self.issues: list[Issue] = []
        self._depth = 0
        self._buffers: dict[str, str] = {}
        self._flattened: set[ast.For] = set()
        # Spawns are resolved up front: a helper may be defined after the loop that calls it, so the
        # walk cannot answer "does this spawn?" on its own.
        self._spawn_modules, self._spawn_direct = _spawn_bindings(tree)
        self._spawning_funcs = _spawning_functions(tree, self._spawn_modules, self._spawn_direct)

    def _flag(self, node: _Located, cat: str, msg: str, fix: str, sev: str = "") -> None:
        """Record a finding, taking its severity from the check table.

        Only a category whose declared severity is a pair — 'HIGH/MEDIUM' — needs
        sev, and its call site decides which half applies from the context.
        """
        severity = sev or _CHECKS[cat].severity
        self.issues.append(Issue(self.filename, node.lineno, severity, cat, msg, fix))

    def _enter(self, node: ast.AST) -> None:
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    def _visit_scope(self, node: ast.AST) -> None:
        """Visit a function body with a fresh accumulator map, then restore."""
        outer = self._buffers
        self._buffers = {}
        self.generic_visit(node)
        self._buffers = outer

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_scope(node)

    def _check_repeated_subscript(self, node: ast.For | ast.While) -> None:
        """Flag the same constant-key lookup done three or more times per iteration."""
        counter = _SubscriptCounter()
        for stmt in node.body:
            counter.visit(stmt)
        for (obj, key), accesses in counter.accesses.items():
            if len(accesses) >= 3:
                self._flag(
                    accesses[0],
                    "repeated-subscript",
                    f"'{obj}[{key!r}]' accessed {len(accesses)}x per loop iteration",
                    "Cache in a local variable at the top of the loop body",
                )

    def visit_For(self, node: ast.For) -> None:
        self._check_range_len(node)
        self._check_manual_flatten(node)
        self._check_lone_append(node)
        for name in ast.walk(node.target):
            if isinstance(name, ast.Name):
                self._buffers.pop(name.id, None)  # the loop variable rebinds it
        self._check_repeated_subscript(node)
        self._enter(node)

    def _check_range_len(self, node: ast.For) -> None:
        """Flag 'for i in range(len(seq))' — direct iteration or pairwise says it better."""
        it = node.iter
        if not (
            isinstance(it, ast.Call)
            and isinstance(it.func, ast.Name)
            and it.func.id == "range"
            and it.args
        ):
            return
        offset = _range_len_offset(it.args[-1])
        if offset == 1:
            self._flag(
                node,
                "range-len",
                "for i in range(len(seq) - 1) — a sliding window over adjacent pairs",
                "Use itertools.pairwise(seq): 'for a, b in pairwise(seq)' — ~60% faster",
                sev="MEDIUM",
            )
        elif offset is not None:
            self._flag(
                node,
                "range-len",
                "for i in range(len(seq)) — index-based iteration over a sequence",
                "Use 'for item in seq:' or 'for i, item in enumerate(seq):'",
                sev="LOW",
            )

    def _lone_append(self, node: ast.For) -> ast.Call | None:
        """Return the append() call if the loop body is exactly one .append(...) on a name."""
        if len(node.body) != 1 or node.orelse or not isinstance(node.body[0], ast.Expr):
            return None
        call = node.body[0].value
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "append"
            and isinstance(call.func.value, ast.Name)
            and len(call.args) == 1
            and not call.keywords
        ):
            return call
        return None

    def _check_lone_append(self, node: ast.For) -> None:
        """A loop whose whole body is one append converts mechanically to a comprehension."""
        if node in self._flattened or self._lone_append(node) is None:
            return
        self._flag(
            node,
            "append-in-loop",
            "loop body is a single .append() — this is a list comprehension written long-hand",
            "Readability only, not speed: result = [expr for item in seq]",
        )

    def _check_manual_flatten(self, node: ast.For) -> None:
        """Flag 'for sub in nested: for x in sub: out.append(x)' — a hand-rolled flatten."""
        if len(node.body) != 1 or not isinstance(node.body[0], ast.For):
            return
        inner = node.body[0]
        call = self._lone_append(inner)
        if call is None:
            return
        # The inner loop must walk the outer variable and append only its own variable.
        if not (
            isinstance(node.target, ast.Name)
            and isinstance(inner.iter, ast.Name)
            and inner.iter.id == node.target.id
            and isinstance(inner.target, ast.Name)
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id == inner.target.id
        ):
            return
        self._flag(
            node,
            "manual-flatten",
            "nested loop whose only work is appending inner items — a hand-rolled flatten",
            "Use itertools.chain.from_iterable(nested) — ~40% faster and one line",
        )
        self._flattened.add(inner)  # so visiting it does not also report its inner append

    def visit_Subscript(self, node: ast.Subscript) -> None:
        self._check_sort_then_slice(node)
        self._check_materialize_then_slice(node)
        self.generic_visit(node)

    def _check_sort_then_slice(self, node: ast.Subscript) -> None:
        call = node.value
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "sorted"
        ):
            return
        reverse = any(
            kw.arg == "reverse"
            and not (isinstance(kw.value, ast.Constant) and kw.value.value is False)
            for kw in call.keywords
        )
        if _is_head_slice(node):
            picker = "nlargest" if reverse else "nsmallest"
            self._flag(
                node,
                "sort-then-slice",
                "sorted(...)[:n] — sorts the whole sequence just to keep n items",
                f"Use heapq.{picker}(n, seq, key=...) — ~90% faster on large inputs",
            )
            return
        idx = _int_index(node.slice)
        if idx in {0, -1}:
            want = "min" if (idx == 0) != reverse else "max"
            self._flag(
                node,
                "sort-then-slice",
                f"sorted(...)[{idx}] — a full O(n log n) sort to take one element",
                f"Use {want}(seq, key=...) — a single O(n) pass",
            )

    def _check_materialize_then_slice(self, node: ast.Subscript) -> None:
        call = node.value
        if not (_is_head_slice(node) and isinstance(call, ast.Call)):
            return
        if isinstance(call.func, ast.Name) and call.func.id in {"list", "tuple"}:
            what = f"{call.func.id}(...)[:n]"
        elif isinstance(call.func, ast.Attribute) and call.func.attr == "readlines":
            what = ".readlines()[:n]"
        else:
            return
        self._flag(
            node,
            "materialize-then-slice",
            f"{what} — builds the whole sequence in memory, then throws all but n away",
            "Use itertools.islice(iterable, n) to stop consuming after n items",
        )

    def visit_While(self, node: ast.While) -> None:
        self._check_repeated_subscript(node)
        self._enter(node)

    # A comprehension is a loop: whatever its body does is done once per item.
    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._enter(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._enter(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._enter(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._enter(node)

    def visit_Try(self, node: ast.Try) -> None:
        if self._depth > 0:
            for handler in node.handlers:
                matched = _CONTROL_FLOW_EXCS & _handler_names(handler)
                if matched:
                    exc_names = ", ".join(sorted(matched))
                    self._flag(
                        handler,
                        "except-as-control-flow",
                        f"Catching {exc_names} inside a loop — exception overhead per miss",
                        "Use 'if key in dict' / 'if i < len(seq)' checks before access",
                    )
        self.generic_visit(node)

    def _flag_concat(self, node: _Located, kind: str, what: str) -> None:
        self._flag(
            node,
            _CONCAT_CATEGORY[kind],
            f"{what} inside a loop — {kind} is immutable, so this is O(n²)",
            _CONCAT_FIX[kind],
        )

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if self._depth > 0 and isinstance(node.op, ast.Add):
            target = node.target
            tracked = self._buffers.get(target.id) if isinstance(target, ast.Name) else None
            kind = _buffer_kind(node.value) or tracked
            if kind:
                if isinstance(node.value, ast.JoinedStr):
                    what = "f-string +="
                else:
                    what = "String +=" if kind == _STR else "bytes +="
                self._flag_concat(node, kind, what)
        self.generic_visit(node)

    def _check_manual_counter(self, node: ast.Assign) -> None:
        """Flag 'counts[k] = counts.get(k, 0) + 1' — a hand-rolled Counter."""
        target = node.targets[0] if len(node.targets) == 1 else None
        if not (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)):
            return
        value = node.value
        if not (isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add)):
            return
        for side in (value.left, value.right):
            if (
                isinstance(side, ast.Call)
                and isinstance(side.func, ast.Attribute)
                and side.func.attr == "get"
                and isinstance(side.func.value, ast.Name)
                and side.func.value.id == target.value.id
                and len(side.args) == 2
            ):
                name = target.value.id
                self._flag(
                    node,
                    "dict-init-idiom",
                    f"'{name}[k] = {name}.get(k, ...) + ...' — a hand-rolled tally",
                    "Use collections.Counter(items), or defaultdict(int) with counts[k] += 1",
                )
                return

    def _check_self_concat(self, node: ast.Assign, name: str, other: ast.expr) -> None:
        """Flag 'x = x + ...' in a loop — quadratic for str and bytes, and for list too."""
        kind = self._buffers.get(name) or _buffer_kind(other)
        if kind:
            self._flag_concat(node, kind, f"'{name} = {name} + ...'")
        elif isinstance(other, ast.List):
            self._flag(
                node,
                "list-concat-loop",
                f"'{name} = {name} + [...]' — creates a new list every iteration",
                "Use .append() or += (which calls extend) instead of +",
            )

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._depth > 0:
            self._check_manual_counter(node)
        seed = _buffer_kind(node.value)
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            other = _self_concat_operand(node.value, target.id)
            if other is not None:
                # A self-concat neither seeds nor clears the accumulator: 'x = x + y'
                # leaves x whatever kind it already was.
                if self._depth > 0:
                    self._check_self_concat(node, target.id, other)
            elif seed:
                self._buffers[target.id] = seed
            else:
                self._buffers.pop(target.id, None)  # rebound to something else
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        for i, op in enumerate(node.ops):
            # `not in` pays the same scan as `in`: it walks to the end before it can
            # answer, so a miss is the worst case rather than the cheap one.
            if not isinstance(op, ast.In | ast.NotIn):
                continue
            operator = "not in" if isinstance(op, ast.NotIn) else "in"
            comp = node.comparators[i]
            if isinstance(comp, ast.List | ast.Tuple) and len(comp.elts) > 1:
                kind = "list" if isinstance(comp, ast.List) else "tuple"
                self._flag(
                    node,
                    "membership-seq",
                    f"'{operator} {kind}' literal — O(n) scan each time",
                    "Use a set literal {a, b, ...} for O(1) membership tests",
                    sev="HIGH" if self._depth > 0 else "MEDIUM",
                )
            elif (
                isinstance(comp, ast.Call)
                and isinstance(comp.func, ast.Attribute)
                and comp.func.attr == "keys"
                and not comp.args
            ):
                self._flag(
                    node,
                    "dict-keys-membership",
                    f"'{operator} dict.keys()' — .keys() is redundant for membership tests",
                    "Use 'in dict' directly",
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        f = node.func
        self._check_logging_fstring(node, f)
        self._check_pandas_iter(node, f)
        self._check_cmp_to_key(node, f)
        if self._depth > 0:
            self._check_regex_recompile(node, f)
            self._check_open_in_loop(node, f)
            self._check_globals_in_loop(node, f)
            self._check_sort_in_loop(node, f)
            self._check_setdefault_mutable(node, f)
            self._check_list_as_queue(node, f)
            self._check_list_remove_in_loop(node, f)
            self._check_deepcopy_in_loop(node, f)
            self._check_subprocess_in_loop(node, f)
        self.generic_visit(node)

    def _flag_list_as_queue(self, node: _Located, op: str, repl: str) -> None:
        self._flag(
            node,
            "list-as-queue",
            f"{op} in a loop — every element shifts up, making the loop O(n²)",
            f"Use collections.deque and {repl} — O(1) at both ends",
        )

    def _check_list_as_queue(self, node: ast.Call, f: ast.expr) -> None:
        if not (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)):
            return
        if f.attr == "pop" and len(node.args) == 1 and _int_index(node.args[0]) == 0:
            self._flag_list_as_queue(node, f"{f.value.id}.pop(0)", "popleft()")
        elif f.attr == "insert" and node.args and _int_index(node.args[0]) == 0:
            self._flag_list_as_queue(node, f"{f.value.id}.insert(0, ...)", "appendleft(...)")

    def visit_Delete(self, node: ast.Delete) -> None:
        if self._depth > 0:
            for t in node.targets:
                if (
                    isinstance(t, ast.Subscript)
                    and isinstance(t.value, ast.Name)
                    and _int_index(t.slice) == 0
                ):
                    self._flag_list_as_queue(node, f"del {t.value.id}[0]", "popleft()")
        self.generic_visit(node)

    def _check_list_remove_in_loop(self, node: ast.Call, f: ast.expr) -> None:
        if (
            isinstance(f, ast.Attribute)
            and f.attr == "remove"
            and isinstance(f.value, ast.Name)
            and len(node.args) == 1
            and not node.keywords
        ):
            self._flag(
                node,
                "list-remove-in-loop",
                f"{f.value.id}.remove() in a loop — O(n) scan + shift per call, O(n²) total",
                "Build a new list with a comprehension, or collect indices and remove in bulk",
            )

    def _check_deepcopy_in_loop(self, node: ast.Call, f: ast.expr) -> None:
        if _called_name(f) == "deepcopy":
            self._flag(
                node,
                "deepcopy-in-loop",
                "deepcopy() per iteration — it rewalks the whole object graph every call",
                "Copy the parts you need explicitly, or deepcopy once before the loop",
            )

    _SPAWN_FIX = "Batch the inputs into one invocation, or import the child and call it in-process"

    def _check_subprocess_in_loop(self, node: ast.Call, f: ast.expr) -> None:
        what = _spawn_label(f, self._spawn_modules, self._spawn_direct)
        if what is not None:
            self._flag(
                node,
                "subprocess-in-loop",
                f"{what} in a loop — each spawn costs ~20ms of fork/exec before any work happens",
                self._SPAWN_FIX,
            )
            return
        called = _called_name(f)
        reached = self._spawning_funcs.get(called)
        if reached is not None:
            self._flag(
                node,
                "subprocess-in-loop",
                f"{called}() reaches {reached} — one process spawned per iteration",
                self._SPAWN_FIX,
            )

    def visit_Import(self, node: ast.Import) -> None:
        self._check_import_in_loop(node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self._check_import_in_loop(node)
        self.generic_visit(node)

    def _check_import_in_loop(self, node: ast.Import | ast.ImportFrom) -> None:
        if self._depth > 0:
            self._flag(
                node,
                "import-in-loop",
                "import inside a loop — repeats the sys.modules lookup every iteration",
                "Hoist to module scope, or to the top of the function for a deliberate lazy import",
            )

    def _check_cmp_to_key(self, node: ast.Call, f: ast.expr) -> None:
        if _called_name(f) == "cmp_to_key":
            self._flag(
                node,
                "cmp-to-key",
                "cmp_to_key() — the wrapper is invoked once per comparison, O(n log n) times",
                "Pass a key function directly: key=operator.itemgetter(0) or key=lambda r: r.field",
            )

    def _check_setdefault_mutable(self, node: ast.Call, f: ast.expr) -> None:
        if not (isinstance(f, ast.Attribute) and f.attr == "setdefault" and len(node.args) == 2):
            return
        default = node.args[1]
        is_container = isinstance(default, ast.List | ast.Dict | ast.Set) or (
            isinstance(default, ast.Call)
            and isinstance(default.func, ast.Name)
            and default.func.id in {"list", "dict", "set"}
        )
        if is_container:
            self._flag(
                node,
                "dict-init-idiom",
                "setdefault() with a container default — the default is built on every call",
                "Use collections.defaultdict(list) and index directly: groups[key].append(v)",
            )

    def _check_regex_recompile(self, node: ast.Call, f: ast.expr) -> None:
        re_ops = {"match", "search", "findall", "finditer", "sub", "subn", "split", "fullmatch"}
        if (
            isinstance(f, ast.Attribute)
            and isinstance(f.value, ast.Name)
            and f.value.id == "re"
            and f.attr in re_ops
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            self._flag(
                node,
                "regex-recompile",
                f"re.{f.attr}(string_pattern) in loop — pattern recompiled each call",
                "Call re.compile(r'...') once before the loop",
            )

    def _check_open_in_loop(self, node: ast.Call, f: ast.expr) -> None:
        if isinstance(f, ast.Name) and f.id == "open":
            self._flag(
                node,
                "open-in-loop",
                "open() called inside a loop",
                "Open the file once before the loop",
            )

    def _check_globals_in_loop(self, node: ast.Call, f: ast.expr) -> None:
        if isinstance(f, ast.Name) and f.id in {"globals", "locals"}:
            self._flag(
                node,
                "globals-in-loop",
                f"{f.id}() inside a loop — rebuilds a dict of all variables each call",
                f"Cache before the loop: ns = {f.id}()",
            )

    def _check_sort_in_loop(self, node: ast.Call, f: ast.expr) -> None:
        if isinstance(f, ast.Attribute) and f.attr in {"sort", "reverse"}:
            self._flag(
                node,
                "sort-in-loop",
                f".{f.attr}() called inside a loop — O(n log n) work every iteration",
                "Sort once after the loop, or use bisect.insort() to maintain order incrementally",
            )

    def _check_logging_fstring(self, node: ast.Call, f: ast.expr) -> None:
        log_methods = {"debug", "info", "warning", "error", "critical", "exception"}
        if (
            isinstance(f, ast.Attribute)
            and f.attr in log_methods
            and node.args
            and isinstance(node.args[0], ast.JoinedStr)
        ):
            self._flag(
                node,
                "logging-fstring",
                f"f-string passed to .{f.attr}() — formatted even when log level suppresses output",
                f"Use lazy args: logger.{f.attr}('%s', val) or guard with isEnabledFor()",
            )

    def _check_pandas_iter(self, node: ast.Call, f: ast.expr) -> None:
        if isinstance(f, ast.Attribute) and f.attr in {"iterrows", "itertuples"}:
            self._flag(
                node,
                "pandas-iter",
                f".{f.attr}() — row-by-row Python iteration over a DataFrame is slow",
                "Use vectorized operations, df.apply(), or convert to numpy arrays",
                sev="HIGH" if self._depth > 0 else "MEDIUM",
            )


# Approximate cold-import cost in milliseconds, against a ~20ms interpreter baseline.
# Only modules worth deferring are listed; cheap ones (pathlib, dataclasses, json) are omitted
# deliberately as deferring them isn't a real saving.
_HEAVY_IMPORTS = {
    "logging": 30,
    "urllib.request": 28,
    "http.client": 20,
    "xmlrpc": 30,
    "yaml": 40,
    "PIL": 60,
    "requests": 80,
    "cryptography": 90,
    "numpy": 150,
    "sqlalchemy": 150,
    "scipy": 250,
    "matplotlib": 300,
    "boto3": 300,
    "django": 300,
    "pandas": 400,
    "sklearn": 400,
    "torch": 800,
    "transformers": 900,
}


def _import_cost(module: str) -> int | None:
    """Cost for a module or the heaviest package it lives under."""
    parts = module.split(".")
    for i in range(len(parts), 0, -1):
        cost = _HEAVY_IMPORTS.get(".".join(parts[:i]))
        if cost is not None:
            return cost
    return None


def _module_bindings(stmt: ast.stmt) -> list[tuple[str, str]]:
    """Names bound by a top-level import, as (bound_name, module)."""
    if isinstance(stmt, ast.Import):
        return [(a.asname or a.name.split(".")[0], a.name) for a in stmt.names]
    if isinstance(stmt, ast.ImportFrom) and stmt.module and not stmt.level:
        return [(a.asname or a.name, stmt.module) for a in stmt.names]
    return []


def check_heavy_imports(tree: ast.Module, filename: str) -> list[Issue]:
    """Flag an expensive module-scope import whose only consumer is one function.

    Module-scope imports run on every process launch, so an import used by a single (possibly rarely
    reached) function is pure overhead on every call that does not reach it. Deferring is only safe
    when nothing at module level — including class bodies and annotations, which run at import —
    needs it.
    """
    funcs: dict[str, set[str]] = {}
    module_names: set[str] = set()
    for stmt in tree.body:
        names = {n.id for n in ast.walk(stmt) if isinstance(n, ast.Name)}
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
            funcs[stmt.name] = names
        else:
            module_names |= names

    issues: list[Issue] = []
    for stmt in tree.body:
        for bound, module in _module_bindings(stmt):
            cost = _import_cost(module)
            if cost is None or bound in module_names:
                continue
            users = [fn for fn, used in funcs.items() if bound in used]
            if len(users) == 1:
                issues.append(
                    Issue(
                        filename,
                        stmt.lineno,
                        "MEDIUM",
                        "heavy-import",
                        f"'{module}' costs ~{cost}ms to import, but only {users[0]}() uses it",
                        f"Import it inside {users[0]}() so calls that never reach it don't pay",
                    )
                )
    return issues


def analyze(path: Path) -> list[Issue]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as e:
        raise SyntaxError(f"syntax error in {path}: {e}") from e
    v = PerfVisitor(str(path), tree)
    v.visit(tree)
    return v.issues + check_heavy_imports(tree, str(path))


def _analyze_all(files: list[Path]) -> list[Issue]:
    issues: list[Issue] = []
    for path in files:
        issues.extend(analyze(path))
    return issues


def _profile_target(raw: str) -> Path | None:
    """Resolve --profile's script path, reporting the error if it doesn't exist."""
    script = Path(raw)
    if script.exists():
        return script
    _emit_error(f"Profile target not found: {raw}", "PROFILE_TARGET_NOT_FOUND")
    return None


def _resolve_inputs(paths: list[str]) -> tuple[list[Path], list[str]]:
    """Expand paths into a flat list of .py files. Directories are walked recursively.

    Returns (files, missing) — missing is a list of paths that didn't exist.
    """
    files: list[Path] = []
    missing: list[str] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if not p.exists():
            missing.append(raw)
            continue
        if p.is_dir():
            files.extend(sorted(p.rglob("*.py")))
        else:
            files.append(p)  # any explicit file is analyzed; a SyntaxError bubbles up
    return files, missing


def run_profile(
    script: Path, script_args: list[str], *, divert_stdout: bool = False
) -> cProfile.Profile:
    """Execute a script under cProfile, as if it had been run directly.

    `divert_stdout` sends the target's own output to stderr, for callers that own stdout for a
    machine-readable report — otherwise the two interleave there and the report no longer parses.
    """
    pr = cProfile.Profile()
    old_argv = sys.argv[:]
    sys.argv = [str(script), *script_args]
    script_dir = str(script.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    redirect: contextlib.AbstractContextManager[Any] = (
        contextlib.redirect_stdout(sys.stderr) if divert_stdout else contextlib.nullcontext()
    )
    try:
        code = compile(script.read_text(encoding="utf-8"), str(script), "exec")
        with redirect:
            pr.enable()
            exec(code, {"__name__": "__main__", "__file__": str(script)})
    except SystemExit:
        pass
    except Exception as e:
        print(f"  script raised {type(e).__name__}: {e}", file=sys.stderr)
    finally:
        pr.disable()
        sys.argv = old_argv
    return pr


def print_profile(pr: cProfile.Profile, script: Path, top: int) -> None:
    """Render pstats output, highlighting frames from the profiled script itself."""
    buf = io.StringIO()
    pstats.Stats(pr, stream=buf).sort_stats("cumulative").print_stats(top)
    lines = buf.getvalue().splitlines()

    c = _colors()
    print(f"\n{c['BOLD']}Runtime Profile — top {top} by cumulative time{c['RESET']}")
    print("─" * _WRAP)
    in_table = False
    for line in lines:
        if "ncalls" in line and "tottime" in line:
            in_table = True
            print(f"  {c['BOLD']}{line.strip()}{c['RESET']}")
        elif in_table and line.strip():
            hi = script.name in line or "__main__" in line
            print(f"  {c['HIGH'] if hi else ''}{line}{c['RESET'] if hi else ''}")


def _profile_entries(pr: cProfile.Profile, top: int) -> list[dict[str, object]]:
    stats = pstats.Stats(pr, stream=io.StringIO())
    stats.sort_stats("cumulative")
    raw: Any = getattr(stats, "stats", {})
    entries = [
        {
            "function": funcname,
            "file": filename,
            "line": lineno,
            "calls": nc,
            "primitive_calls": cc,
            "tottime": round(tt, 6),
            "cumtime": round(ct, 6),
        }
        for (filename, lineno, funcname), (cc, nc, tt, ct, _) in raw.items()
    ]
    entries.sort(key=lambda e: e["cumtime"], reverse=True)
    return entries[:top]


def _wrap(text: str, label: str, indent: int = 2, color: str = "") -> str:
    """Render 'Label  text' with continuation lines aligned under the text.

    Colour codes are added after the width is computed, since they occupy no columns on screen but
    would otherwise eat into the wrap budget.
    """
    plain = " " * indent + label + "  "
    body = textwrap.wrap(text, width=max(_WRAP - len(plain), 40)) or [""]
    reset = _colors()["RESET"] if color else ""
    first = f"{' ' * indent}{color}{label}{reset}  {body[0]}"
    return "\n".join([first, *(" " * len(plain) + line for line in body[1:])])


def _group_issues(issues: list[Issue]) -> list[tuple[str, str, list[Issue]]]:
    """Bucket findings by (severity, category) — worst first, then most frequent.

    Grouping is what lets each explanation be printed once per category rather than repeated against
    every occurrence, which is the difference between a report you read and one you skim past.
    """
    groups: defaultdict[tuple[str, str], list[Issue]] = defaultdict(list)
    for issue in issues:
        groups[issue.severity, issue.category].append(issue)
    ordered = sorted(groups.items(), key=lambda kv: (_SEV_ORDER[kv[0][0]], -len(kv[1]), kv[0][1]))
    return [
        (sev, cat, sorted(items, key=lambda i: (i.file, i.line))) for (sev, cat), items in ordered
    ]


def print_severity_legend() -> None:
    c = _colors()
    print(f"  {c['BOLD']}What the severities mean{c['RESET']}")
    for sev in ("HIGH", "MEDIUM", "LOW"):
        print(_wrap(_SEVERITY_POLICY[sev], f"{sev:6}", indent=4, color=c[sev]))
    print()


def print_issues(issues: list[Issue]) -> None:
    c = _colors()
    if not issues:
        print("  No findings.\n")
        print(
            _wrap(
                "Static analysis only sees the shape of the code, not where the time actually "
                "goes. If it is still slow, measure it: perf_check.py --profile <script.py> "
                "-- <args>",
                "Next",
            )
        )
        print()
        return
    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for sev, cat, group in _group_issues(issues):
        counts[sev] += len(group)
        check = _CHECKS[cat]
        plural = "" if len(group) == 1 else "s"
        print(
            f"{c[sev]}{c['BOLD']}{sev:6}{c['RESET']} {c['BOLD']}{cat}{c['RESET']}"
            f" — {check.title}  ({len(group)} occurrence{plural})"
        )
        fixes = {i.fix for i in group}
        for issue in group:
            print(f"       {issue.file}:{issue.line}  {issue.message}")
            if len(fixes) > 1:
                print(f"         → {issue.fix}")
        print(_wrap(check.why, "Why"))
        if len(fixes) == 1:
            print(_wrap(group[0].fix, "Fix"))
        print()
    print(f"  Summary: {counts['HIGH']} high  {counts['MEDIUM']} medium  {counts['LOW']} low\n")
    print_severity_legend()


def _explain_categories(selector: str) -> list[str] | None:
    """Resolve --explain's argument to a category list, or None if it is unknown."""
    if selector == "all":
        return sorted(_CHECKS, key=lambda c: (_SEV_ORDER[_CHECKS[c].primary_severity], c))
    return [selector] if selector in _CHECKS else None


def print_explain(cats: list[str], full: bool) -> None:
    c = _colors()
    print(f"\n{c['BOLD']}perf_check.py — what each check looks for{c['RESET']}")
    print("─" * _WRAP)
    for cat in cats:
        check = _CHECKS[cat]
        col = c[check.primary_severity]
        print(
            f"\n{col}{c['BOLD']}{check.severity:12}{c['RESET']} {c['BOLD']}{cat}{c['RESET']}"
            f" — {check.title}"
        )
        print(_wrap(check.why, "Why"))
        print(_wrap(check.fix, "Fix"))
    if not full:
        return
    print(f"\n{c['BOLD']}Deliberately not flagged{c['RESET']}")
    print("─" * _WRAP)
    for topic, reason in _NOT_FLAGGED:
        print(f"\n  {c['BOLD']}{topic}{c['RESET']}")
        print(textwrap.fill(reason, width=_WRAP, initial_indent="    ", subsequent_indent="    "))
    print()
    print_severity_legend()


def _explain_json(cats: list[str], full: bool) -> None:
    payload: dict[str, Any] = {
        "checks": [{"category": cat, **asdict(_CHECKS[cat])} for cat in cats]
    }
    if full:
        payload["not_flagged"] = [{"topic": t, "reason": r} for t, r in _NOT_FLAGGED]
        payload["severity_policy"] = _SEVERITY_POLICY
    print(json.dumps(payload, indent=2))


def _report_explain(selector: str, use_json: bool) -> int:
    cats = _explain_categories(selector)
    if cats is None:
        _emit_error(
            f"Unknown check category: {selector}",
            "UNKNOWN_CATEGORY",
            hint="Run --explain with no argument to list every category",
        )
        return EXIT_USER_ERROR
    # The catalogue-wide extras — what is deliberately not flagged, the severity
    # policy — belong to the full listing, not to a single category's entry.
    full = selector == "all"
    if use_json:
        _explain_json(cats, full)
    else:
        print_explain(cats, full)
    return EXIT_OK


def _report_json(files: list[Path], profile: str | None, script_args: list[str], top: int) -> int:
    result: dict[str, Any] = {}
    if files:
        issues = _analyze_all(files)
        result["static"] = [asdict(i) for i in issues]
        result["meta"] = {
            "files_analyzed": len(files),
            "issues_total": len(issues),
            "issues_high": sum(1 for i in issues if i.severity == "HIGH"),
            # Shipped with the findings so a caller reading JSON gets the same
            # interpretation guidance a human reading the text report does.
            "severity_policy": _SEVERITY_POLICY,
        }
    if profile:
        script = _profile_target(profile)
        if script is None:
            return EXIT_USER_ERROR
        if script not in files:
            result.setdefault("static", []).extend(asdict(i) for i in analyze(script))
        pr = run_profile(script, script_args, divert_stdout=True)
        result["profile"] = _profile_entries(pr, top)
    print(json.dumps(result, indent=2))
    return EXIT_OK


def _report_text(files: list[Path], profile: str | None, script_args: list[str], top: int) -> int:
    c = _colors()
    if files:
        issues = _analyze_all(files)  # analyze first: a SyntaxError must precede any output
        noun = "finding" if len(issues) == 1 else "findings"
        print(
            f"\n{c['BOLD']}Static analysis — {len(files)} file(s), {len(issues)} {noun}{c['RESET']}"
        )
        print("─" * _WRAP + "\n")
        print_issues(issues)
    if profile:
        script = _profile_target(profile)
        if script is None:
            return EXIT_USER_ERROR
        if script not in files:
            issues = analyze(script)
            if issues:
                print(f"\n{c['BOLD']}Static analysis — {script}{c['RESET']}")
                print("─" * _WRAP + "\n")
                print_issues(issues)
        print_profile(run_profile(script, script_args), script, top)
    return EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="perf_check.py",
        description="Find Python performance problems (static analysis + runtime profile).",
        epilog=textwrap.dedent("""\
            examples:
              perf_check.py app.py                            # static analysis of one file
              perf_check.py src/                              # walk a directory recursively
              perf_check.py app.py --format json              # machine-readable output
              perf_check.py app.py --quiet                    # suppress informational stderr
              perf_check.py --profile slow.py                 # profile at runtime
              perf_check.py --profile script.py -- a b c      # pass args to profiled script
              perf_check.py --explain                         # every check, and what it means
              perf_check.py --explain list-as-queue           # detail for one category
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "files",
        nargs="*",
        metavar="PATH",
        help="Python files or directories to analyze statically (directories walked recursively)",
    )
    p.add_argument("--profile", metavar="SCRIPT", help="script to profile at runtime")
    p.add_argument(
        "--explain",
        nargs="?",
        const="all",
        metavar="CATEGORY",
        help="Explain what a finding category means and what to do about it; "
        "with no argument, every check plus the patterns deliberately not flagged.",
    )
    p.add_argument(
        "--top",
        type=int,
        default=20,
        metavar="N",
        help="top N functions in profile output (default: 20)",
    )
    p.add_argument(
        "--format",
        choices=["json", "text"],
        default="text",
        help="Output format (default: text). Use --format json for agent-callable output.",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Alias for --format json (kept for back-compat).",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress informational stderr (file counts, etc.). Errors still emit.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if "--" in raw:  # everything after -- belongs to the profiled script, not to us
        idx = raw.index("--")
        script_args, raw = raw[idx + 1 :], raw[:idx]
    else:
        script_args = []

    p = _build_parser()
    args = p.parse_args(raw)

    if not args.files and not args.profile and not args.explain:
        p.print_help()
        return EXIT_USER_ERROR

    use_json = args.json or args.format == "json"

    if args.explain:
        return _report_explain(args.explain, use_json)

    try:
        files, missing = _resolve_inputs(args.files) if args.files else ([], [])
    except Exception as exc:
        _emit_error(
            f"Unexpected error resolving inputs: {exc}",
            "RESOLVE_FAILED",
            hint="Check that paths exist and are readable",
        )
        return EXIT_SYSTEM_ERROR

    if missing:
        _emit_error(
            f"Path(s) not found: {', '.join(missing)}",
            "PATH_NOT_FOUND",
            hint="Pass an existing file or directory; directories are walked recursively",
        )
        return EXIT_USER_ERROR

    if args.files and not files:
        _emit_error(
            f"No Python files matched: {', '.join(args.files)}",
            "NO_PYTHON_FILES",
            hint="Pass a .py file, or a directory holding one — directories are walked recursively",
        )
        return EXIT_NOT_FOUND

    if files:
        _log(f"Analyzing {len(files)} file(s)...", quiet=args.quiet)
    else:
        _log(f"Analyzing and profiling {args.profile}...", quiet=args.quiet)

    report = _report_json if use_json else _report_text
    try:
        return report(files, args.profile, script_args, args.top)
    except SyntaxError as exc:
        _emit_error(
            str(exc),
            "PARSE_FAILED",
            hint="Fix the syntax error in the listed file before re-running",
        )
        return EXIT_SYSTEM_ERROR
    except Exception as exc:
        _emit_error(
            f"{type(exc).__name__}: {exc}",
            "UNEXPECTED_ERROR",
            hint="Re-run with the file directly to isolate the failing input",
        )
        return EXIT_SYSTEM_ERROR


if __name__ == "__main__":
    sys.exit(main())
