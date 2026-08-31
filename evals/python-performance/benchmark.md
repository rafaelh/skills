# Eval benchmark — `python-performance`

A dated record of what this skill scored, so a future round can be compared against it rather than
read in isolation. Append rounds; don't rewrite them. The harness that produces these numbers lives
beside this file — read [README.md](README.md) before re-measuring.

Two arms (`with_skill`, `without_skill`), one run per cell. At one run per cell, treat a 20% swing
in tokens or time as noise. The mechanical checks are the durable signal — files on disk, their
AST, the skill's own static checker, and two pytest runs — and they re-compute identically over a
stored workspace. The judgement checks are graded by a model from the run's summary alone and move
by a check or two between gradings of the same run; two of round 1's cells shifted by one when the
rubric was widened and every run re-graded.

Workspaces are kept outside the repo at `~/.cache/claude-evals/python-performance/iteration-<n>`,
so a later rubric can re-score an earlier round.

## Rubric versions

| Version | Assertions | Introduced |
|---|---|---|
| v1 | 8 shared mechanical + per-fixture (5 `report`, 4 `ingest`, 4 `tidy`, 5 `logscan`) + 3 judgement per case | Round 1 |
| v1.1 | v1 unchanged mechanically; the output-equivalence judgement statement is now shared across the three cases that change something, in one wording | After round 1 |

v1.1 exists because round 1 scored 0/2 on "the run says how it knows the digest still renders the
same output" and that check only ran on `report-repo`. The wording is now
*"…the code still returns the same answers…"* on evals 0, 1 and 3 — a retirement of the
digest-specific phrasing rather than an addition, so round 1's stored runs need re-grading before
their numbers line up with round 2's. The judgement half reads `outputs/summary.md`, which is
kept, so that is one command over the stored workspace:

```bash
find ~/.cache/claude-evals/python-performance/iteration-1 -name timing.json -printf '%h\n' \
  | xargs -L1 .venv/bin/python evals/python-performance/grade.py
```

Three checks were repaired *before* round 1 was recorded, each because a run had plainly done the
thing the check said it had not:

- **The tool-call log truncated at 200 characters.** A timing command is usually a `cd` into an
  absolute workspace path followed by an inline script, so "a measurement was actually executed"
  read 0/4 in the arm that had measured every time. `shared/claude_cli.run_claude` grew a
  `tool_summary_chars` argument (default unchanged at 200; this suite passes 1000) and the round
  was re-run from scratch. The discarded round is kept as `iteration-1-truncated-log`.
- **A timing harness written outside the repo was invisible.** The file scan only looked inside the
  staged repo, and one run wrote `bench.py` to a scratch directory. The check now also reads the
  call log for a Bash invocation of a `bench`/`profil`/`timing`/`timeit`/`measure` script —
  excluding `perf_check.py`, which is a static checker, and counting it would hand every
  `with_skill` run a free pass on the check that matters most.
- **"The summary says the regex is not where the time goes" missed the phrasing runs use.** The
  verdict attaches to the subject — *"that's the cost, not the regex"* — rather than arriving as a
  sentence about the regex. Widened; a widening can only turn a fail into a pass, which is what
  keeps later rounds comparable.

## Round 1 — 2026-08-31, sonnet

### Per eval

| Eval | with_skill | without_skill |
|---|---|---|
| 0 quadratic-digest | 88% (14/16) | 88% (14/16) |
| 1 static-clean-needs-a-profile | 93% (14/15) | 67% (10/15) |
| 2 low-findings-only-restraint | 77% (10/13) | 38% (5/13) |
| 3 wrong-hypothesis | 100% (16/16) | 88% (14/16) |
| **Mean** | **90.0% (54/60)** | **71.7% (43/60)** |

### Checks that separated the arms

| Check | with_skill | without_skill |
|---|---|---|
| perf_check.py was run before the first edit | 4/4 | 0/4 |
| The measurement came before the first edit | 2/2 | 1/2 |
| The customer export is indexed once instead of scanned per row | 1/1 | 0/1 |
| The bottleneck was identified from a measurement the run actually took | 1/1 | 0/1 |
| The diff stays small — at most 15 changed lines across src/ | 1/1 | 0/1 |
| The summary says this module is not where the time goes | 1/1 | 0/1 |
| The run concludes the flagged patterns are not worth changing | 1/1 | 0/1 |
| The user is left knowing where the time actually goes | 1/1 | 0/1 |

### Cost

