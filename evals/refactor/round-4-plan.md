# Round 4 plan — deciding Step 2's tables

Round 3 settled the question rounds 1 and 2 could not: the skill separates from the baseline on a
rubric with headroom, **88.2% against 79.1% on Sonnet and 84.9% against 79.1% on Haiku**. The
strategic read that round 3 held in reserve — "two instructions wearing an 11 KB coat" — did not
fire. So round 4 is not about whether to keep the skill. It is about how much of it is doing the
work.

One thing is now the obvious candidate and has been deferred twice: **Step 2's three tables, 2,550
characters, 22% of the file.** Round 3's plan refused to cut them because a saturated rubric could
not falsify the cut. The rubric is no longer saturated, so the cut is measurable — but only with a
third arm, because the comparison is between two versions of the skill, not between the skill and
nothing. Read [benchmark.md](benchmark.md) for the numbers this reacts to and
[eval-approach.md](../eval-approach.md) for the rules it obeys.

## Three constraints that shaped it

**A third arm triples the confound surface.** Round 3 changed the rubric and the fixtures in one
go and got away with it because the new checks were per-fixture. Round 4 adds an arm *and* carries
four fresh `SKILL.md` edits into `with_skill`. That is already two changes; a third would make the
round unreadable. **The rubric is frozen at v3.1 and no fixture is touched.**

**`plan/` already paid for the lesson that n=1 cannot resolve arm-vs-arm.** Its round 3 measured
+1.8pp between the new skill and the old one and had to record it as "inside noise at one run per
cell". That is exactly the size of difference this round is looking for. A three-arm round at one
run per cell would buy an unreadable number, so **round 4 runs three per cell on both models** —
the first round in this suite with distributions rather than single observations.

**`with_skill` is no longer round 3's `with_skill`.** Four edits landed after the round (`f715b61`):
the superseded-module bullet, the "already clean" counterweight, the duplication threshold, and
Principle 5's scope cut. Round 4 measures those too, and it can only do so across rounds — which is
sound *only if* `without_skill` holds steady. The baseline is this round's drift control, and if it
moves, every cross-round claim about the edits is void.

## The third arm points at an ablation, not at a snapshot

Both the round-3 plan and the benchmark say `old_skill` should be `git show
63c1802:skills/refactor/SKILL.md`. **Do not do that.** That file differs from today's in the
Verification checklist *and* all four round-3 edits *and* the tables — pointing an arm at it
measures the sum of three rounds of work and attributes none of it. `run_case.py --skill` takes any
path, so the third arm should be whatever file answers the question. Here that is a deliberate
ablation of the current skill.

**The ablation is name-only, not a pure deletion.** Two variants were considered:

| Variant | What it does | Why not |
|---|---|---|
| Pure cut | Step 2 keeps its heading and one line; all 17 rows gone | If it loses, you learn nothing about whether a cheaper version would have done. If it wins, so would name-only |
| **Name-only** | The 17 pattern names survive as a bare list; the Signal and Simplification columns go | **Chosen.** ~2,174 chars, 19% of the file, and it is the change you would actually ship |

Name-only dominates because both outcomes are actionable: if it holds, ship it; if it loses, the
elaboration is load-bearing and the tables stay whole. A pure cut only answers one of those.

**The ablation must differ from `with_skill` in exactly one hunk.** Generate it from the live file,
then `diff` the two and confirm the only difference is inside Step 2. Anything else and the arm is
measuring something other than the tables.

**One row of the ablation is uncomfortable, and deliberately so.** The duplication row's Signal
column was rewritten two days ago in response to a measured failure — "two lines is enough when they
encode one decision", after both Sonnet arms missed sub-five-line duplications on `toolkit-repo` and
`inventory-repo`. Name-only deletes that threshold. If the ablation arm reproduces those misses,
that is the strongest available evidence that the Signal column is scaffolding rather than padding,
and the tables stay.

## Decisions taken

| Decision | Choice | Why |
|---|---|---|
| Third arm | An ablation of the current file, not a git snapshot | A snapshot confounds three rounds of edits; the question is about the tables alone |
| Ablation shape | Name-only, 17 bullets | Shippable if it wins, diagnostic if it loses |
| Rubric | Frozen at v3.1 | Two changes are already in flight; a third makes the round unreadable |
| Fixtures | None touched, none added | The rubric has headroom at 88.2%; new cases would spend it on confounds |
| Repeats | Three per cell, every case, both models | `plan/`'s round 3 proves arm-vs-arm at n=1 is unreadable, and that is this round's central comparison |
| Models | Sonnet **and** Haiku, both three-arm | A cut safe on Sonnet and costly on Haiku is exactly what a single-model round misses, and Haiku is where the tables are most likely to be scaffolding |
| Burden of proof | On keeping the prose | The round is a screen for harm, not a proof of safety — see the decision rule below |
| Skill edits | **None before the round** | Four landed after round 3 and are unmeasured; adding more makes them unattributable |

