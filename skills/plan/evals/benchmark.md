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
