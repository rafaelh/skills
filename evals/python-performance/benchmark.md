# Eval benchmark — `python-performance`

A dated record of what this skill scored, so a future round can be compared against it rather than
read in isolation. Append rounds; don't rewrite them. The harness that produces these numbers lives
beside this file — read [README.md](README.md) before re-measuring.

Round 1 is two arms (`with_skill`, `without_skill`) at one run per cell; round 2 adds `old_skill`
on a snapshot and repeats every cell three times; round 3 keeps three arms at five runs per cell;
round 4 keeps five for the two skill arms and drops the baseline to one, the settled result held as
a floor. At one run per cell, treat a 20% swing in tokens or time as noise — and see round 2's and
round 3's per-cell spread for how wide that band really is once you can see it. Five runs was still
not enough to call a 2-point difference between two skill versions, and round 4 measured why: the
same skill body scored 1.2 points apart in two different rounds. The
mechanical checks are the durable signal — files on disk, their AST, the skill's own static checker,
and two pytest runs — and they re-compute identically over a stored workspace. The judgement checks
are graded by a model from the run's summary alone and move by a check or two between gradings of
the same run; two of round 1's cells shifted by one when the rubric was widened and every run
re-graded.

Workspaces are kept outside the repo at `~/.cache/claude-evals/python-performance/iteration-<n>`,
so a later rubric can re-score an earlier round.

## Rubric versions

| Version | Assertions | Introduced |
|---|---|---|
| v1 | 8 shared mechanical + per-fixture (5 `report`, 4 `ingest`, 4 `tidy`, 5 `logscan`) + 3 judgement per case | Round 1 |
| v1.1 | v1 unchanged mechanically; the output-equivalence judgement statement is now shared across the three cases that change something, in one wording | After round 1 |
| v1.2 | v1.1 with two mechanical checks repaired — both were grading *how* a run did something rather than whether it did it. No statement added or retired | During round 2 |
| v1.3 | v1.2 plus two shared mechanical statements — the working tree was not moved to get a baseline, and every runtime quoted at the user's scale is marked as a projection — and one widening: `DURATION` now reads `25-minute` as a duration | For round 3 |
| v1.4 | v1.3 with the projection check gated on what the run measured: a runtime quoted at a size at or below the largest size the run actually ran something at is a measurement, and the marker is no longer demanded of it. No statement added or retired | For round 4 |
| v1.5 | v1.4 with that gate taught about a workload named in two dimensions — `ingest`'s 180k customers *and* 400k rows — so reaching the smaller one counts as having run it. No statement added or retired | After round 4 |

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

## Rubric v1.2 — two repairs during round 2

Both were found by reading a cell whose number contradicted the transcripts, and both are the
failure mode this file has now recorded three times: the harness reading *how* a run did something
instead of *whether* it did. Neither adds or retires a statement, so both rounds were re-graded
under v1.2 and the numbers below are all on that footing.

- **`MUTATION` counted a write outside the repo as "the first edit".** It matched any
  `Edit|Write|NotebookEdit`, and the tool log leaves paths outside the staged repo absolute. A run
  that wrote its timing harness with `Write` and then measured therefore failed *"the measurement
  came before the first edit"*, while a run that piped the identical script through a heredoc
  passed. This fell on `with_skill` hardest — step 3 asks for a harness that holds the inputs on
  both sides of the change, which is a thing you write to a file — and inverted the check to 3/6
  against a baseline's 6/6. Scoped to repo-relative paths, it is 6/6 in all three arms: a
  regression floor, not a discriminator.
- **The `ingest` indexing check only recognised `setdefault`.** `old_skill` and `without_skill`
  wrote `ref = customer["ref"]` / `if ref not in index: index[ref] = customer` — the same
  index, built once, first-wins, passing the hidden suite — and scored 0/3 and 1/3 against
  `with_skill`'s 3/3. That was three points of pure idiom preference in the skill's favour. Widened
  to the `if ref not in index` spelling; now 3/3 in every arm.

The second one is worth dwelling on: it flattered the skill, and it survived round 1 because round
1 had one run per cell and that run happened to use `setdefault`. Repeats are what exposed it.

## Round 1 restated — rubric v1.2

| Eval | with_skill | without_skill |
|---|---|---|
| 0 quadratic-digest | 94% (15/16) | 88% (14/16) |
| 1 static-clean-needs-a-profile | 88% (14/16) | 69% (11/16) |
| 2 low-findings-only-restraint | 77% (10/13) | 38% (5/13) |
| 3 wrong-hypothesis | 100% (17/17) | 82% (14/17) |
| **Mean** | **90.3% (56/62)** | **71.0% (44/62)** |

Recorded as 90.0%/71.7% under v1 above. The stored v1 gradings are kept beside each run as
`grading-v1-rubric.json`.

## Round 2 — 2026-09-01, sonnet

Three arms, three runs per cell, 36 runs. `old_skill` is `snapshots/skill-v1.0-round-1.md`, so the
`with_skill`/`old_skill` column is the v1.1 prose edits measured on their own, and the
`perf_check.py` `not in` fix is held constant across both.

### Per eval

| Eval | with_skill | old_skill | without_skill |
|---|---|---|---|
| 0 quadratic-digest | 96% (46/48) | 94% (45/48) | 83% (40/48) |
| 1 static-clean-needs-a-profile | 98% (47/48) | 94% (45/48) | 79% (38/48) |
| 2 low-findings-only-restraint | 97% (38/39) | 95% (37/39) | 46% (18/39) |
| 3 wrong-hypothesis | 96% (49/51) | 92% (47/51) | 88% (45/51) |
| **Mean** | **96.8% (180/186)** | **93.5% (174/186)** | **75.8% (141/186)** |

### Checks that separated the arms

| Check | with_skill | old_skill | without_skill |
|---|---|---|---|
| perf_check.py was run before the first edit | 12/12 | 12/12 | 0/12 |
| The run says how it knows the code still returns the same answers | 9/9 | 5/9 | 3/9 |
| Every speed claim has a measured number beside it | 8/12 | 6/12 | 4/12 |
| A measurement was actually executed, not just reasoned about | 12/12 | 11/12 | 9/12 |
| The diff stays small — at most 15 changed lines across src/ | 3/3 | 3/3 | 0/3 |
| The summary quotes a concrete measured runtime | 3/3 | 3/3 | 0/3 |
| The summary says this module is not where the time goes | 3/3 | 3/3 | 1/3 |
| The run concludes the flagged patterns are not worth changing | 3/3 | 3/3 | 1/3 |
| The user is left knowing where the time actually goes | 3/3 | 3/3 | 1/3 |
| The bottleneck was identified from a measurement the run took | 2/3 | 3/3 | 0/3 |
| The measurement was taken at a visible input size, stated | 8/9 | 9/9 | 9/9 |
| The summary says the regex is not where the time goes | 3/3 | 2/3 | 3/3 |
| The summary reports a before and an after measurement | 9/9 | 9/9 | 8/9 |

