# `review-repo-agents` benchmark

Dated record of eval rounds. Each entry names the rubric version it was graded under, because a
score is only comparable to another graded the same way. See [README.md](README.md) for what the
checks mean and [../eval-approach.md](../eval-approach.md) for the shape.

## Rubric v1

Five mechanical checks on every case (agent coverage, files opened, verdict per agent, one figure
with a unit, three verbatim quotes), a 600-word budget on `sound-agent-set-restraint` alone, and
five to eight judgement statements per case — nineteen in total across three cases, graded blind by
sonnet against a per-fixture ground-truth paragraph.

## Round 1 — 2026-09-18, sonnet, rubric v1

One run per cell, two arms, three cases. The suite's first round, so these numbers are a starting
line, not a comparison.

| Eval | with_skill | without_skill |
|---|---|---|
| 0 defective-agent-set | 92% (12/13) | 69% (9/13) |
| 1 sound-agent-set-restraint | 91% (10/11) | 100% (11/11) |
| 2 mixed-keep-and-remove | 100% (11/11) | 82% (9/11) |
| **Mean** | **94.3% (33/35)** | **82.9% (29/35)** |

### Checks that moved

| Check | with_skill | without_skill |
|---|---|---|
| At least one recommendation is backed by a quantity | 2/3 | 1/3 |
| Each recommendation says how the improvement would be checked afterwards | 1/1 | 0/1 |
| For each kept agent, which concrete benefit it delivers | 1/1 | 0/1 |
| test-runner and unit-test-runner do the same job — merge or differentiate | 1/1 | 0/1 |
| Four of five agents have no trigger path | 0/1 | 1/1 |
| The report quotes at least three strings verbatim | 3/3 | 2/3 |

### Cost

|  | with_skill | without_skill |
|---|---|---|
| Tokens, mean | 219,912 | 227,649 |
| Wall clock, mean | 69s | 59s |
| Tool calls, mean | 13.3 | 15.3 |
| Cost, total | $0.63 | $0.60 |

Cost is a wash. The skill buys what the reports say, not fewer tokens.

### What this round actually established

**The separation is real but narrower than the mean suggests.** It comes from evals 0 and 2 — the
two cases with something to find — and from four checks, all of which are about *how a
recommendation is argued* rather than whether the defect was spotted. Both arms find the planted
defects. Only the skill arm says what an agent buys, how a fix would be verified, and that two
duplicates could be merged rather than one simply deleted. That is the skill's contribution, and it
is a coherent one: the body's demand for "measurably" is what the baseline has no reason to meet.

**Eval 1 separated nothing.** All five of its judgement statements passed in both arms: the
baseline removed no agent, proposed no new one, concluded the setup was sound and still examined
the model tiers. Restraint on a clean repo appears to be what sonnet does anyway, so the case is
currently a regression floor rather than a discriminator. Either the fixture needs a temptation in
it — an agent that looks wasteful and is not — or the case is measuring something the skill does not
need to supply. Decide that before round 2; do not rewrite the statements in place.

**The one regression is worth fixing in the skill.** On eval 0 the skill arm noted only
`unit-test-runner` as unreferenced; the baseline generalised it to all four orphans and won the
check outright. The trigger criterion lives in the skill's third section as half a sentence —
*"Consider how they are triggered and whether that could be improved"* — and the run treated it as a
per-agent aside rather than something to sweep for. It is the only place the skill scored below its
own baseline.

**The quantity check is not yet trustworthy.** It read 3/3 against 0/3 on one staging of this round
and 2/3 against 1/3 on the next, with one observation per cell. It is the single strongest-looking
discriminator here and the one most likely to be noise. Run eval 1 and the quantity check at
`--runs 3` before anyone cites that number.

**Saturated in both arms, kept as floors:** agent coverage, files opened, the 600-word budget, and
fourteen of the nineteen judgement statements — including every statement on eval 2 bar none in the
skill arm. Leave them; add sharper checks beside them rather than rewriting these.

### Fixture history

`sound-repo` was patched twice during this round, before any of it was recorded, because the first
two runs of eval 1 both found real inconsistencies in it rather than practising restraint:

1. `docs-drift` was told to read a `README.md` and CLAUDE.md named `stations/*.json`, neither of
   which existed. Added both, plus `src/tideline/stations.py` to read them.
2. `docs-drift`'s description still promised to check "station files" its instructions never
   opened, and `harmonic-review`'s CLAUDE.md trigger row was narrower than its own description.
   Reconciled both.

The fixture as it stands is the one round 1 was graded against. A restraint fixture only works if a
careful reviewer genuinely finds nothing structural in it, and getting there took two passes — worth
knowing before editing it again.
