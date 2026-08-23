# Eval benchmark — `plan`

A dated record of what this skill scored, so a future round can be compared against it rather
than read in isolation. Append rounds; don't rewrite them. The harness that produces these
numbers lives beside this file — read [README.md](README.md) before re-measuring.

Four evals, two arms each (`with_skill`, `without_skill`), one run per cell. One run per cell
means token, cost and time figures are single observations, not distributions — treat a 20%
swing as noise. Pass rates carry more, but roughly half of each eval's checks are model-graded,
so they are not free of noise either.

## Rubric versions

| Version | Assertions | Introduced |
|---|---|---|
| v1 | 5 mechanical (+2 with a fixture) and 6 shared judgement, plus 3–4 per eval | Round 1 |
| v2 | 6 mechanical (+2 with a fixture) and 10 shared judgement, plus 3–4 per eval | After round 1 |

v2 exists because reviewing round 1 changed what counts as good, not only how well the skill did
it. Rounds 1 and 2 are comparable on the assertions they share and **not** on these:

- **One question per turn is gone.** Answering two or three real decisions in a turn is fine and
  faster; what isn't fine is padding a turn with questions that have one sensible answer. The
  mechanical check is retired and replaced by two judgement assertions — no strawman options, and
  no bundling a decision with the thing it depends on.
- **"Ends with a plan someone else could implement" is replaced** by "the plan is one the user
  agreed to decision by decision". The old wording scored 0/4 with the skill and 2/4 without,
  because a one-turn plan dump reads as complete. It was rewarding the dump.
- **"Asks nothing the repo answers" now needs three turns first.** A run that asks almost nothing
  cannot ask a bad question, and was passing for free — the same defect the termination check had.
  Re-grading round 1's transcripts under this rule moves it from 3/3 to 3/1.
- **Three assertions added** for behaviour the skill did not previously ask for: framing choices by
  consequence rather than jargon, leaving room for an unlisted answer, and favouring the option
  that leaves less to maintain while naming what it gives up.
- **Eval 0's per-eval assertions were sharpened.** Two of its three passed in both arms, which is
  why round 1 was a 9/9 tie there. They now target making the settled calls yourself and explaining
  the algorithm choice by its effect on a bursty client.

## Rubric v4 — 2026-08-15, after round 3

Four checks retired for being unsatisfiable by a run following the skill, one reworded, one
re-based. Round 4 runs under v4, and re-grades round 3's stored transcripts under it so the two
rounds line up — round 3's own numbers above stay as they were measured.

- **The opening word budget is gone.** It was the wrong axis: raised once from 350 to 450, it still
  failed a 484-word turn that had read the repo and asked four recommendation-led questions, and it
  failed a 579-word turn asking eight questions alongside a genuine plan dump. The check now looks
  for what a delivered plan actually does — announce itself in a `## The plan` heading — and
  ignores length. On round 3's transcripts that reads 4/4 new, 4/4 old, 2/4 none: still separating
  the arm that dumps, no longer punishing the arm that reads before it asks.
- **"Every question states a recommended answer" is scoped to decision questions.** As written it
  failed a run for asking how many rows the biggest report held — a fact the interviewer cannot
  look up and cannot recommend an answer to — which is why the arm that asked least scored best on
  it, 2/4 against the skill's 1/4. Questions asking only for an unlookupable fact are now exempt.
- **Eval 3's first two per-eval assertions are replaced.** One required asking what was slow when
  the fixture's docstring names the endpoint; the other required staging an instrument-first choice
  when the bug is confirmed in the source. Both punish what the skill teaches, which is why they
  were 0/3 for three rounds. They are replaced by three that target the case's actual purpose —
  decision-forcing on vague scope: cut the complaint to one named target, settle the order of work
  including what is deferred, and settle what "fast enough" means or settle explicitly that it
  cannot be set.
- **Eval 0's algorithm assertion is re-based** off "a bursty ETL client at the top of the hour",
  which demanded the run invent one particular illustration. A round-3 run explaining that "5/sec
  invites arguments about a burst of 6 that landed in the same second" was failed by it. It now
  asks for the experience of a client hitting the limit, however illustrated.