### Per-cell spread

Three runs per cell, pass rate per run:

| Eval | with_skill | old_skill | without_skill |
|---|---|---|---|
| 0 | 100, 88, 100 | 100, 88, 94 | 81, 81, 88 |
| 1 | 100, 94, 100 | 94, 94, 94 | 81, 81, 75 |
| 2 | 92, 100, 100 | 100, 85, 100 | 38, 38, 62 |
| 3 | 94, 94, 100 | 94, 94, 100 | 88, 88, 88 |

### Cost

|  | with_skill | old_skill | without_skill |
|---|---|---|---|
| Runs | 12 | 12 | 12 |
| Tokens, mean | 481,080 | 402,123 | 301,708 |
| Wall clock, mean | 80s | 92s | 57s |
| Tool calls, mean | 13.4 | 12.2 | 9.4 |
| Tokens per tool call | 35,857 | 33,051 | 32,040 |
| Cost | $3.11 | $2.61 | $1.96 |

The extra tokens are turns, not prose. Across all 36 runs `tokens ~= 37,570 * tool_calls - 43k`
at R^2 0.85, and at *matched* tool counts the arms are indistinguishable — 7 calls costs 257k with
the skill and 219k without, 11 calls costs 301k with and 366k without. SKILL.md is 5.6 KB, about
1.4k tokens; re-sent on all 13 turns that is under 4% of the total. The count is superlinear in
turns because `_usage_tokens` sums `cache_read_input_tokens`, so every turn re-bills the whole
transcript so far and the fourteenth tool call costs the accumulated context again, not just its
own output.

So the question to ask of the cost column is what the extra turns bought. On `report-repo` the
baseline spends 7: read, glob, glob, read the test, edit, pytest, and one after-only timing. The
`with_skill` run spends 15 for the same fixture — the checker before the first edit, a timing
harness, a baseline measurement, three edits, pytest, the checker again, an after measurement
across five input sizes. Every one of those is a step the baseline skipped, and skipping them is
what costs it 21 points. The tokens buy evidence, not comprehension: the checker *does* replace the
baseline's code-spelunking, which is why round 1's `with_skill` arm finished faster in wall clock
despite spending more tokens. The skill then spends that saving, and more, proving the change
worked.

Two cells qualify this. Eval 2, where the correct answer is to change almost nothing, costs the
skill no extra turns at all (7.3 against 6.7). Eval 3's baseline is nearly as expensive as the
skill arm (16 against 18 calls) and scores well below it — it pursues the wrong hypothesis at
length, so those turns buy nothing. Turn count is the lever if a later revision wants the skill
cheaper: measuring before and after in one scripted invocation rather than two would take real
tokens off, where trimming the prose would not.

### What the round showed

**The skill is worth 21 points over no skill** (96.8% against 75.8%), and the gap is wider and
better-evidenced than round 1's, because three runs per cell make it readable. It costs 59% more
tokens and four more tool calls to get there.

**The v1.1 edits are worth 3.3 points over v1.0** (180/186 against 174/186), and essentially all of
it is one edit. *"The run says how it knows the code still returns the same answers"* goes 9/9
against v1.0's 5/9 — the check that sat at 0/2 in round 1 and was flagged here as possibly
unsatisfiable. It was satisfiable; the skill just had to ask. The mechanism is visible in the
summaries: `with_skill` runs reach for SHA-256 over the output on both sides of the change, which
is the step-3 sentence *"where the output is large, hash it"* showing up almost verbatim in
behaviour.

**The extrapolation edit shows a weak positive.** "Every speed claim has a measured number" moved
from 6/12 to 8/12 against v1.0 — the right direction, still the weakest check in the suite, and at
this sample size not much more than suggestive. Round 1's eval-0 `with_skill` run marking its 400k
figure *"(not run — would extrapolate)"* is the behaviour the edit was written for, and it does
appear.

**The restraint edit cannot be credited.** `tidy-repo` is 97% `with_skill` against 95% `old_skill`
— inside the per-cell spread. Round 1's 77% for v1.0 on that case was one unlucky run, not a
systematic gap, which is exactly what repeating the cell was supposed to establish. The step-2
"nothing above LOW" wording is not shown to have done anything; it is also cheap and consistent
with the rest of the prose, so leaving it is fine, but it should not be described as a fix.

**Both arms with the skill beat the baseline on the same axis, and it is not finding quadratic
code.** Every mechanical rewrite check — the join, the front-drain, the set membership, the
indexed export, the once-read rules file — is 3/3 in all three arms. Sonnet does those with or
without the skill. So is the hidden behaviour suite, at 9/9 everywhere: no arm broke a trap this
round. What the skill buys is the reporting discipline around the rewrite: that a measurement
happened, at a stated size, with a number attached, and with a reason to believe the output did
not change.

**`tidy-repo` remains the sharpest case in the suite**, at 46% for the baseline against 97%. It is
the only case where the correct answer is to change almost nothing, and the baseline reliably fails
it by rewriting five LOW findings and reporting an unmeasured win.

### To watch next round

- **The mechanical half has largely stopped measuring.** 17 of 30 checks are now identical in all
  three arms — every fixture-specific rewrite check, the hidden suites, the frozen-file checks, the
  why-comments, and (after the v1.2 repair) the measurement-order check. They are regression floors
  and worth keeping as such, but a round 3 that wants to separate skill versions needs sharper
  questions, not these. The live signal is concentrated in four checks.
- **`wrong-hypothesis` has gone quiet.** "The run tells the user their regex hypothesis was wrong"
  is 3/3 in every arm, where round 1 had the baseline ahead. At 96/92/88 the case now separates
  the skill from nothing much. If it ties again it needs a harder question.
- **"Every speed claim has a measured number" at 8/12 is the one live weakness.** It is the lowest
  score in the `with_skill` column and has been the lowest in both rounds. If a v1.2 of the skill
  is written, this is what to aim it at.
- **If cost becomes a constraint, cut turns.** Tokens track tool calls at R^2 0.85 and the skill's
  premium is entirely the extra steps, so any revision aimed at cost has to remove a step — folding
  the before and after measurements into one invocation is the obvious candidate — and would then
  have to be checked against the measurement checks it exists to satisfy.
- **Per-cell spread runs to 24 points** (`tidy-repo`/`without_skill`: 38, 38, 62). Three runs is
  enough to see a 21-point arm gap and not enough to call a 3-point one. Any future claim that one
  skill version beats another by low single digits needs more repeats than this round had.

## After round 2 — skill v1.2

Nothing here has been measured yet; this records what changed and what round 3 has to settle. The
round-2 body is kept verbatim at `snapshots/skill-v1.1-round-2.md`.

The round's cost decomposition pointed at the same place its weakest check did. Tokens track tool
calls, the two biggest per-run deltas over the baseline were the measurement turns and a *second*
`perf_check.py` call the skill never asked for, and three of the four failures of "every speed
claim has a measured number" were one mistake: a number extrapolated to the size the user named
and written up as though it had been timed. A tool that owns the measurement can fix both — it
collapses the turns, and it can print the projection already labelled.

