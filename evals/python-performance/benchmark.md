# Eval benchmark — `python-performance`

A dated record of what this skill scored, so a future round can be compared against it rather than
read in isolation. Append rounds; don't rewrite them. The harness that produces these numbers lives
beside this file — read [README.md](README.md) before re-measuring.

Round 1 is two arms (`with_skill`, `without_skill`) at one run per cell; round 2 adds `old_skill`
on a snapshot and repeats every cell three times; round 3 keeps three arms at five runs per cell.
At one run per cell, treat a 20% swing in tokens or time as noise — and see round 2's and round 3's
per-cell spread for how wide that band really is once you can see it. Five runs was still not enough
to call a 2-point difference between two skill versions; see round 3 on what to do about that. The
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

Nothing here has been measured yet. The round-3 body is kept verbatim at
`snapshots/skill-v1.2-round-3.md`.

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
