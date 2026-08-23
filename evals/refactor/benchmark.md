# Eval benchmark — `refactor`

A dated record of what this skill scored, so a future round can be compared against it rather than
read in isolation. Append rounds; don't rewrite them. The harness that produces these numbers lives
beside this file — read [README.md](README.md) before re-measuring.

Two arms each (`with_skill`, `without_skill`), one run per cell except round 3's eval 5, which ran
three per arm. Rounds 1 and 2 ran three evals; rubric v3 takes it to six. One run per cell means
the token and time figures are single observations, not distributions: treat a 20% swing as noise.
Pass rates are the durable signal because every check is mechanical — files on disk, their AST,
and one run of the fixture's own test suite (plus, in `digest-repo`, one the fixture does not
ship).

Rounds 1 and 2 kept no workspace and cannot be re-graded. From round 3 the workspace is kept
outside the repo — `~/.cache/claude-evals/refactor/iteration-<n>` for the Sonnet rounds and
`~/.cache/claude-evals/refactor-haiku/iteration-<n>` for the controls — so a later rubric can
re-score them.

## Rubric versions

| Version | Assertions | Introduced |
|---|---|---|
| v1 | 8 shared + 5 (`pricing`), 5 (`toolkit`), 4 (`ledger`) | Round 1 |
| v2 | 10 shared + the same per-fixture sets | Round 2, applied retroactively to round 1 |
| v3 | v2 unchanged, plus three cases: 15 (`inventory`), 15 (`digest`), 12 (`resample`) | Round 3 |
| v3.1 | v3 unchanged; `LEFT_ALONE` widened after it false-negatived twice | After round 3 |

v1 saturated on first contact — 100% against 92%, with the entire gap resting on one check — so it
measured almost nothing. v2 keeps all thirteen v1 checks as a regression floor and adds two that
read `outputs/tool-calls.txt` rather than the repo: **verification waste** (a tool the project does
not configure, invoked more than once) and **incrementality** (mutation→verify cycles, with runs of
fewer than two mutations passing outright so `toolkit-repo`'s correct single-edit answer is not
punished).

Round 1's v1 gradings are preserved as `grading-v1.json` beside each run. Under v2 round 1 becomes
**93.2% with the skill against 86.4% without**.

v3 adds no shared check and edits none, because rounds 1 and 2 kept no stored workspaces — a
shared check added now could never be computed for them, and the cross-round comparison that
`with_skill`'s 44/44 has to be read against would break. Everything new is per-fixture and lives on
the three new fixtures, so rounds 1 and 2 remain gradable exactly as recorded. See
[round-3-plan.md](round-3-plan.md).

**v3.1 adds and retires nothing** — it widens one proxy regex, `LEFT_ALONE`, which was failing
summaries that plainly did the behaviour it grades ("left everything else alone" went unmatched
because the object of "left" was a phrase). Widening a regex can only turn a fail into a pass, so
the un-re-gradable rounds stay comparable: round 1 passed this check in both arms, and its single
per-cell failure is recorded as assertion 8 throughout. Round 2's record does not break its four
baseline failures down, so if one of them was this check its recorded 90.9% is a hair low under
v3.1. Round 3's stored runs are re-graded below, with the v3 gradings kept beside them as
`grading-v3.json`.

**Round 1 cannot answer the verification-waste check.** `_tool_summary` only began capturing Bash
commands after that round, so round 1 records a bare `Bash` for every shell call. Those runs fail
the check with `not computable — predates Bash command capture`, which keeps the denominator
honest instead of quietly shortening the rubric. Round 1 still answers the incrementality check,
because tool *names* are enough for it.

## Round 1 — 2026-08-23

Skill at commit `ef4d331`, unedited. Model under test: `sonnet`. Runs driven by `run_case.py`
under `--safe-mode` with `--permission-mode acceptEdits`.

| Eval | Fixture | with_skill | without_skill |
|---|---|---|---|
| 0 pricing-accumulated-complexity | `pricing-repo` | 100% (13/13) | 92% (12/13) |
| 1 already-clean-restraint | `toolkit-repo` | 100% (13/13) | 92% (12/13) |
| 2 post-green-scope | `ledger-repo` | 100% (12/12) | 92% (11/12) |
| **Mean** | | **100%** | **92.1%** |