| Change | What it answers |
|---|---|
| New `scripts/perf_bench.py`. The agent writes only `setup(n)` / `run(data)`; the script owns the size sweep, best-of-k timing, a SHA-256 per result, the log-log growth fit, and `--baseline git:HEAD` — which times the committed tree in a detached worktree, so before, after, speed-up and output equivalence come back from one call | 2.8 measurement turns per run, each re-deriving the same harness; plus the duplicate checker call, which `--recheck` folds into the same invocation |
| Step 3: *every number in the write-up is either measured or marked as not*, with the sentence written out, and `--project N` printing that line pre-labelled | "Every speed claim has a measured number" — 8/12, the lowest `with_skill` score in both rounds, and three of its four failures were unmarked extrapolations |
| Step 2 gains the growth sweep and the warning that the same quadratic function reads *linear* at 8k items and *quadratic* at 80k | Found while smoke-testing `perf_bench.py` on `report-repo`: measuring at a size where the effect has not appeared yet is a wrong answer that looks like a measurement |
| Step 3: never `git stash` to get a baseline | One round-2 run did exactly that. A stash that fails to pop takes the user's uncommitted work with it — the tool now uses a throwaway worktree instead |
| Step 1's severity explainer is cut back to the LOW-restraint sentence | Every check the HIGH/LOW definitions could drive — no HIGH finding remains, and all five fixture-specific rewrites — is 100% in the no-skill arm in both rounds. The tool prints severity with each finding and `--explain` documents the scheme, so the paragraph also contradicted step 1's "there is nothing else to read to interpret the output" |
| Step 3 drops *"quadratic fixes are invisible on ten items and dramatic on ten thousand"* | "The measurement was taken at a visible input size, stated" is 3/3 in both arms in round 1 and the only round-2 check where `with_skill` scores *below* baseline (8/9 against 9/9). Step 2's growth sweep now makes the point with a measured number instead |

The last two are removals rather than additions, and neither is expected to move a number: they
are justified by checks that are saturated in *every* arm, which is evidence the prose was not
doing the work, not evidence that cutting it helps. Round 2 also showed tokens track tool calls
(R^2 0.85) with SKILL.md under 4% of a run's total, so the ~90 words buy nothing measurable. If
any of the saturated checks above regresses in round 3, these are the first edits to suspect.

**Round 3 has a rubric problem to settle first.** 17 of 30 checks were already identical in all
three arms, so the mechanical half will not separate v1.2 from v1.1 on its own; and the two live
checks this revision targets are both judgement checks, which move by a check or two between
gradings. Adding a mechanical assertion for *the projection is labelled* would be a widening of
the kind this file allows — it can only turn a fail into a pass — but the honest reading is that a
3-point difference was not callable at three runs per cell, and these edits are aimed at a gap
about that size. Round 3 needs more repeats than round 2 had, or it needs harder cases.

## Rubric v1.3 — two additions for round 3

Both are *additions*, not rewrites, and both are computed from `outputs/summary.md` and
`outputs/tool-calls.txt`, which every stored round keeps. Rounds 1 and 2 must be re-graded under
v1.3 before their totals line up with round 3's — the denominators change by two on evals 0, 1 and
3 and by one on eval 2.

Both were calibrated against the stored rounds before being adopted, which is the only reason to
trust that they measure anything. A third candidate was dropped for failing that calibration.

**"Every runtime quoted at the scale the user named is marked as a projection."** Each prompt names
a workload no run can reach inside its budget — 400k events, 400k rows against 180k customers, a
25-minute pass over a day of logs. A duration quoted *there* is arithmetic no matter how much the
run measured elsewhere. The check finds the scale in the summary, looks for a duration or a ratio
within 90 characters, and requires an explicit marker; hedges (`should`, `about`, `~`) do not
count, because those are what a run writes either way. `tidy-repo` does not carry it — its prompt
names no scale.

Scored over the stored rounds, this is the least saturated check in the suite:

| | round 1 | round 2 |
|---|---|---|
| with_skill | 0/3 | 2/9 |
| old_skill | — | 0/9 |
| without_skill | 0/3 | 0/9 |

It is a near-floor for every arm, which is exactly what a round comparing skill versions needs, and
it is the mechanical sibling of the judgement check that has been the weakest `with_skill` score in
both rounds. Three of round 2's four failures of that judgement check were this and nothing else.
v1.1's *"where you do extrapolate, say that you did"* moved it from 0/3 to 2/9; v1.2 turns it into
a rule with a sentence to copy and has `--project N` print the labelled line, so if the edit works
this is where it shows.

**"The baseline was taken without moving the user's working tree."** Catches `git stash`,
`git reset --hard`, `git checkout --` and `git restore`. Round 1: none. Round 2: **5 of 36 runs**,
spread across all three arms — `with_skill` 2, `old_skill` 1, `without_skill` 2. None lost work in
the end, but reaching for a stash to get a before-version is one failed pop away from taking the
user's uncommitted work with it, and the spread across arms says it is the natural idiom rather
than something the skill taught. Skill v1.2 forbids it by name and `perf_bench.py --baseline` uses
a detached worktree, so this is the floor under that.

**One widening.** `DURATION` now allows a hyphen between the number and its unit, so `25-minute`
reads as a duration. It was missing the phrasing runs use to quote the user's own figure back at
them, which left the claim attached to it ungraded — the `logscan` run that wrote *"this should
take your 25-minute run down to well under a minute"* passed the new check until this was fixed. A
widening can only turn a fail into a pass, which is what keeps the earlier rounds comparable.

**The candidate that was dropped.** "The largest size measured is one where the effect is visible"
would have been the mechanical sibling of the judgement check about input size — and it cannot be
computed honestly today. Sizes are only unambiguous on a `perf_bench.py --sizes` flag; scraped out
of a hand-rolled harness they come back as the scratch directory's UUID digits and Unix
timestamps, which is what the calibration returned (`8238`, `8262`, `4700000`). It is recorded as
`swept_sizes` in the execution metrics instead, and becomes a real check once enough runs sweep
through the tool for the numbers to mean something.

**Two new execution metrics**, not scored: `bench_calls` (adoption of `perf_bench.py`) and
`stashes`. `bench_calls` stays unscored on purpose — only an arm carrying the skill can know the
script exists, and scoring that would inflate the arm gap the way round 2's `setdefault`-only index
check did.

## Rounds 1 and 2 restated — rubric v1.3

Re-graded from the stored workspaces so their totals line up with round 3's. The v1.2 gradings are
kept beside each run as `grading-v1.2-rubric.json`, as round 1's v1 gradings already were.