Not touched, though both were 0/3 in round 3: eval 2's endpoint-URL and in-flight-events
assertions. That run interviewed for two turns and stopped — a short interview is the likeliest
explanation, and there is no evidence yet that a longer one could not satisfy them.

## Round 3 — 2026-08-15

One change to the skill, deliberately: the lead-with-a-recommendation rule in `How to ask` now says
the recommendation belongs on the still-open question, not only on the preamble of calls already
made. Rubric v3 — the mechanical open-door check dropped (it fired on 1 of 4 transcripts the blind
grader passed 4 of 4, so it was measuring which phrasings the regex knew; the judgement statement
covering the same behaviour stays), and one judgement assertion added on decisions settled
unilaterally, since the rubric could see whether the questions *asked* were real but not whether the
ones *skipped* were skippable. Arms: `with_skill` is the edit, `old_skill` is `5f8679d`'s SKILL.md
(round 2's rewrite), `without_skill` is no skill. All `sonnet`; `--max-turns 16`.

| Eval | new skill | old skill | no skill |
|---|---|---|---|
| 0 rate-limit-in-repo | 76% (16/21) | 81% (17/21) | 76% (16/21) |
| 1 postmortem-rollout-no-code | 95% (18/19) | 79% (15/19) | 74% (14/19) |
| 2 stress-test-webhook-plan | 65% (15/23) | 74% (17/23) | 17% (4/23) |
| 3 slow-api-vague | 67% (14/21) | 62% (13/21) | 48% (10/21) |
| **Mean** | **75.7%** | **73.9%** | **53.7%** |

+1.8pp is inside noise at one run per cell, the same reading as round 2. Cost is flat between the
skill arms at $0.47–$0.68 a run, against $0.15–$0.42 unaided.

### Three instruments were repaired mid-round

Found by reading transcripts against their own grades. Mechanical checks are deterministic, so the
runs were re-graded in place without re-spending on the grader; judgement verdicts are untouched.

- `BUILD_HANDOFF` matched a bare "want me to write", so *"want me to write this up as a markdown
  plan doc"* — the handoff the skill exists to offer — was scored as an offer to write code. Its
  write branch now has to name something code-shaped.
- `PLAN_FILE_OFFER` missed the same sentence: it allowed no words between the article and
  `file|doc`, and real offers name the artefact. So both skill arms lost two checks on eval 1 for
  doing the right thing once.
- `_RECOMMENDATION` was a closed verb list that did not contain "my call:", "I'd fix", "I'd reach
  for" or "I'd leave". It now reads any "I'd <verb>" bar the forms that ask for something
  ("I'd need to know"). This is the same defect that retired the open-door check, in the check that
  matters most.

**Round 2's numbers for these three checks were produced by the broken versions and cannot be
re-graded — those transcripts are gone.** Its "file offer 2/4" and its recommendation column are
not comparable with anything here.

### What the round says about the skill

- **The edit cannot be credited with the recommendation result.** Under the repaired instrument the
  round reads 4/4 new, 3/4 old, 2/4 none — but round 2's 2/4 was measured with the broken one, so
  there is no before to compare against. What can be said is that with a working instrument, both
  skill arms lead their questions and the unaided arm does so less.
- **Eval 1 is where the edit shows**: 95%, +16pp over the old skill, its one remaining failure being
  the opening word budget.
- **One clear regression**: "favours the option that leaves less to maintain" is 1/4 new against 3/4
  old.
- **Convergence speed is the new variance.** The new skill's eval 2 run interviewed for two turns —
  below the three-turn interview floor, costing it that check and the repo-answers one. Round 2's
  ran four.

### Eval 3, read by a human

Round 2 asked for this. Two of its three per-eval assertions are unsatisfiable by a run that follows
the skill, which is why they have failed in every arm for three rounds:

- *"Pins down what is actually slow … before proposing any fix"* — the fixture's own docstring names
  the endpoint and the N+1 is visible in the source. The skill says read rather than ask; the
  assertion requires asking.
- *"Forces a choice between instrumenting first and fixing the visible problem first"* — with the
  bug confirmed in the source, instrument-first is not a live option. The skill says cut decisions
  with one sensible answer; the assertion requires staging one.

Only the third, pagination as a breaking change to a public response shape, is a fair miss. Rewrite
the first two against what the round-3 transcript shows a good run doing.

### What this round says about the rubric

- **Round 2's convergence finding does not replicate.** The same old-skill text ran 7, 10, 4 and 3
  turns here and stopped itself every time, where round 2 capped it at 16 on two evals and concluded
  non-termination was "a property of the skill". It is run-to-run variance. Nothing about turn count
  should be concluded from one run per cell.
- **The "every question" judgement assertions reward asking less.** "Every question states a
  recommended answer" reads 1/4 new, 0/4 old, **2/4 none** — the grader is told a single exception
  fails the assertion, and a factual question ("how big is their largest report?") cannot carry a
  recommendation. Scope it to decision questions.
- **The opening word budget is now catching the skill's own prescription.** Eval 3's new-skill turn
  failed at 484 words against 450, for a turn that read the whole repo and asked four
  recommendation-led questions. Raising the number again is not the fix; the check wants a proxy for
  "delivered a finished plan" that is not length.
- Inverse-saturated for a second round: eval 0's bursty-ETL-client assertion, 0/3.

## Round 2 — 2026-08-13

Skill rewritten from round 1's review (see "What the review changed in the skill" below). Rubric
v2. Three arms this round, because the question had become "did the rewrite help?" rather than "does
the skill help": `with_skill` is the rewrite, `old_skill` is `e0d540c`'s SKILL.md, `without_skill` is
no skill. All `sonnet`; `--max-turns` raised 12 → 16.

| Eval | new skill | old skill | no skill |
|---|---|---|---|
| 0 rate-limit-in-repo | 86% (18/21) | 81% (17/21) | 71% (15/21) |
| 1 postmortem-rollout-no-code | 79% (15/19) | 74% (14/19) | 58% (11/19) |
| 2 stress-test-webhook-plan | 70% (16/23) | 65% (15/23) | 17% (4/23) |
| 3 slow-api-vague | 62% (13/21) | 67% (14/21) | 38% (8/21) |
| **Mean** | **74.0%** | **71.7%** | **46.2%** |

**Read the headline as "no measured regression", not as a win.** One run per cell puts +2.3pp well
inside noise, and eval 3 went the other way.

The result that is not noise is convergence:

| Eval | new skill | old skill |
|---|---|---|
| 0 | 4 turns, stopped itself, $0.45 | 16 turns, **capped**, $0.84 |
| 1 | 6 turns, stopped itself, $0.32 | 16 turns, **capped**, $0.34 |
| 2 | 4 turns, stopped itself, $0.58 | 10 turns, stopped itself, $0.55 |
| 3 | 5 turns, stopped itself, $0.62 | 14 turns, stopped itself, $0.67 |

Raising the cap from 12 to 16 did not rescue the old skill — it capped at 16 on the same two evals
it capped at 12 on. Its failure to terminate is a property of the skill, not of the turn limit.

### What landed

- Bundled decisions are independent of each other: 4/4, up from 2/4.
- Every question is a real decision rather than a strawman: 4/4, up from 3/4.
- Offering to write the plan out to a file: 2/4, up from 0/4 — half landed, evals 0 and 1 only.

### What regressed

**"Question turns carry an explicit recommendation" fell to 2/4 from the old skill's 4/4.** The
rewrite moved recommendation language up into the settled-calls preamble and left the questions
themselves phrased as options. This is the first thing round 3 should fix — it was the single
cleanest separator in round 1 and the rewrite spent it.

### What this round says about the rubric

- **The open-door check is broken.** Mechanically it fires 1/4; the blind grader passes the
  semantic version 4/4 on the same transcripts. The regex is too narrow to be trusted. Widen it or
  drop it and keep the judgement statement.
- **A new gap.** The rewrite trades questions for calls the skill makes itself. There is an
  assertion that every question *asked* is a real decision, but none that every decision *settled
  unilaterally* was genuinely settle-able. A short, high-scoring interview could be one that quietly
  decided something the user cared about. Round 3 needs that assertion.
- **Eval 3 is unmoved** — 13/21 vs 14/21, and all three of its per-eval assertions fail in every
  arm across both rounds. Either the skill has a real gap on vague-scope work or those three are
  written too strictly. This is the case most worth a human read.
- `Reads the repository before its first question` is 3/3/3 for the second round running. Floor.

## Round 1 — 2026-08-13

Skill at commit `e0d540c`, unedited — this round exists to establish a baseline and to find out
whether the rubric discriminates at all. Interviewer, simulated user and grader all `sonnet`;
`--max-turns 12`.

| Eval | Fixture | with_skill | without_skill |
|---|---|---|---|
| 0 rate-limit-in-repo | `api-repo` | 56% (9/16) | 56% (9/16) |
| 1 postmortem-rollout-no-code | — | 64% (9/14) | 57% (8/14) |
| 2 stress-test-webhook-plan | `payments-repo` | 76% (13/17) | 35% (6/17) |
| 3 slow-api-vague | `api-repo` | 63% (10/16) | 38% (6/16) |
| **Mean** | | **64.9%** | **46.5%** |

Turns, cost and wall clock, interviewer only:

| Eval | with_skill | without_skill |
|---|---|---|
| 0 | 12 turns, capped, $0.60, 247s | 10 turns, $1.38, 597s |
| 1 | 12 turns, capped, $0.42, 203s | 9 turns, $0.92, 397s |
| 2 | 9 turns, $0.64, 280s | 1 turn, $0.26, 125s |
| 3 | 5 turns, $0.65, 310s | 2 turns, $0.24, 98s |

The cost column runs backwards on evals 0 and 1: the unaided arm is more than twice as
expensive because it answers a planning request by writing a long plan document, repeatedly.

### What separated the arms

Two checks did nearly all the work. **Recommendation-led questions** passed 4/4 with the skill
and 0/4 without — the single cleanest signal in the round. **Opening by asking rather than by
delivering a plan** was 4/1. Behind those, forcing a choice between named options (2/0) and
picking up branches opened by an answer (4/2).

### What the round says about the skill

- **It does not converge.** Evals 0 and 1 both ran out at the 12-turn cap mid-interview, which
  also cost them the handoff-ready and TDD-offer checks. Round 2 should raise `--max-turns` to
  ~16 to separate "thorough but slow" from "never terminates" before concluding anything.
- **It bundles.** "At most one question per turn" failed on 3 of 4 evals, and the blind grader
  independently failed the semantic version on the same runs, so this is behaviour and not a
  proxy artefact.
- **Vague scope is its weak spot.** Three assertions failed in *both* arms, all on the
  instrument-vs-fix and what-is-actually-slow decisions in eval 3.

### What the review changed in the skill

The reviewer's notes on these transcripts drove a rewrite of `SKILL.md`, which round 2 measures:
cut decisions that only have one rational answer instead of asking them; frame a choice by what it
changes rather than by naming the mechanism; leave room for an answer that wasn't offered; group
independent real decisions freely rather than one per turn; prefer the option that leaves less to
maintain, with an explicit guard against confusing that with fewer lines; and offer to write the
settled plan to a file, not only `/tdd`.

### What the round says about the rubric

Four defects to fix before round 2. Recording them here because a rubric edited silently between
rounds makes the rounds incomparable.

- **"Ends with a plan someone else could implement" is inverted** — 0/4 with the skill, 2/4
  without. The baseline dumps a finished plan in one turn and reads as complete; the with-skill
  runs were cut off by the turn cap. It currently rewards the dump.
- **"Asks nothing the repository already answers" is confounded.** An arm that asks almost
  nothing cannot ask a bad question, so a one-turn dump passes it for free. It should only be
  scored over runs that actually held an interview — the same defect as the termination check,
  which was given a three-turn floor mid-round for exactly this reason.
- **"Reads the repository before its first question" has saturated** at 3/3 in both arms. Sonnet
  reads the repo unprompted. Keep it as a floor; it is no longer a signal.
- **Eval 0 has stopped discriminating** — a 9/9 tie, with all three of its per-eval judgement
  assertions passing in both arms. An unaided model raises the same content on a rate-limiting
  design; it just never interviews. Either sharpen eval 0's assertions toward interview shape or
  accept it as a floor case. Eval 2's content assertions have the same problem, though its
  overall gap (76% vs 35%) is the widest in the round.