|  | with_skill | without_skill |
|---|---|---|
| Runs | 4 | 4 |
| Tokens, mean | 388,396 | 263,525 |
| Wall clock, mean | 50s | 64s |
| Tool calls, mean | 10.5 | 8.2 |
| Cost | $0.72 | $0.53 |

The skill costs about 47% more tokens and two and a half more tool calls, and finished *faster* in
wall clock — the baseline spent its time re-reading code that the checker summarises in a second.

### What the round showed

**The gap is not about finding quadratic code.** On `report-repo` the arms tied at 88%: sonnet
without the skill spotted all three quadratic patterns, fixed them, timed the result and kept the
hidden behaviours. A skill that only said "look for O(n²)" would have measured nothing here. The
whole 18-point mean gap comes from the three cases where reading the code is not the answer.

**It is about what happens when the code looks fine, or looks guilty.** `ingest-repo` (93% against
67%) is the clearest: the `with_skill` run ran the checker, got nothing, built a timing harness,
found `find_customer`, and only then edited. The baseline edited first and timed afterwards — and
its rewrite did not survive the index check. `tidy-repo` (77% against 38%) is the same instinct in
the other direction: the baseline rewrote the five LOW idiom findings, reported a speed-up it had
not measured, and never told the user that the 280ms pricing call is where checkout p95 actually
is.

**Both arms are weak at the same thing.** "Every speed claim has a measured number beside it" went
2/4 in both arms, and "the run says how it knows the digest still renders the same output" went 0/1
in both. Runs quote a before and an after for the change they made, then add unmeasured claims
around it. That is the gap worth aiming step 3 at in the next revision.

**The one `with_skill` failure worth reading** is `tidy-repo`: the run followed step 1, got only LOW
findings, and concluded — correctly, and in the right register, pushing back on the reviewer — that
this file is not the p95 problem. But it never measured. It asserted "microseconds regardless" and
"doesn't hold up against measurement" while having timed nothing. Three checks caught it. The skill
tells a run to measure when static analysis comes back *clean*; it does not say what to do when it
comes back *only LOW*, and this run read that gap the way the prose allows.

### To watch next round

- `report-repo` at 88%/88% is not yet discriminating. If it ties again, the case needs a sharper
  question than "is the quadratic gone" — the hidden suite is doing its job, but nothing there
  separates a run that proved its fix from one that merely made it.
- "The run says how it knows the digest still renders the same output" is 0/2. One round is not
  enough to call it unsatisfiable, but if nothing passes it in round 2 it needs re-reading rather
  than believing.
- One run per cell, and `tidy-repo`'s correct answer is close to binary. Repeat that cell
  (`--runs 3`) before drawing a conclusion from a change to the skill's restraint language.

## After round 1 — skill v1.1

Three edits to `SKILL.md`, each answering a specific failure above rather than a hunch. The
round-1 body is kept verbatim at `snapshots/skill-v1.0-round-1.md`, so round 2 can run three arms
and measure the edit instead of assuming it.

| Edit | What it answers |
|---|---|
| Step 2's trigger goes from "if nothing is flagged" to "if nothing above LOW is flagged", and step 1 gains *deciding to leave code alone is a claim about what it costs* | `tidy-repo`/`with_skill`: LOW-only findings meant step 2 never fired, and the run answered out of the severity table — "microseconds regardless" — having timed nothing |
| Step 3: when the old version is too slow to run at the size that hurts, shrink the input until it finishes and time both there; where you extrapolate, say so | evals 0 and 1 both reported an *extrapolated* before against a measured after. "Every speed claim has a measured number" went 2/4 in both arms, and this is what it was catching |
| Step 3: a faster wrong answer is not a fix — capture the output on each side of the change and compare it, and say how you checked | 0/2 on output equivalence. Both arms rested on a green suite, which is exactly what the hidden suites are built to be indifferent to |

`perf_check.py` also gained a fix this suite found rather than measured: `visit_Compare` matched
only `ast.In`, so `x not in ["a", "b", "c"]` — the same scan, the same rewrite — was never
flagged, and neither was `k not in d.keys()`. `report-repo` writes that filter in the positive
form because of it, and stays that way: editing a fixture makes round 1 a different experiment.

A round 2 that only re-ran the same two arms would confound the three prose edits with the
checker fix. Run it as `--arms with_skill,old_skill,without_skill` with `old_skill` on the
snapshot, and repeat `tidy-repo` (`--runs 3`) — its correct answer is close to binary, and one
observation cannot tell a fixed skill from a lucky run.