| Eval | R1 with_skill | R1 without_skill | | R2 with_skill | R2 old_skill | R2 without_skill |
|---|---|---|---|---|---|---|
| 0 quadratic-digest | 83% (15/18) | 78% (14/18) | | 89% (48/54) | 85% (46/54) | 81% (44/54) |
| 1 static-clean-needs-a-profile | 83% (15/18) | 67% (12/18) | | 94% (51/54) | 89% (48/54) | 76% (41/54) |
| 2 low-findings-only-restraint | 79% (11/14) | 43% (6/14) | | 100% (42/42) | 93% (39/42) | 50% (21/42) |
| 3 wrong-hypothesis | 95% (18/19) | 79% (15/19) | | 89% (51/57) | 86% (49/57) | 81% (46/57) |
| **Mean** | **85.5% (59/69)** | **68.1% (47/69)** | | **92.8% (192/207)** | **87.9% (182/207)** | **73.4% (152/207)** |

The two new checks reproduce the calibration figures recorded above exactly — the projection check
at 2/9 · 0/9 · 0/9 in round 2, the no-stash check at 10/12 · 11/12 · 10/12 — which is the evidence
that v1.3 grades the stored rounds the same way it will grade round 3.

## Round 3 — 2026-09-02, sonnet

Three arms, five runs per cell, 60 runs. `with_skill` is the live v1.2 body, `old_skill` is
`snapshots/skill-v1.1-round-2.md`, so the `with_skill`/`old_skill` column is v1.2's edits — the
`perf_bench.py` driver, the measured-or-marked rule, the stash ban, and two removals — measured on
their own.

### Per eval

| Eval | with_skill | old_skill | without_skill |
|---|---|---|---|
| 0 quadratic-digest | 94% (85/90) | 93% (84/90) | 82% (74/90) |
| 1 static-clean-needs-a-profile | 93% (84/90) | 90% (81/90) | 68% (61/90) |
| 2 low-findings-only-restraint | 97% (68/70) | 99% (69/70) | 66% (46/70) |
| 3 wrong-hypothesis | 98% (93/95) | 93% (88/95) | 82% (78/95) |
| **Mean** | **95.7% (330/345)** | **93.3% (322/345)** | **75.1% (259/345)** |

### Checks that separated the arms

| Check | with_skill | old_skill | without_skill |
|---|---|---|---|
| Every runtime quoted at the scale the user named is marked as a projection | 6/15 | 1/15 | 0/15 |
| Every speed claim has a measured number beside it | 17/20 | 14/20 | 8/20 |
| The run says how it knows the code still returns the same answers | 15/15 | 15/15 | 1/15 |
| The baseline was taken without moving the user's working tree | 20/20 | 17/20 | 20/20 |
| A measurement was actually executed, not just reasoned about | 20/20 | 20/20 | 15/20 |
| The measurement came before the first edit | 10/10 | 10/10 | 7/10 |
| perf_check.py was run before the first edit | 20/20 | 20/20 | 0/20 |
| The diff stays small — at most 15 changed lines across src/ | 5/5 | 5/5 | 1/5 |
| The summary quotes a concrete measured runtime | 5/5 | 5/5 | 3/5 |
| The summary reports a before and an after measurement | 15/15 | 15/15 | 13/15 |
| The bottleneck was identified from a measurement the run took | 4/5 | 5/5 | 1/5 |
| The measurement was taken at a visible input size, stated | 14/15 | 15/15 | 14/15 |
| The run concludes the flagged patterns are not worth changing | 5/5 | 5/5 | 4/5 |
| The summary says this module is not where the time goes | 4/5 | 5/5 | 4/5 |
| The user is left knowing where the time actually goes | 5/5 | 5/5 | 4/5 |
| Every 'why' comment in the target module survives | 20/20 | 20/20 | 19/20 |

### Per-cell spread

Five runs per cell, pass rate per run:

| Eval | with_skill | old_skill | without_skill |
|---|---|---|---|
| 0 | 94, 94, 94, 94, 94 | 89, 94, 94, 94, 94 | 83, 83, 78, 83, 83 |
| 1 | 94, 94, 89, 94, 94 | 89, 89, 94, 83, 94 | 61, 67, 67, 78, 67 |
| 2 | 93, 100, 93, 100, 100 | 100, 100, 100, 100, 93 | 43, 71, 64, 79, 71 |
| 3 | 95, 95, 100, 100, 100 | 89, 89, 95, 89, 100 | 79, 79, 84, 84, 84 |

Per-run standard deviation is 3.2 points `with_skill`, 4.8 `old_skill`, 10.7 `without_skill`. The
skill arms are far tighter than round 2's 24-point worst cell — five runs and a matured rubric
between them — and the baseline is still the loose one.

### Cost

|  | with_skill | old_skill | without_skill |
|---|---|---|---|
| Runs | 20 | 20 | 20 |
| Tokens, mean | 762,860 | 491,879 | 310,973 |
| Wall clock, mean | 204s | 100s | 55s |
| Tool calls, mean | 18.9 | 13.3 | 9.2 |
| Cost | $6.64 | $4.47 | $3.12 |

### Execution metrics

Not scored. `bench_calls` is how the round reads adoption of the v1.2 driver.

| | with_skill | old_skill | without_skill |
|---|---|---|---|
| `bench_calls`, mean (runs > 0) | 5.0 (19/20) | 0 (0/20) | 0 (0/20) |
| `checker_calls`, mean | 1.25 | 1.80 | 0 |
| `measurements`, mean | 5.05 | 2.85 | 1.30 |
| `edits`, mean | 1.25 | 0.80 | 1.10 |
| `stashes` (runs > 0) | 0/20 | 3/20 | 0/20 |

### What the round showed

**The driver was adopted, and that part is not a statistical claim.** 19 of 20 `with_skill` runs
called `perf_bench.py`, at a mean of 5 calls; no run in either other arm called it, because no
other arm can know it exists. Two behaviours move with it and have the same clean causal story:
`stashes` goes to 0/20 where `old_skill` still reaches for a stash in 3 of 20 runs, and
`checker_calls` falls from 1.80 to 1.25 as `--recheck` folds the duplicate call in. The stash ban
and the `--recheck` fold both did what they were written to do.

**The cost prediction was wrong, and wrong in the interesting direction.** Round 2 predicted the
driver would take 10–15% off the token count by collapsing the measurement turns. Tokens instead
rose 59% — 481k to 763k — with tool calls up from 13.4 to 18.9 and wall clock from 80s to 204s. The
mechanism is visible in `measurements`, which went from 2.5 per run to 5.05: the driver did make
each measurement cheaper to write, and runs responded by measuring twice as often — a sweep, a
baseline, a re-check, a projection. Making a step cheap bought more of the step, not less of the
bill. Any future revision aimed at cost has to remove a step the skill *asks for*, not make the
asking easier.

**The projection rule worked, and the check that grades it is broken on `report-repo`.** *"Every
runtime quoted at the scale the user named is marked as a projection"* reads 6/15 `with_skill`
against 1/15 `old_skill` and 0/15 `without_skill`. But the per-eval split is 0/5, 2/5, 4/5 — every
arm scores zero on eval 0, and reading the runs says why. v1.3's premise was that each prompt names
a workload *no run can reach inside its budget*. That is false for `report-repo`: all five
`with_skill` runs swept to 400,000 events and all five `old_skill` runs timed there too, because
400k events is about 7 seconds. Their 400k figures are measurements. The check demanded they be
labelled as projections and failed them for being honest.

