# Eval benchmark — `python-performance`

A dated record of what this skill scored, so a future round can be compared against it rather than
read in isolation. Append rounds; don't rewrite them. The harness that produces these numbers lives
beside this file — read [README.md](README.md) before re-measuring.

Round 1 is two arms (`with_skill`, `without_skill`) at one run per cell; round 2 adds `old_skill`
on a snapshot and repeats every cell three times. At one run per cell, treat a 20% swing in tokens
or time as noise — and see round 2's per-cell spread for how wide that band really is once you can
see it. The mechanical checks are the durable signal — files on disk, their
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
| v1.2 | v1.1 with two mechanical checks repaired — both were grading *how* a run did something rather than whether it did it. No statement added or retired | During round 2 |
| v1.3 | v1.2 plus two shared mechanical statements — the working tree was not moved to get a baseline, and every runtime quoted at the user's scale is marked as a projection — and one widening: `DURATION` now reads `25-minute` as a duration | For round 3 |

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

## Round 3 — planned, not yet run

**The question.** Does skill v1.2 beat v1.1 — and if it does, is it the benchmark driver, the
measured-or-marked rule, or neither?

**Shape.** Three arms, five runs per cell: `with_skill` on the live v1.2 body, `old_skill` on
`snapshots/skill-v1.1-round-2.md`, `without_skill` on no skill. 4 evals × 3 arms × 5 runs = **60
runs**, about $16 at round 2's rate. Five rather than three because round 2's per-cell spread ran
to 24 points, and v1.2's edits are aimed at a gap around 3 — three runs could not have called it,
and this is the round where that matters.

```bash
WS=~/.cache/claude-evals/python-performance
PY=.venv/bin/python

$PY evals/python-performance/prepare.py "$WS" --iteration 3 --runs 5 \
    --arms with_skill,old_skill,without_skill

find "$WS/iteration-3" -name eval_metadata.json -printf '%h\n' | grep -v /old_skill/ \
  | xargs -P 8 -L1 $PY evals/python-performance/run_case.py --model sonnet

find "$WS/iteration-3" -path '*/old_skill/*' -name eval_metadata.json -printf '%h\n' \
  | xargs -P 8 -L1 $PY evals/python-performance/run_case.py --model sonnet \
      --skill evals/python-performance/snapshots/skill-v1.1-round-2.md

find "$WS/iteration-3" -name timing.json -printf '%h\n' \
  | xargs -P 4 -L1 $PY evals/python-performance/grade.py
$PY evals/shared/aggregate.py "$WS/iteration-3"
```

Re-grade rounds 1 and 2 under v1.3 first, or their totals will not line up:

```bash
for i in 1 2; do
  find "$WS/iteration-$i" -name timing.json -printf '%h\n' \
    | xargs -P 4 -L1 $PY evals/python-performance/grade.py
done
```

**What would count as an answer.**

- *The projection rule worked* — "every runtime quoted at the scale the user named is marked"
  climbs well clear of round 2's 2/9 in the `with_skill` arm while `old_skill` stays near 0/9. This
  is the check with the most headroom and the clearest causal story, so it is the one to read
  first.
- *The driver was adopted* — `bench_calls` is non-zero in most `with_skill` runs. If it is near
  zero the prose introducing it is the problem, not the script, and no other `with_skill` number in
  the round can be attributed to v1.2's tooling.
- *The driver paid for itself* — `with_skill` tokens and `tool_calls` fall against round 2's 481k
  and 13.4, and `checker_calls` falls towards 1. The predicted saving was 10–15%, which five runs
  per cell can just about resolve; anything smaller is not callable and should not be claimed.
- *Restraint held* — `tidy-repo` stays near 97%. v1.2 adds a tool that makes measuring cheap, and
  the risk is that a run reaches for it on a module that does not need it. Watch the diff-size and
  new-module checks there, not the mean.

**What this round still cannot settle.** 17 of 30 checks were already identical in all three arms
at v1.1, and nothing in v1.2 aims at them; they stay as regression floors. If the two live checks
above also saturate, round 4 needs a fifth fixture rather than a fifth rubric revision — the
obvious shape being a repo whose real workload genuinely cannot be run inside the budget, so the
only correct answer is an explicitly marked extrapolation, and a run that measures at a tractable
size and says so plainly is the one that scores.