| Cost | with_skill | without_skill |
|---|---|---|
| Tokens, mean | 690,291 | 261,939 |
| Wall clock, mean | 97s | 42s |
| Tool calls, mean | 18 | 9 |
| Round cost | $1.22 | $0.66 |

### The rubric saturated on first contact

Both arms passed 37 of the 38 assertion instances. **Every failure in the round was the same
check** — assertion 8, "the summary reports added and deleted line counts", which the baseline
missed 3/3 and the skill arm passed 3/3. Nothing else separated them.

That is the v1 rubric measuring almost nothing, in the same way `create-agents-for-repo`'s v1 did.
The scores are real, but a 7.9pp gap resting on one check is a rubric finding, not a skill finding.

### What the arms actually did

Diffs, measured against the fixtures:

| Eval | with_skill | without_skill |
|---|---|---|
| 0 pricing | +72 / −92 | +68 / −87 |
| 1 toolkit | +1 / −1 | +1 / −1 |
| 2 ledger | +35 / −47 | +38 / −46 |

On `toolkit-repo` both arms made **exactly the intended one-line change** — `title_words()` calling
`collapse_whitespace()` instead of repeating it — and both said in prose that the rest of the
package was already clean. The restraint case did not discriminate at all.

On `ledger-repo` the baseline volunteered, unprompted: *"Left `posting.py` and `export.py`
untouched — both are marked frozen/stable and out of scope for this refactor."* It also preserved
the tie-break comment and said why. That is the skill's Principle 5 and its why-comment rule,
performed by a run that had never seen either.

The honest reading: **on Sonnet, against these fixtures, the skill's measurable contribution in
round 1 is the diffstat habit.** The behaviours the other twelve checks grade are ones the model
already had. The skill still bought them at 2.6× the tokens and 2.3× the wall clock.

### Why the fixtures under-discriminate — the thing to fix first

`ledger-repo`'s `CLAUDE.md` gives the answer away. It labels `posting.py` *"Stable since 2021.
Every change here needs a finance sign-off"* and `export.py` *"Frozen"*. That fixture exists to test
whether a run infers scope from `git log`; instead a run can read scope straight off the prose, and
the baseline did. The two-commit history `prepare.py` builds was never load-bearing.

`pricing-repo` leaks less but still leaks: the prompt names `pricing.py`, so leaving
`legacy_invoice.py` alone needs no judgement.

## Haiku control — 2026-08-23

Not a round: the same three evals and both arms on the **unedited** skill, with
`--model claude-haiku-4-5-20251001` instead of Sonnet, graded under v2. Its pass rates are not
comparable to the Sonnet rounds on the same axis — it exists to answer one question before the
round-2 edits, namely whether the redundant prose is dead weight or scaffolding a weaker model
leans on. The pre-committed rule was: gap ≥ 15pp means cut conservatively.

| Eval | with_skill | without_skill |
|---|---|---|
| 0 pricing-accumulated-complexity | 87% (13/15) | 87% (13/15) |
| 1 already-clean-restraint | 87% (13/15) | 87% (13/15) |
| 2 post-green-scope | 79% (11/14) | 79% (11/14) |
| **Mean** | **84.1%** (37/44) | **84.1%** (37/44) |

**Gap: +0.0pp**, against Sonnet's +6.8pp under the same rubric. But the zero is a cancellation, not
an absence — the arms differ on four individual checks, in both directions:

| Check | Won by |
|---|---|
| Summary reports added and deleted line counts | with_skill (2 of 3 evals) |
| Changes applied incrementally | with_skill (1 of 3) |
| **No unconfigured tool invoked more than once** | **without_skill (3 of 3)** |

Every `with_skill` run invoked `ruff` two or three times against fixtures that configure neither
ruff nor pyright. **The skill's Verification section hands back exactly what its other instructions
earn.** That is direct causal evidence for change 1, which round 1 could only infer from token
counts — and it cost 2.0× the baseline's tokens to produce the same net score.

| Cost | with_skill | without_skill |
|---|---|---|
| Tokens, mean | 888,721 | 442,888 |
| Wall clock, mean | 89s | 71s |
| Tool calls, mean | 26 | 15 |
| Round cost | $0.62 | $0.38 |

### What round 2 should add

Per [eval-approach.md](../eval-approach.md), keep all thirteen v1 checks as a regression floor and
add sharper ones beside them. Add cases rather than editing the three fixtures, which would make
this round incomparable:

- **A fourth case whose scope signal is *only* git history** — a repo whose `CLAUDE.md` says
  nothing about which modules are frozen, and where the ugly out-of-scope module is more tempting
  than the in-scope one. This is the check `ledger-repo` was supposed to be.
- **A case where the tests are weak**, so "preserve behaviour exactly" cannot be discharged by
  running pytest. Both arms leaned on green tests as their whole verification story; the skill's
  Chesterton's Fence step is what should cover the gap, and nothing here measures it.
- **A case where the correct answer is "don't"** — code under a rewrite, or performance-critical
  code where the simpler form is slower. The "When NOT to use" section of the skill is entirely
  ungraded today.
- **Incrementality**, which no current check reaches but which the skill demonstrably induces.
  Counting mutation→verify cycles from `tool-calls.txt`:

  | Eval | with_skill | without_skill |
  |---|---|---|
  | 0 pricing | 3 edits / 2 test runs | 1 / 1 |
  | 1 toolkit | 1 / 1 | 1 / 1 |
  | 2 ledger | 3 edits / 3 test runs | 1 / 1 |

  On both cases with real work the skill arm applied changes one at a time and ran the suite
  between them, exactly as Step 3 asks; the baseline wrote the file once and tested at the end.
  This is the clearest behavioural difference in the round and nothing in v1 grades it.

## Round 2 — 2026-08-23

Skill after the three round-1 edits: the hardcoded Verification commands replaced by a discovery
order, the Common Rationalizations / Red Flags / Python-specific sections deleted with their two
unique lines folded into Principles 1 and 2, and the diffstat instruction moved to the head of
Step 4. `SKILL.md` went from 14,096 to 11,142 bytes, a **20% cut** (~740 tokens off every turn).
Model pinned to `claude-sonnet-5` rather than the `sonnet` alias.

| Eval | with_skill | without_skill |
|---|---|---|
| 0 pricing-accumulated-complexity | 100% (15/15) | 87% (13/15) |
| 1 already-clean-restraint | 100% (15/15) | 93% (14/15) |
| 2 post-green-scope | 100% (14/14) | 93% (13/14) |
| **Mean** | **100%** (44/44) | **90.9%** (40/44) |

### The cross-round comparison holds

Round 2 used two arms compared against round 1, which risks model drift between rounds. It did not
happen. Scoring **only the thirteen v1 checks**, so the not-computable artifact cannot distort it:

| | Round 1 | Round 2 |
|---|---|---|
| with_skill, v1 checks only | 100.0% (38/38) | 100.0% (38/38) |
| without_skill, v1 checks only | 92.1% (35/38) | 92.1% (35/38) |

The baseline is identical to the check. The apparent +4.5pp baseline improvement on the full v2
rubric is entirely the verification-waste check becoming computable, exactly as the round-1 note
predicted — not the model moving.

### Did the changes work?

**Change 1 — yes, and it is the round's clearest result.** The verification-waste check goes
`0/3 not computable` (round 1) and `0/3 pass` on the unedited skill under the Haiku control, to
**3/3 pass** in round 2. No run invoked an unconfigured tool more than once. Within-round token
ratio, which is immune to the run-to-run variance below, fell from **2.6× the baseline to 1.6×**.

**Change 2 — safe.** Every v1 check held at 100% for `with_skill`. Nothing the cut removed was
load-bearing.

**Change 3 — held.** The diffstat check stayed 3/3.

### Cost, and why not to read much into it

| | Round 1 | Round 2 |
|---|---|---|
| with_skill, mean tokens | 690,291 | 583,559 (−15%) |
| without_skill, mean tokens | 261,939 | 355,882 (+36%) |
| with_skill, mean tool calls | 18 | 15 |

The baseline burned 36% more tokens for an identical pass rate, which is the clearest possible
demonstration that absolute token counts at one run per cell are noise. `eval-0`'s skill arm rose
46% while `eval-2`'s fell 62%. Treat the −15% mean as directionally encouraging and nothing more;
the ratio and the waste check are the load-bearing numbers.

### What is still unmeasured

The three round-1 recommendations for new *cases* all stand, and matter more now that the skill
arm is at ceiling on every existing check: a scope case whose only signal is git history, a case
whose tests are too weak to discharge "preserve behaviour exactly", and a case where the correct
answer is "don't". `with_skill` at 44/44 means this rubric has no headroom left to detect the next
improvement.