Seven of the nine `with_skill` failures measured at or above the scale they quoted. Only two are
genuine: one `ingest` run that swept to 16k and then quoted 400k unmarked, and one `logscan` run
that turned the user's 25-minute figure into "well under a minute". On the two evals where the
premise does hold, the contrast is `with_skill` 6/10 against `old_skill` 1/10 (Fisher p = 0.057) —
a cleaner and stronger result than the headline, with eval 0 contributing nothing but a floor in
both arms.

The irony is worth recording: **v1.2's own driver invalidated the check written to grade it.**
v1.3 was calibrated against rounds 1 and 2, where no run had `perf_bench.py` and none swept to the
named scale, so "quoted at 400k" reliably meant "extrapolated to 400k". Making measurement cheap
broke that equivalence. This is the fourth time this file has recorded a check grading *how* a run
worked rather than *whether* it did, and the first time the skill under test caused it.

**The headline v1.2-over-v1.1 gap is not callable.** 95.7% against 93.3% is +2.1 points per run at
a permutation p of 0.127. None of the individual targeted checks clears significance either — the
projection check at p = 0.080, the no-stash check at p = 0.231, "every speed claim has a measured
number" (17/20 against 14/20) at p = 0.451. Every one of them points the same way, which is worth
something, but round 2 already warned that edits aimed at a 3-point gap need more than this, and
five runs per cell was still not enough. The honest summary is that v1.2 is directionally ahead of
v1.1 on every axis it targeted and proven ahead on none of them, with the exception of the driver
adoption and stash figures, which are not close enough to chance to need a test.

**The skill is worth 21 points over no skill** (95.7% against 75.1%), unchanged from round 2's 19
and round 1's 17 under the same rubric. That gap is not in doubt and has never been the question.
The single widest check remains *"the run says how it knows the code still returns the same
answers"* at 15/15 in both skill arms against 1/15 in the baseline — the v1.1 edit that round 2
credited, holding at a full sweep a round later.

**Restraint held.** `tidy-repo` is 97% `with_skill` against 99% `old_skill`, with the diff-size
check 5/5 and no new module in either arm. The risk this round was that a cheap measuring tool
would tempt a run into benchmarking a module that does not need it; it did not. The 2-point
shortfall is one check on one run and is inside the spread.

### To watch next round

- **Stop asking whether the skill beats nothing.** Three rounds have answered it (17, 19, 21
  points). The baseline arm is now costing a third of the round's budget to re-confirm a settled
  result; consider dropping it to one run per cell as a regression floor and spending the runs on
  the version comparison, which is the question that keeps failing to resolve.
- **The version comparison needs a different instrument, not more runs.** Going from 3 to 5 runs
  per cell moved the p-value on a 2-point gap from uncallable to uncallable. Twenty runs per cell
  would cost roughly $80 a round to resolve 2 points. The alternative the last round already named
  is better: a fifth fixture where the correct answer is *only* an explicitly marked extrapolation,
  so the checks the revisions target are near-binary rather than one item in a denominator of 17.