## What the round is, precisely

Three arms × six cases × three runs × two models = **108 runs**.

| Arm | `--skill` | Answers |
|---|---|---|
| `with_skill` | `skills/refactor/SKILL.md` | Did the four post-round-3 edits work? (against round 3) |
| `old_skill` | `evals/refactor/ablations/step2-names-only.md` | Are the tables dead weight? (against `with_skill`) |
| `without_skill` | — | Drift control, and the standing baseline |

## Sequence

**Phase 0 — the machinery, before anything runs.**

1. `prepare.py --arms with_skill,old_skill,without_skill` — `shared/workspace.ARMS` is a fixed
   two-tuple today and `prepare.py` loops over it. A suite-local `--arms` flag is the smaller
   change; leave `shared/` alone mid-round.
2. `evals/refactor/ablations/step2-names-only.md`, generated from the live `SKILL.md`, plus the
   `diff` that proves the only hunk is Step 2.
3. `evals/refactor/aggregate.py` (`# agent-tool: false`) — 108 runs across three arms is past what
   a throwaway script should carry. It reads `grading.json`, emits the per-eval table, the
   per-check arm comparison, and the cost block. Promote it to `shared/` only if another suite
   asks for it.
4. `README.md`: the three-arm invocation, and the two-pass `xargs` it needs — `old_skill` run
   directories take `--skill`, the other two do not.

**Phase 1 — the round.** Fresh workspaces at `--iteration 4`, `--runs 3`, both models.

**Phase 2 — the decision**, taken against the rules below before looking at anything else, then
recorded in `benchmark.md` with the round.

## What would falsify each part

**The tables come out** if the ablation is within **2pp** of `with_skill` on *both* models **and**
no table-mapped check regresses by more than one run on either. The table-mapped checks are the ~14
the tables' rows claim to teach: depth-and-length, dead-code and duplication on `pricing`, `ledger`,
`inventory` and `digest`, plus the `what`-comment check and the shared `why`-comment check.

**The tables stay** if the ablation loses **≥5pp** on either model, or any table-mapped check drops
by **≥2 runs** on either. Between 2 and 5pp with no attributable check regression: keep them, say
the round could not resolve it, and stop asking — three deferrals is enough.

The asymmetry is deliberate. The burden of proof is on keeping 2,550 characters that cost tokens on
every turn, not on cutting them.

**The four edits worked** if, on Sonnet `with_skill`: eval 5's 15-line budget reaches **≥2/3** (1/3
in round 3), eval 1's assertion 3 reaches **≥2/3** (0/1), and `inventory`'s duplication check
reaches **≥1/3** (0/1).

**The edits over-corrected** if eval 5's budget falls to **0/3** while eval 1's assertion 3 is 3/3 —
the counterweight bought action on the restraint case by spending restraint on the case that needed
it. That is the specific risk of writing two bullets that pull against each other, and it is the
first thing to look at.

**Everything cross-round is void** if `without_skill` lands more than **3pp** from round 3's 79.1%
on the same 110 checks. Within-round arm comparisons still stand; the claims about the edits do not.

**Principle 5's cut was safe** if assertion 6 and eval 3's git-history check hold at their round-3
rates in `with_skill`.

## Cost

Round 3 cost $5.18 across 28 runs. At round 3's per-run rates — $0.246 Sonnet, $0.103 Haiku — this
round is **about $19 for 108 runs**, roughly 25 minutes of wall clock at `-P 6`.

That is the most expensive round the suite has run, and it buys two things no earlier round could:
the first distributions in the suite's history, and a defensible answer on a 19% cut. If the budget
has to come down, drop Haiku's repeats to one run per cell (−$3.7) and accept that the tables
question is then answered on Sonnet alone — do **not** economise by dropping Sonnet's repeats,
which is the axis the round is built on.

## The strategic read

Round 3 established that the skill does something. Round 4 asks what fraction of it does that
something. There are only two honest outcomes: the file comes down to roughly 9.3 KB with a measured
guarantee that nothing graded moved, or the tables are shown to be load-bearing and the "11 KB coat"
reading is retired with evidence rather than deferred again.

The thing to resist is a third outcome — an ambiguous result read optimistically in whichever
direction was already preferred. That is what the pre-committed thresholds above are for, and they
are worth more than the round if they are honoured.