## Round 3 — 2026-08-24

Skill after the Verification-checklist cut (`ee0fb13`), 11,142 → 10,855 bytes. Six evals under
rubric v3, `--model claude-sonnet-5`, one run per cell except eval 5, which ran three per arm
because decline-or-act is binary and one observation of a coin says very little. **The workspace is
kept** at `~/.cache/claude-evals/refactor/iteration-3`, which rounds 1 and 2 were not — a later
rubric can re-grade this round.

| Eval | with_skill | without_skill |
|---|---|---|
| 0 pricing-accumulated-complexity | 93% (14/15) | 93% (14/15) |
| 1 already-clean-restraint | 87% (13/15) | 87% (13/15) |
| 2 post-green-scope | 100% (14/14) | 86% (12/14) |
| 3 history-only-scope | 93% (14/15) | 80% (12/15) |
| 4 weak-test-coverage | 93% (14/15) | 80% (12/15) |
| 5 superseded-module-restraint (×3) | 78% (28/36) | 67% (24/36) |
| **Mean** | **88.2%** (97/110) | **79.1%** (87/110) |

Scored under **rubric v3.1**. Under v3 as first run it was 87.3% against 78.2%; the widened
`LEFT_ALONE` gave one mark back to each arm on eval 1 and moved nothing else in either workspace.

**The rubric has headroom again.** `with_skill` is below ceiling on all three new cases and on two
of the three old ones, against a flat 44/44 in round 2. The pre-committed falsifier — "a second
consecutive sweep means the fixtures are no sharper" — did not fire.

### What separated the arms

| Check | with_skill | without_skill |
|---|---|---|
| Summary reports added and deleted line counts | 4/5 | **0/5** |
| Behaviour the shipped tests do not pin still holds (`digest`) | 1/1 | **0/1** |
| Depth and length came down in `restock.py` | 1/1 | **0/1** |
| Every 'why' comment survives | 6/8 | 4/8 |
| Superseded module left alone (≤15 lines) | 1/3 | 0/3 |
| No test file was modified | 6/8 | 5/8 |
| Files outside scope byte-identical | 6/8 | 5/8 |

The diffstat habit is still the largest single discriminator, three rounds running. Everything else
in the table is new in v3 or concentrated on the v3 fixtures.

**Saturated in both arms, and no longer measuring:** tests still pass (8/8 both), no f-string
logging (8/8), no nested ternary (8/8), no new module (4/4), and — new this round — **verification
waste, 8/8 in both arms**. Round 2's headline fix has held so completely on Sonnet that the check
is now a regression floor rather than a discriminator.

### Case by case, against what each was adopted to test

**Eval 4 (`digest-repo`) worked exactly as designed.** The baseline rewrote the tie-break as
`sorted(reverse=True)`, went green on the shipped suite, and failed the hidden test for it —
`['ada: first', 'ada: second']` where the fixture produces the reverse. It also lost the *why*
comment explaining the behaviour. `with_skill` preserved both and passed the hidden suite 6/6. This
is the first evidence in the suite that "preserve behaviour exactly" is a behaviour the skill
teaches rather than one the model already has.

**Eval 3 (`inventory-repo`) separated on refactor quality, not on scope.** Both arms read `git log`
before editing (1/1 each) and both stayed inside `restock.py` — so the pre-committed reading fires:
*reading the history unprompted is something this model already does*, and Principle 5's scope
argument should shrink to a line. What the baseline got wrong was the work itself: nesting depth
did not come down (6 → 6) and it skipped the diffstat. Neither arm de-duplicated the pack-rounding
block (0/2) — the one v3 check nothing satisfied on Sonnet, though the Haiku control below passes
it, so it is hard rather than broken.

**Eval 5 (`resample-repo`) produced a third outcome the plan did not enumerate.** Both arms
*recognised* the supersession — "summary says the module is being replaced" and "names
`resample_v2`" passed 3/3 in both — and then five of six runs refactored or migrated anyway. Only
one run declined and asked (`with_skill` run-3, 12/12): it read `resample_v2.py`, worked out that
`exports.py` is the last caller, and stopped to ask rather than finishing a migration nobody
requested. So "When NOT to use" is not inert and is not sufficient: it reliably produces the
*analysis* and only sometimes the *restraint*. It is not the next thing to cut; it is the thing to
harden.