- **Fix the projection check before round 4 — it is the first thing to do.** Gate it on the
  largest size the run actually measured, and only require a marker when the quoted scale exceeds
  it. That is the check v1.3 dropped as uncomputable ("the largest size measured is one where the
  effect is visible"), and v1.2's driver is what made it computable: 19 of 20 `with_skill` runs pass
  their sizes on a `--sizes` flag, so `swept_sizes` is now reliable where in round 2 it returned
  scratch-path digits. Until this lands, eval 0 contributes a guaranteed zero to every arm and the
  check cannot separate anything there.

- **Watch the token curve if the driver stays.** 763k per run is 2.5x the baseline and the trend
  across rounds is up (388k, 481k, 763k). None of the round's scores depend on the extra
  measurements — the checks they feed were already saturated — so this is spend without a
  corresponding number, which is the definition of a step worth cutting.
- **17 of 30 checks remain identical in all three arms.** Unchanged from round 2, and nothing in
  v1.2 aimed at them. They stay as regression floors, and they did their job: no arm regressed on
  the two prose removals v1.2 made, which is the evidence those removals were safe.

## After round 3 — skill v1.3

Measured in round 4, below. The round-3 body is kept verbatim at
`snapshots/skill-v1.2-round-3.md`, and v1.3's own at `snapshots/skill-v1.3-round-4.md`.

Round 3's failure list was short and lopsided: nine of the fifteen `with_skill` failures were one
check, and seven of those nine were the check misreading a measurement as a projection. Only two
edits below answer a real behaviour; the third is a cut justified by a check that does not separate
the arms.

| Change | What it answers |
|---|---|
| Step 2 gains the branch that was missing: put the user's named size at the top of the sweep and find out whether it finishes, sweeping the small sizes first and falling back to `--project` only when the largest one won't complete | The two genuine projection failures, which are the same mistake from opposite ends — one `ingest` run swept to 16k and quoted 400k unmarked, one `ingest` run charged straight at 400k, hit ~10 minutes per repeat and had to abort and re-plan. The skill only ever described the *too slow* branch, so runs had to invent the other one |
| Step 3 says the `--baseline` call replaces the step-2 sweep rather than adding to it | `measurements` at 5.05 per run against `old_skill`'s 2.85 and the baseline's 1.30, with tokens up 59%. `--baseline` re-times both sides, so a run that sweeps, edits, sweeps and then baselines buys the same numbers twice |
| The growth-slope paragraph is cut from six lines to four | "The measurement was taken at a visible input size, stated" is 14/15 `with_skill`, 15/15 `old_skill`, **14/15 `without_skill`** — the skill arm does not beat no-skill on the check this prose exists to drive. The *"go up an order of magnitude"* sentence is kept: it is the plausible reason runs reach 400k at all, which is behaviour worth having |

The last is a trim rather than a deletion for the reason round 2 recorded about its own two
removals — a check saturated in every arm is evidence the prose was not doing the work, not
evidence that cutting it helps. If "visible input size" regresses in round 4, this is the edit to
suspect.

**Round 4 must fix the projection check before it measures anything.** Gate it on `swept_sizes` and
require a marker only where the quoted scale exceeds the largest size actually measured. Until then
eval 0 contributes a guaranteed zero to every arm, and the two edits above aim at behaviour that
check is currently unable to see. Round 3's stored workspace can be re-graded under the repaired
check for free, which is the cheapest available read on whether these edits were needed at all.

## Rubric v1.4 — the projection check, repaired

Round 3 recorded this as the first thing round 4 had to do, and why: v1.3's premise was that the
scale each prompt names is one *no run can reach inside its budget*, so a duration quoted there is
arithmetic. v1.2's own `perf_bench.py` falsified that. 400k events is about seven seconds, so every
arm swept there and every `report-repo` run in round 3 was failed for quoting an honest
measurement — a guaranteed zero contributed to all three arms.

The gate is `measured_ceiling`, a new execution metric: the largest input size the run
demonstrably ran something at. It reads `perf_bench.py --sizes` and, for the arms that cannot know
that script exists, the scale pattern itself appearing in a measurement call or in a harness file
the run wrote — a hand-rolled `range(400_000)` counts exactly as a swept size does, so the gate
cannot favour an arm. A claim at or below the ceiling is dropped before the marker is looked for.
`logscan-repo` states its scale as a duration rather than a size, so nothing can be compared
against it and the marker stays required there.

This is the repair round 3 named, and it does what it was meant to. It also all but retires the
check on two of the three cases it runs on: measuring at the named scale is now the norm, so
eval 0 and eval 1 sit near a ceiling in every arm, and the separation lives entirely on eval 3.

| Projection check, v1.4 | round 1 | round 2 | round 3 |
|---|---|---|---|
| eval 0 · with / old / without | 1/1 · — · 1/1 | 2/3 · 3/3 · 3/3 | 5/5 · 4/5 · 5/5 |
| eval 1 · with / old / without | 1/1 · — · 1/1 | 2/3 · 2/3 · 3/3 | 3/5 · 4/5 · 5/5 |
| eval 3 · with / old / without | 0/1 · — · 0/1 | 1/3 · 0/3 · 0/3 | 4/5 · 1/5 · 0/5 |
| **all** | 2/3 · — · 2/3 | 5/9 · 5/9 · 6/9 | 12/15 · 9/15 · 10/15 |

What is left is honest and narrow: on `logscan`, where the user's scale is a 25-minute production
run that no eval run can reproduce, v1.2 marks its extrapolations 4 times in 5 against v1.1's 1
and the baseline's 0. Everywhere else the right answer turned out to be *measure there instead*,
which the skill also produced, and which no marker check can credit.

One imprecision is knowingly left in. A run that measures the *fixed* code at 400k and then says
the old code "would have taken hours" is quoting an unmeasured duration at a measured scale, and
the gate drops the whole claim. Separating the two sides of a before/after at one scale is past
what a window regex can do; the judgement check about measured numbers is what covers it.

A second one was found by round 4 and fixed in v1.5 below: the ceiling is a single number, and
`ingest`'s prompt names a workload with two dimensions (180k customers, 400k rows). A sweep that
reaches the full workload records 180,000, so a claim quoting "180k/400k" read as above the
ceiling and was failed for missing a marker it did not need. Five of round 4's eleven failures of
this check were that, spread evenly across both arms.

## Rounds 1 to 3 restated — rubric v1.4

Re-graded from the stored workspaces with `grade.py --reuse-judgement`, which recomputes the
mechanical half and reads the judgement results back off disk, so the repaired check moves and
nothing else does. Each run keeps its previous grading beside it as `grading-prev-rubric.json`
(round 3 additionally as `grading-v1.3-rubric.json`).

| Eval | R1 with | R1 without | | R2 with | R2 old | R2 without | | R3 with | R3 old | R3 without |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 quadratic-digest | 89% | 83% | | 93% | 91% | 87% | | 100% | 98% | 88% |
| 1 static-clean-needs-a-profile | 89% | 72% | | 96% | 93% | 81% | | 94% | 94% | 73% |
| 2 low-findings-only-restraint | 79% | 43% | | 100% | 93% | 50% | | 97% | 99% | 66% |
| 3 wrong-hypothesis | 95% | 79% | | 89% | 86% | 81% | | 98% | 93% | 82% |
| **Mean** | **88.4%** | **71.0%** | | **94.2%** | **90.3%** | **76.3%** | | **97.4%** | **95.7%** | **78.0%** |

The skill-versus-nothing gap under v1.4 is 17.4, 17.9 and 19.4 points across the three rounds —
the same settled result v1.3 reported, one to two points narrower now that the baseline is no
longer failed for measuring at scale.

## Round 4 — 2026-09-02, sonnet

Three arms, 44 runs: `with_skill` (the live v1.3 body) and `old_skill`
(`snapshots/skill-v1.2-round-3.md`) at five runs per cell, `without_skill` cut to **one** run per
cell. Round 3 recorded the reason — three rounds have answered whether the skill beats nothing, and
the baseline was costing a third of the budget to re-confirm it — so it stays as a regression floor
and the runs went to the version comparison. Graded under rubric v1.4.

### Per eval

| Eval | with_skill | old_skill | without_skill |
|---|---|---|---|
| 0 quadratic-digest | 99% (89/90) | 98% (88/90) | 89% (16/18) |
| 1 static-clean-needs-a-profile | 94% (85/90) | 93% (84/90) | 78% (14/18) |
| 2 low-findings-only-restraint | 99% (69/70) | 100% (70/70) | 43% (6/14) |
| 3 wrong-hypothesis | 96% (91/95) | 95% (90/95) | 84% (16/19) |
| **Mean** | **96.8% (334/345)** | **96.2% (332/345)** | **75.4% (52/69)** |

### Checks that separated the arms

| Check | with_skill | old_skill | without_skill |
|---|---|---|---|
| perf_check.py was run before the first edit | 20/20 | 20/20 | 0/4 |
| The run says how it knows the code still returns the same answers | 15/15 | 14/15 | 1/3 |
| Every speed claim has a measured number beside it | 18/20 | 16/20 | 2/4 |
| A measurement was actually executed, not just reasoned about | 20/20 | 20/20 | 3/4 |
| The measurement came before the first edit | 10/10 | 10/10 | 1/2 |
| Every runtime quoted at the scale the user named is marked as a projection | 10/15 | 9/15 | 2/3 |
| The baseline was taken without moving the user's working tree | 20/20 | 19/20 | 4/4 |
| The diff stays small — at most 15 changed lines across src/ | 5/5 | 5/5 | 0/1 |
| The summary quotes a concrete measured runtime | 5/5 | 5/5 | 0/1 |
| The summary says this module is not where the time goes | 5/5 | 5/5 | 0/1 |
| The run concludes the flagged patterns are not worth changing | 5/5 | 5/5 | 0/1 |
| The user is left knowing where the time actually goes | 5/5 | 5/5 | 0/1 |
| The run tells the user their regex hypothesis was wrong, with a number | 3/5 | 5/5 | 1/1 |
| The bottleneck was identified from a measurement the run took | 3/5 | 4/5 | 0/1 |

### Per-cell spread

| Eval | with_skill | old_skill | without_skill |
|---|---|---|---|
| 0 | 94, 100, 100, 100, 100 | 94, 94, 100, 100, 100 | 89 |
| 1 | 100, 94, 94, 94, 89 | 100, 94, 100, 83, 89 | 78 |
| 2 | 100, 100, 93, 100, 100 | 100, 100, 100, 100, 100 | 43 |
| 3 | 89, 95, 100, 95, 100 | 89, 95, 95, 95, 100 | 84 |

Per-run mean and standard deviation: `with_skill` 96.9% ± 3.8, `old_skill` 96.5% ± 4.8,
`without_skill` 73.4% ± 20.9 (n=4). Permuting per-run pass rates within each eval (20,000
resamples): `with_skill` against `old_skill` is +0.5 points at p = 0.779; each skill arm against
the baseline is +23 points at p = 0.001.

### Cost

|  | with_skill | old_skill | without_skill |
|---|---|---|---|
| Runs | 20 | 20 | 4 |
| Tokens, mean | 757,282 | 749,602 | 288,575 |
| Wall clock, mean | 168s | 168s | 52s |
| Tool calls, mean | 17.4 | 18.6 | 8.0 |
| Cost | $7.05 | $6.10 | $0.65 |

### Execution metrics

Not scored. Both skill arms carry `perf_bench.py` this round — v1.3 and v1.2 both ship it — so
`bench_calls` is no longer an arm difference, and `measured_ceiling` is the metric to read instead.

| | with_skill | old_skill | without_skill |
|---|---|---|---|
| `measured_ceiling`, mean | 389,900 | 182,920 | 200,000 |
| `bench_calls`, mean (runs > 0) | 4.9 (19/20) | 4.7 (19/20) | 0 (0/4) |
| `checker_calls`, mean | 1.15 | 1.35 | 0 |
| `measurements`, mean | 5.15 | 5.05 | 1.0 |
| `edits`, mean | 1.1 | 1.4 | 1.25 |
| `stashes` (runs > 0) | 0/20 | 1/20 | 0/4 |

### What the round showed

**v1.3 and v1.2 are the same skill as far as this rubric can tell.** 96.9% against 96.5% per run,
a gap of +0.5 points at a permutation p of 0.779 — further from callable than round 3's +1.5 at
p = 0.208, off the same 20 runs per skill arm. The round also puts a number on the
noise floor for the first time: **v1.2 was measured twice**, as round 3's `with_skill` (97.4%) and
round 4's `old_skill` (96.2%), a 1.2-point drift for an identical body between rounds. Any gap
under about a point is weather.

**The step-2 branch produced the behaviour it was written for, in one run out of five.** v1.3 tells
a run to put the user's named size at the top of the sweep and find out whether it finishes. One
`logscan` run generated a 4.2-million-line day of logs and timed the fix there — a measurement of
the exact workload the user described, which no run in any previous round has produced.
`measured_ceiling` reads 389,900 against 182,920 on the strength of it. That single run *is* the
difference: strip it and the two arms' ceilings are level — v1.3 higher on `tidy` (58k against
14k), lower on `ingest` (224k against 268k), the same on `logscan`. The instruction works when a
run takes it; four in five did not.

