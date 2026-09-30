---
name: python-performance
description: >
  Find and fix performance problems in Python — a slow script, function, loop, or data pipeline.
  Trigger whenever the user says Python code is slow, hangs, times out, eats memory, or "takes
  forever", and when they ask to optimize, speed up, profile, or benchmark Python. Also
  trigger on review-shaped asks — "is there anything slow in this file", "why does this scale so
  badly", "it was fine on 1k rows and dies on a million" — and on named symptoms: an O(n²) loop,
  a list used as a queue, string concatenation in a loop, a regex recompiled per call, slow
  pandas iteration, or a CLI with a sluggish startup. NOT for speeding up a test suite or CI as
  a build-configuration problem, and NOT for other languages.
compatibility: >
  Python 3.14+, standard library only. `scripts/perf_check.py` parses with `ast` and never
  imports the code it analyses; `--profile` deliberately executes the target script in-process.
metadata:
  version: "1.1"
---

# Python performance

Slowness in Python is nearly always one of two things: a pattern whose cost grows faster than the
input, or time going somewhere nobody has looked. The first is findable by reading the code, and
a script here does that in a second. The second needs a measurement. Do them in that order —
static analysis is cheap enough that skipping it to go straight to guesswork is never the right
trade.

## 1. Check the code

```bash
python3 "${SKILL_DIR}/scripts/perf_check.py" <file-or-directory>
```

Findings are grouped by category, worst first, and each one explains itself: where it is, what it
costs, why it costs that, and the specific rewrite. There is nothing else to read to interpret
the output.

- `--explain` describes every check the tool knows, including the patterns it deliberately stays
  quiet about — reach for it when the tool said nothing and you want to know whether that means
  something.
- `--format json` when you want to filter or count findings programmatically.

Severity is about the shape of the cost, not about how sure the tool is. HIGH means the cost
grows faster than the input and will get worse with real data — plus process spawning, the one
constant factor big enough to dominate a loop on its own; LOW means idiom, where the win is
readability. Don't spend the user's time on LOW findings in code that isn't the bottleneck —
but deciding to leave code alone is a claim about what it costs, and needs a number behind it
exactly as a rewrite does.

## 2. If nothing above LOW is flagged, measure

Static analysis sees shapes, not seconds. A clean result — or one carrying only LOW findings,
which is the same result — means the cause is something only a measurement points at: an
algorithm that's wrong for this data, a chatty I/O or query pattern, or a library call that
costs far more than it looks like it does. It may also mean the code is already fast enough and
the problem is somewhere the user hasn't looked, which is worth just as much to them, and is
worth exactly as little without a measurement to say so.

```bash
python3 "${SKILL_DIR}/scripts/perf_check.py" --profile <script.py> -- <script-args>
```

That runs cProfile and sorts by cumulative time with the script's own frames highlighted; `--`
separates the tool's flags from the arguments passed through.

It genuinely runs the script, in this process, with `__name__` set to `"__main__"` — files get
written, requests get sent, and a `sys.exit` is swallowed rather than ending the run. Where that
touches state the user cares about, profile a copy or a narrower entry point.

Use whatever else fits the question — `timeit` for a head-to-head, `tracemalloc` for memory
growth, a `perf_counter` around one suspect block, `py-spy` for a process already running. You
know these tools; this skill isn't here to re-teach them, only to make sure the measurement
happens before the rewrite.

Read the profile for *cumulative* time first to find which subtree is expensive, then *tottime*
to find where inside it the work actually is. A function with high cumulative and near-zero
tottime is a caller, not a culprit.

## 3. Prove the fix

A change that "should be faster" is not a result. Time before and after on input large enough for
the effect to appear — quadratic fixes are invisible on ten items and dramatic on ten thousand,
so input size matters more than repetition count — and tell the user the actual numbers. If the
measurement doesn't move, revert it: unmeasured optimizations are how code gets harder to read
for nothing.

Time it, don't profile it. cProfile's per-call overhead inflates call-heavy code several-fold,
so profile totals are comparable only to other profile totals — the before and after you quote
are wall-clock.

When the old version is too slow to run at the size that hurts, shrink the input until it
finishes and time both versions there. Two measured numbers at 5k rows, plus the shape of the
growth, tell the user more than one measured number and a guess at 400k — and where you do
extrapolate, say that you did, so they can tell your evidence from your arithmetic.

A faster wrong answer is not a fix. The timing harness already has the inputs in front of it, so
capture what the code returns on each side of the change and compare it; where the output is
large, hash it. Say how you checked. A green test suite means the tests still pass, which is a
weaker claim than it looks: the behaviour most at risk from a performance rewrite is the part
nobody wrote a test for — tie-break order, which duplicate wins, what an empty input returns.