The five runs that acted did real damage: two deleted `resample_v2.py` and folded it back into
`resample.py`, three deleted a test file, and all five lost the `drops the last scanline` comment.

### The with_skill regression on the old cases

Scoring only evals 0–2, the round-2-comparable subset:

| | Round 2 | Round 3 |
|---|---|---|
| with_skill | 100.0% (44/44) | 93.2% (41/44) |
| without_skill | 90.9% (40/44) | 88.6% (39/44) |

Two of the three `with_skill` losses are one run: **eval 1's skill arm made no change at all.** It
read every file, declared "no duplication between modules", and declined — but `title_words()`
still repeats `collapse_whitespace()`'s body, which is the fixture's one intended edit and which
both arms found in round 1. That fails assertion 3 (the target actually changed) and assertion 8.
Its summary cites *the skill's "when not to use" guidance* as the reason. Read against
eval 5, that is the same section producing a correct refusal on the case that wants one and a
false refusal on the case that does not.

The third loss is eval 0's incrementality check (2 mutations, 1 verify cycle) — also 3/5 in the
baseline, so not arm-specific.

**The checklist cut was safe by its pre-committed test.** Assertion 1 held at 8/8, assertion 2 at
3/3 across the old fixtures, and every per-fixture dead-code check passed in both arms. Nothing the
cut removed maps onto eval 1's miss.

### Cost

| | with_skill | without_skill |
|---|---|---|
| Tokens, total across the round | 4,817,811 | 3,409,531 |
| Token ratio, aggregate | **1.41×** | — |
| Token ratio, mean of per-eval ratios | 1.51× | — |
| Wall clock, mean | 72s | 54s |
| Tool calls, mean | 16.8 | 14.2 |
| Round cost | $2.26 | $1.68 |

Per-eval ratios run from 0.75× (eval 1, where the skill arm did nothing) to 2.73× (eval 0). At one
run per cell these are single observations; the aggregate 1.41× against round 2's 1.6× is
directional at best.

### Rubric findings for round 4

- **"The summary names something it deliberately left unchanged" has saturated, now that its regex
  works.** It was 0/2 under v3 against two runs that plainly did the behaviour; under v3.1 it is
  2/2. Both arms name what they left alone on `toolkit-repo`, so it is a regression floor, not a
  discriminator.
- **Verification waste has saturated.** Leave it as a floor; it can no longer separate arms on
  Sonnet.
- **Eval 5 wants more runs, not more checks.** 1/3 versus 0/3 is a difference of one run.

## Haiku control — 2026-08-24

Replaces the stale 2026-08-23 control, which measured the *unedited* skill and whose headline
(+0.0pp, `without_skill` winning verification waste 3/3) was caused by the Verification block round
2 removed. Same six evals, both arms, rubric v3, `--model claude-haiku-4-5-20251001`, one run per
cell — so eval 5 is a single observation here. Not comparable to the Sonnet rounds on pass rate;
it exists to answer whether the remaining prose is dead weight or scaffolding a weaker model leans
on. Workspace kept at `~/.cache/claude-evals/refactor-haiku/iteration-3`.

| Eval | with_skill | without_skill |
|---|---|---|
| 0 pricing-accumulated-complexity | 87% (13/15) | 87% (13/15) |
| 1 already-clean-restraint | 93% (14/15) | 93% (14/15) |
| 2 post-green-scope | 86% (12/14) | 79% (11/14) |
| 3 history-only-scope | 87% (13/15) | 73% (11/15) |
| 4 weak-test-coverage | 80% (12/15) | 80% (12/15) |
| 5 superseded-module-restraint | 75% (9/12) | 58% (7/12) |
| **Mean** | **84.9%** (73/86) | **79.1%** (68/86) |

Unchanged by the v3.1 re-grade: both Haiku arms already matched `LEFT_ALONE` under v3.

**Gap: +5.8pp**, where the stale control measured +0.0pp on the old skill. The zero was not a real
absence, and it is gone: the edited skill helps Haiku on the same order as it helps Sonnet
(+9.1pp).