**The edit aimed at cost did nothing.** v1.3 says the `--baseline` call replaces the step-2 sweep
rather than adding to it, against round 3's `measurements` of 5.05 per run and its 59% token rise.
Round 4: `measurements` 5.15 against 5.05, tokens 757k against 750k, wall clock identical at 168s.
The prose did not remove the step. Round 3 concluded that making a step cheaper buys more of the
step; round 4 adds that *telling a run not to take a step it has already been told to take* does
not remove it either. What is left is cutting the instruction itself.

**The trim was safe.** v1.3 cut the growth-slope paragraph from six lines to four, and round 3
flagged "the measurement was taken at a visible input size, stated" as the check to watch if that
was a mistake. It reads 15/15 in both skill arms. Nothing else moved with it.

**Restraint and the floors held.** `tidy-repo` is 99% against 100% — one check on one run — with
the diff-size check 5/5 and no new module in either arm. `perf_check.py` before the first edit is
20/20 in both skill arms and 0/4 in the baseline, the hidden behaviour suites are 15/15 everywhere,
and `stashes` is 0/20 for v1.3 against 1/20 for v1.2.

**The projection check has stopped separating the version arms, and half of what it still fails
is the instrument.** 10/15 against 9/15 under the repaired v1.4 gate. Both bodies push runs to
measure at the named scale now, so the marker is rarely the right answer any more. Reading the
eleven failures says the rest is two different things:

- **`ingest` (3 `with_skill`, 2 `old_skill`) is an artifact of a two-dimensional scale.** The
  prompt names *180k customers and 400k rows*; `measured_ceiling` is one number, and a
  `perf_bench --sizes … 180000` sweep records 180,000. Every one of these five runs measured the
  fixed importer on the full 180k/400k workload and said "measured" beside the figure — the check
  reads the `400k` token, finds it above a 180,000 ceiling, and demands a marker for a measurement.
  It hits both arms in the same proportion, so the round's comparison is unaffected, but it is the
  same class of bug as the one v1.4 fixed and it is the check's biggest single source of failures.
  Repaired in rubric v1.5 below, where this round is restated.
- **`logscan` (2 and 4) is the real residue**, and the only place the check can still move. Its
  scale is a duration nothing can convert into a size, so every claim there needs the marker;
  v1.3's failures are one run that quoted the 25 minutes with no marker at all and one that
  converted it into "roughly 4M lines" as bare arithmetic — the same run that then went and
  measured there.

**The baseline arm at one run per cell was the right trade.** It reproduced the settled result —
23 points behind both skill arms, p = 0.001 — for $0.65 of the round's $13.80, and its per-run
spread (± 20.9) is a reminder of why the comparison that matters is the one between skill versions.

### To watch next round

- **Stop revising prose against a 1-point noise floor.** Two rounds have now failed to separate two
  skill versions at five runs per cell, and this round shows the same body scoring 1.2 points apart
  between rounds. Either the next edit is large enough to move a check outright — the way the
  driver moved `bench_calls` and the stash ban moved `stashes` — or it is not worth a round.
- **The fifth fixture is still the outstanding instrument.** Round 3 named it and round 4 confirms
  the need from the other direction: with the projection check repaired, only one of four cases can
  express the behaviour the last two revisions targeted. A case whose correct answer is *only* an
  explicitly marked extrapolation — a workload nothing can generate — would make that near-binary
  instead of one item in a denominator of 17.
- **Cost is now the open question, not quality.** Both skill arms sit at ~750k tokens and 5
  measurements per run against the baseline's 289k and 1.0, and every check those measurements feed
  is saturated. Two rounds of prose aimed at trimming this have failed. The next attempt should
  delete a step rather than qualify one — the obvious candidate being the separate `--baseline`
  re-time, which duplicates the sweep it is meant to replace.
- **`measured_ceiling` is the metric to watch, not `bench_calls`.** Both bodies ship the driver
  now, so adoption is no longer an arm difference. What still varies is whether a run reaches the
  user's own scale, and that is one run in five.
- **Repair the ceiling for `ingest` before round 5, as v1.4 repaired the check itself.** A scalar
  ceiling cannot express *180k customers × 400k rows*: give `ingest`'s spec the smaller named
  dimension as the size that counts as having reached the workload, so a sweep to 180k credits a
  claim at 180k/400k, while round 3's genuine failure — a sweep to 16k quoting 400k — still fails.
  Then re-grade rounds 1 to 4 with `--reuse-judgement`, which is what makes the five runs above
  readable as behaviour rather than noise.

