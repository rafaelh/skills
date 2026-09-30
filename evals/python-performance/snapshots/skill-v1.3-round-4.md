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
  `scripts/perf_bench.py` imports and runs the bench module you give it, and its `--baseline`
  shells out to `git worktree`, so that flag needs a git repository.
metadata:
  version: "1.3"
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

Don't spend the user's time on LOW findings in code that isn't the bottleneck — but deciding to
leave code alone is a claim about what it costs, and needs a number behind it exactly as a
rewrite does.

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

A profile answers "where does the time go". To answer "how does the cost grow with the input" —
the question behind *it was fine on 1k rows and dies on a million* — write a bench module and
sweep it:

```bash
python3 "${SKILL_DIR}/scripts/perf_bench.py" bench.py --sizes 20000,40000,80000
```

`bench.py` is yours, and is the only part that knows this repo: `setup(n)` builds an input of size
n, `run(data)` calls the code under test and returns its result. Only `run` is timed, so building
the workload never lands in the measurement. `--help` carries a worked example. The script sweeps
the sizes, fits the growth curve, and hashes each result.

A slope near 1 means the cost tracks the input; near 2 means it grows with the square of it.
Constant factors dominate at small sizes, so the same quadratic function can read *linear* at 8k
items and *quadratic* at 80k — if the slope comes back near 1 on code the user says falls over, go
up an order of magnitude before believing it.

Put the size the user named at the top of the sweep, and find out whether it finishes there before
assuming it won't. A measured number at their scale needs no caveat and settles the question; a
projection to it always invites the follow-up. Sweep the smaller sizes first — they cost seconds
and tell you the slope — then let the largest one run. If it is still going after a minute or two,
kill it and use the largest size that did finish, which is what `--project` is for.

## 3. Prove the fix

A change that "should be faster" is not a result. Once you have edited, one call measures both
sides of the change:

```bash
python3 "${SKILL_DIR}/scripts/perf_bench.py" bench.py --sizes 20000,40000,80000 \
    --baseline git:HEAD --recheck src/nightly/report.py
```

`--baseline` runs the same bench against the committed tree in a throwaway detached worktree and
prints before, after and the speed-up at each size. It compares the result hashes too, so a faster
wrong answer surfaces as `OUTPUT DIFFERS` instead of as a win. `--recheck` re-runs step 1 over the
files you changed, in that same call, so you can say which findings cleared without spending
another one.

This call re-times both sides, so it replaces the step-2 sweep rather than adding to it. There is
no reason to measure the current code again before running it: a run that sweeps, edits, sweeps
and then baselines has paid for the same numbers twice.

Never `git stash` to get a baseline. The user's uncommitted work is not yours to move, and a stash
that fails to pop takes it with them.

Time before and after on input large enough for the effect to appear, and tell the user the
actual numbers. If the measurement doesn't move, revert it: unmeasured optimizations are how
code gets harder to read for nothing.

Time it, don't profile it. cProfile's per-call overhead inflates call-heavy code several-fold,
so profile totals are comparable only to other profile totals — the before and after you quote
are wall-clock.

When the old version is too slow to run at the size that hurts — which is the usual reason the
named scale drops off the sweep — shrink the input until it finishes and time both versions there.
Two measured numbers at 5k rows, plus the shape of the growth, tell the user more than one measured
number and a guess at 400k.

**Every number in the write-up is either measured or marked as not.** Write the projection as part
of the sentence — *"0.28s at 80k events, down to 0.02s; at the 400k you quoted that projects to
about 6s, extrapolated"* — which is the line `--project 400000` prints for you, already labelled.
An unmarked projection reads as a measurement, and quietly presenting one as the other is the most
common way an otherwise honest summary misleads. The same goes for a change you never timed: say
it is untimed, or time it. "Also a bit faster" with nothing behind it is the claim to cut.

A faster wrong answer is not a fix. `--baseline` hashes what the code returned on each side and
tells you whether they match; say in the summary how you checked. A green test suite means the
tests still pass, which is a weaker claim than it looks: the behaviour most at risk from a
performance rewrite is the part nobody wrote a test for — tie-break order, which duplicate wins,
what an empty input returns.