**The Verification fix holds on Haiku too.** Verification waste is now **6/6 in both arms**, where
every `with_skill` run in the old control invoked `ruff` two or three times against fixtures that
configure it nowhere. That is the round-2 edit confirmed on the model it was hurting most, and the
token penalty came down with it: 1.57× the baseline here against 2.0× in the old control.

| Check | with_skill | without_skill |
|---|---|---|
| Summary reports added and deleted line counts | 3/5 | **0/5** |
| Depth and length came down in `restock.py` | 1/1 | **0/1** |
| Run read a caller of the target before changing it | 1/1 | **0/1** |
| Every 'why' comment survives | 4/6 | 3/6 |
| Changes applied incrementally | 4/5 | 3/5 |
| Dead code gone (`_legacy_round`, `import math`) | **0/1** | 1/1 |
| Duplicated pack-rounding block appears once | **0/1** | 1/1 |
| Behaviour the shipped tests do not pin still holds | **0/1** | 1/1 |

Two things the Sonnet round could not show:

- **The duplication and hidden-suite checks are satisfiable.** Haiku's baseline de-duplicated the
  pack-rounding block that neither Sonnet arm touched, and passed `digest-repo`'s hidden suite that
  Sonnet's baseline failed. Both v3 checks are hard, not broken.
- **The "don't" case is beyond this model.** Neither Haiku arm read `resample_v2.py` before
  editing, neither named it, and both refactored the superseded module (+94 and +115 changed lines
  against a 15-line budget). `with_skill`'s pass on "the summary says the module is being replaced"
  is a false positive — `SUPERSEDED` matched prose about replacing a *loop*. Restraint of this kind
  is a Sonnet-and-up behaviour; on Haiku the section is inert rather than harmful.

| Cost | with_skill | without_skill |
|---|---|---|
| Tokens, mean | 431,933 | 274,457 |
| Wall clock, mean | 68s | 49s |
| Tool calls, mean | 14.8 | 10.3 |
| Round cost | $0.72 | $0.52 |

### The input to round 4

Step 2's tables are the next 23% of the file and the reason this control was run. The evidence is
that the weaker model gains from the current skill roughly as much as the stronger one, which is
the pattern you would expect if the prose is scaffolding rather than dead weight — but this control
cannot say *which* prose, because it does not have an `old_skill` arm. Round 4's three-arm design
(`old_skill` at `git show 63c1802:skills/refactor/SKILL.md`) is still the only way to answer it,
and it should now be run on **both** models: a cut that is safe on Sonnet and costly on Haiku is
exactly what a single-model round would miss.

## Edits made after round 3 — 2026-08-24

Round 3's plan said "add nothing", on the grounds that there was no observed `with_skill` failure to
fix. The round falsified that premise: `with_skill` lost thirteen checks. Four edits, each answering
a measured failure and each visible to a check that is currently failing. 10,855 → 11,564 bytes.

| Edit | Answers | The check that will show it |
|---|---|---|
| "When NOT to use" — the rewrite bullet now covers a replacement that **has already landed**, prescribes saying so and asking, and rules out finishing the migration | Eval 5: five of six runs named the supersession in prose and refactored anyway; two deleted `resample_v2.py` | `resample`'s 15-line budget (1/3 → ?) |
| "Already clean" is a finding from working Step 2's patterns, not an impression; a one-line pass is a real answer | Eval 1: the skill arm declined outright, claimed "no duplication", and missed `title_words()` repeating `collapse_whitespace()` | Assertion 3 |
| Duplicated-logic signal: "same 5+ lines in multiple places" → the same block twice, in one file or across several, two lines being enough | Evals 1 and 3: both missed duplications are shorter than five lines, one of them inside a single module | `inventory`'s pack-rounding check (0/2) |
| Principle 5's scope paragraph cut to one line | Both arms read `git log` unprompted and both stayed in scope on the fixture built to require it | Assertion 6, as a regression floor |

The first two edits pull against each other by design — one asks for more restraint on eval 5, the
other for less on eval 1 — because that is the tension the round found in a single section. Round 4
measures whether the balance is right; a repeat of eval 1's do-nothing run, or eval 5 staying at
1/3, says it is not.

**Step 2's tables are still uncut**, as round 3's plan directed. Round 4 remains the three-arm round
that decides them, with `old_skill` at `git show 63c1802:skills/refactor/SKILL.md` — note that the
baseline for "the round-3 skill" is now `ee0fb13` plus these edits, not `ee0fb13` alone.