## After round 4 — skill unchanged at v1.3

No edit. Round 4's own finding is that this suite cannot resolve a prose change of the size the
last two revisions made — 0.5 points at p = 0.779, against a 1.2-point drift measured on an
identical body between rounds — so another revision graded against the same four cases would
produce another uncallable number. The next change to this skill should be one that moves a check
outright, or should wait for the fifth fixture.

## Rubric v1.5 — the two-dimensional scale

Round 4's first *to watch* item, done before anything else, exactly as v1.4 was for round 3.

`measured_ceiling` is one number and `ingest`'s prompt names two: *180k customers and 400k rows*.
One sweep generates both, and only the number on the `--sizes` flag is recorded, so a run that
measured the whole workload recorded 180,000 — and its honest "at 180k/400k, 0.74s (measured)" read
as a claim 220,000 above the ceiling and was failed for missing a marker it did not need. Five of
round 4's eleven failures of this check were that, evenly split across the two skill arms.

`Spec` gains `workload_size`: where a prompt names the workload in more than one dimension, the
smaller of them is what counts as having run it. `ingest` carries 180,000; nothing else carries
anything, because nothing else names two numbers. A claim is credited when the ceiling reaches
`min(quoted, workload_size)`.

The repair keeps every genuine failure. Round 3's `ingest` run that swept to 16k and quoted 400k
still fails, because 16,000 is under the floor as well as under the claim; so does round 3's
`old_skill` run that never measured at all. What it drops is the five runs that measured the
workload and said so.

What is left of this check is `logscan` and nothing else. Evals 0 and 1 are now saturated in every
arm across every round — measuring at the named scale is what the skill produces, and the marker is
the wrong answer there. Eval 3's scale is a duration nothing can convert into a size, so the marker
is always required, and that is where the arms separate: `with_skill` 4/5 · 3/5 in rounds 3 and 4
against `old_skill` 1/5 · 1/5 and a baseline of 0.

### Rounds 1 to 4 restated — rubric v1.5

Re-graded from the stored workspaces with `--reuse-judgement`; the v1.4 gradings are kept beside
each run as `grading-v1.4-rubric.json`.

| Eval | R1 with | R1 without | | R2 with | R2 old | R2 without | | R3 with | R3 old | R3 without | | R4 with | R4 old | R4 without |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 quadratic-digest | 89% | 83% | | 93% | 91% | 87% | | 100% | 98% | 88% | | 99% | 98% | 89% |
| 1 static-clean-needs-a-profile | 89% | 72% | | 96% | 93% | 81% | | 96% | 94% | 73% | | 98% | 96% | 78% |
| 2 low-findings-only-restraint | 79% | 43% | | 100% | 93% | 50% | | 97% | 99% | 66% | | 99% | 100% | 43% |
| 3 wrong-hypothesis | 95% | 79% | | 89% | 86% | 81% | | 98% | 93% | 82% | | 96% | 95% | 84% |
| **Mean** | **88.4%** | **71.0%** | | **94.2%** | **90.3%** | **76.3%** | | **97.7%** | **95.7%** | **78.0%** | | **97.7%** | **96.8%** | **75.4%** |

Round 4's conclusion is unchanged and slightly sharper: v1.3 against v1.2 is 97.8% against 97.0%
per run, +0.7 points at a permutation p of 0.622, against a between-round drift of 0.9 points on
the identical v1.2 body (round 3's `with_skill` 97.7%, round 4's `old_skill` 96.8%). The projection
check reads 13/15 · 11/15 in round 4 and 13/15 · 9/15 in round 3, all of the difference on
`logscan`. Skill against no skill is 24.3 points at p = 0.001.

## After rubric v1.5 — skill v1.4

Nothing here has been measured yet; this records what changed and what round 5 has to settle. The
round-4 body is kept verbatim at `snapshots/skill-v1.3-round-4.md`.

Round 4 left cost as the open question and named the shape of the answer: *delete a step rather
than qualify one.* v1.3 qualified — a paragraph telling runs the `--baseline` call replaced the
step-2 sweep — and `measurements` did not move (5.15 against 5.05). Reading the tool alongside the
prose says why the qualifier had no chance: `perf_bench.py`'s `--help` epilog led with
`--sizes … # before you edit` and `--baseline … # after you edit`, and SKILL.md sends every run
there for the worked example. The body argued against a two-sweep workflow while the tool it cites
prescribed one.

| Change | What it answers |
|---|---|
| The step-2 `--sizes` code block is **deleted**. The bench module and the growth-slope prose move to step 3, so the whole skill now shows one `perf_bench.py` invocation instead of two near-identical ones 25 lines apart | `measurements` 5.15/run and `bench_calls` 4.9/run against a baseline arm's 1.0. Two rounds of prose aimed at this moved neither |
| The `--help` epilog is reordered: `--baseline` leads, and the bare sweep is annotated *growth curve, nothing to compare* rather than *before you edit* | The same duplication, at the other end of it. Round 4 could not have separated the epilog from the prose; nothing had changed it |
| v1.3's "this call re-times both sides, so it replaces the step-2 sweep" paragraph is cut, replaced by one clause on the single call that also names the no-edit path: drop `--baseline` and the same call gives the growth curve alone | The qualifier that lost, and `tidy-repo`'s route to a measured number without an edit, which the deleted block used to carry |
| The two paragraphs on the named scale being too slow to sweep — one in step 2, one in step 3 — merge into one, beside the slope reading | They described the same situation from opposite sides of a step boundary. The step-2 half is the instruction round 4 found firing in 1 run of 5 |

**What round 5 has to settle.** This is a cost edit, not a quality one, and it is deliberately the
kind round 4 said was worth a round: it removes a step rather than discouraging one, so it moves
metrics that are read as counts and not as p-values. `measurements` and `bench_calls` are the
primary reads, tokens and wall clock the secondary. The quality checks it could plausibly cost are
named here so the round can be read against them rather than after the fact:

- **`tidy-repo`'s measured number** — "the summary quotes a concrete measured runtime", 5/5 in both
  skill arms. Its run measures without editing, and the block that showed it how is the one
  deleted. The replacement is a clause in step 3, which is a worse place for it.
- **"The measurement came before the first edit"** — 10/10, carried by `ingest` and `logscan`.
  Step 2's pre-edit instrument is the profiler and is untouched, so this should hold; if it drops,
  the deletion took the pre-edit measurement with it and the block comes back.
- **`measured_ceiling`** — the sweep-sizing paragraph survives intact and moves next to the command
  it applies to. Round 4 measured it firing in 1 run of 5; if the move does nothing, that
  instruction needs to become a flag rather than a paragraph.

If `measurements` does not fall, the remaining candidate is deleting `perf_bench.py` outright, as a
round with `bench_calls` driven to zero by construction.
