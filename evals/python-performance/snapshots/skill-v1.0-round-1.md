---
name: python-performance
description: >
  Find and fix performance problems in Python — a slow script, function, loop, or data pipeline.
  Trigger whenever the user says Python code is slow, hangs, times out, eats memory, or "takes
  forever", and whenever they ask to optimize, speed up, profile, or benchmark Python. Also
  trigger on review-shaped asks — "is there anything slow in this file", "why does this scale so
  badly", "it was fine on 1k rows and dies on a million" — and on named symptoms: an O(n²) loop,
  a list used as a queue, string concatenation in a loop, a regex recompiled per call, slow
  pandas iteration, or a CLI with a sluggish startup. NOT for speeding up a test suite or CI as
  a build-configuration problem, and NOT for other languages.
compatibility: >
  Python 3.14+, standard library only. `scripts/perf_check.py` parses with `ast` and profiles
  with `cProfile`; it never imports the code it analyses statically.
metadata:
  version: "1.0"
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
- Exit `0` means the analysis ran, whatever it found; `3` means no Python files matched the path.

Severity is about the shape of the cost, not about how sure the tool is. HIGH means the cost
grows faster than the input and will get worse with real data — plus process spawning, the one
constant factor big enough to dominate a loop on its own; LOW means idiom, where the win is
readability. Don't spend the user's time on LOW findings in code that isn't the bottleneck.

## 2. If nothing is flagged, measure

Static analysis sees shapes, not seconds. When it comes back clean and the code is still slow,
the cause is something only a measurement points at — an algorithm that's wrong for this data, a
chatty I/O or query pattern, or a library call that costs far more than it looks like it does.

```bash
python3 "${SKILL_DIR}/scripts/perf_check.py" --profile <script.py> -- <script-args>
```

That runs cProfile and sorts by cumulative time with the script's own frames highlighted; `--`
separates the tool's flags from the arguments passed through. Use whatever else fits the
question — `timeit` for a head-to-head, `tracemalloc` for memory growth, a `perf_counter` around
one suspect block, `py-spy` for a process already running. You know these tools; this skill isn't
here to re-teach them, only to make sure the measurement happens before the rewrite.

Read the profile for *cumulative* time first to find which subtree is expensive, then *tottime*
to find where inside it the work actually is. A function with high cumulative and near-zero
tottime is a caller, not a culprit.

## 3. Prove the fix

A change that "should be faster" is not a result. Time before and after on input large enough for
the effect to appear — quadratic fixes are invisible on ten items and dramatic on ten thousand,
so input size matters more than repetition count — and tell the user the actual numbers. If the
measurement doesn't move, revert it: unmeasured optimizations are how code gets harder to read
for nothing.
