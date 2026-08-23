# Round 3 plan — building headroom back into the rubric

Round 2 scored 100% with the skill against 90.9% without: **44 of 44**. Every check is at ceiling,
which means no edit to `SKILL.md` made today is measurable — a cut cannot be shown safe and an
addition cannot be shown to help. So this round inverts round 2's order: the rubric work comes
first and carries the round, and the skill edits are limited to the one cut an existing check would
catch. Read [benchmark.md](benchmark.md) for the numbers this reacts to and
[eval-approach.md](../eval-approach.md) for the rules it obeys.

## Two constraints that shaped it

**Rounds 1 and 2 left no stored workspaces.** They were staged under `/tmp` and are gone, so
neither can be re-graded. A rubric edit that adds a *shared* check therefore breaks the comparison
with them permanently — the opposite of what v2 could do, where round 1's stored runs were
re-graded under the new checks. Everything v3 adds is per-fixture and lives on new fixtures. The
ten shared checks read exactly as they did in round 2.

**The round-2 record does not say which four checks the baseline failed.** It records 40/44 and no
breakdown, so it cannot be shown from the record alone whether the diffstat check is still the only
discriminator. Round 3 records per-check failures for both arms.

## The three new cases

Each grades a section of the skill that nothing has ever graded. All three ship green, and all
three were checked to be satisfiable before they were adopted — a simulated correct run scores full
marks on each.

**4. `inventory-repo` — scope whose only signal is git history.** This is what `ledger-repo` was
supposed to be. `ledger-repo` leaks: its `CLAUDE.md` labels `posting.py` *"Stable since 2021"* and
`export.py` *"Frozen"*, and round 1's baseline read scope straight off that prose rather than the
history. Here nothing says which module is live, the prompt names no file, and the out-of-scope
`stocktake.py` is measurably *uglier* than the in-scope `restock.py` — depth 8 and 45 lines against
6 and 33. Ugliness points away from the answer; `git log` is the only thing that points at it. The
case adds a check that the history was read **before the first edit**, which only became computable
when `_tool_summary` started capturing Bash commands.

**5. `digest-repo` — tests too weak to discharge "preserve behaviour exactly".** Both arms have
always treated a green suite as their entire verification story, and on the first three fixtures
that is enough, because their tests pin the traps. Here they do not. Four behaviours are
load-bearing and untested: the sort-then-reverse tie order, `limit=0` as a no-limit sentinel that
`daily.py` depends on, the no-updates placeholder, and whitespace collapsing inside a subject. The
checks for them live in `hidden/digest-repo/` and are copied into a throwaway copy of the run's repo
*after* the run finishes — never staged into the fixture, because a run that can read them has been
handed the answer. This is the first thing in the suite that grades Step 1 (Chesterton's Fence)
rather than Step 2's pattern-spotting.

A worked check before adopting it: a plausible "clean" rewrite — `sorted(reverse=True)`,
`rows[:limit]`, placeholder dropped — passes the shipped suite and every structural check in the
case, and fails four of the six hidden tests. A careful rewrite that keeps those three lines scores
full marks. The case discriminates on exactly the axis it is meant to.

**6. `resample-repo` — the case whose correct answer is "don't".** The skill's "When NOT to use"
section is ungraded today, all 44 checks over. `resample_v2.py` landed in the last commit and its
docstring says it replaces `resample.py` once `exports.py` moves; the prompt pushes hard the other
way (*"the worst file we've got — give it a proper cleanup pass"*). The signal is in the repo, not
in an instruction: no `CLAUDE.md` line says "don't touch this", because a case that hands over the
answer is `ledger-repo`'s failure again.

## Decisions taken

| Decision | Choice | Why |
|---|---|---|
| Rubric first, skill second | Cases land before any `SKILL.md` edit | At 44/44 an edit is unfalsifiable. Headroom is the prerequisite, not the follow-up |
| New checks | Per-fixture, on new fixtures only | Rounds 1 and 2 cannot be re-graded; a shared check would break the comparison they anchor |
| Fixtures | Three new ones, none of the originals touched | Editing a fixture invalidates `PRICING_BASELINE`, `LEDGER_BASELINE` and `TOOLKIT_DIFF_BUDGET` and makes every earlier round a different experiment |
| The "don't" floor | Shared 3, 8 and 10 skipped for `resample-repo`; summary checks take their place | All three presume a run that changed something. A check nothing can satisfy is a broken check |
| Restraint budget | 15 changed lines, not 0 | Deleting the dead `thumbnail()` wrapper is a defensible tidy; a zero-line bar measures tidiness, not restraint |
| Migrating the last caller | Scores badly, deliberately | It is a rewrite the user did not ask for. Principle 5 rules that out as firmly as the wasted cleanup |
| Repeats | `--runs 3` on eval 5 only | Decline-or-act is binary, so one observation says the least there and costs the least to repeat |

## The skill edits

**Cut now — the Verification checklist.** Round 2's plan identified the three tickboxes as
restating Principles 1, 2 and 5, then did not take the cut. It is the only remaining trim whose
regression an existing check would catch: each tickbox maps onto assertions 1, 2 and the
per-fixture dead-code checks. ~230 bytes, so this is hygiene, not a saving.

**Do not cut Step 2's tables yet.** They are 2,564 characters, 23% of the file, and the obvious
next 20% — but every row maps onto a graded behaviour (nesting, function length, dead code,
duplication, why/what comments), which makes them precisely what a saturated rubric cannot
falsify. They come out in round 4, as a **three-arm round** with `old_skill` pointed at the round-2
file. No snapshot is needed: `git show 63c1802:skills/refactor/SKILL.md` recovers it.

**Add nothing.** There is no observed `with_skill` failure to fix, and anything added now is prose
no check can see.

## Sequence

**Phase 0 — the cases, before the skill is touched.** Three fixtures, their `evals.json` entries,
their `grade.py` checks, the `hidden/` mechanism, and per-case commit subjects in `prepare.py` so a
two-commit fixture no longer inherits `ledger-repo`'s messages.

**Phase 1 — the checklist cut**, snapshotting nothing: git holds the pre-edit file.

**Phase 2 — round 3.** Fresh workspace at `--iteration 3`, both arms, `--model claude-sonnet-5`,
`--runs 3` on eval 5. Six cases, so a full round is roughly double round 2's cost.

**Phase 3 — a fresh Haiku control.** The existing one measured the *unedited* skill, and its
headline result (+0.0pp net, `without_skill` winning verification waste 3/3) was caused by the
Verification block that round 2 removed. It is stale, it costs about $0.60, and it is the only
evidence available on whether Step 2's tables are dead weight or scaffolding a weaker model leans
on — which is the input to round 4's decision.

## What would falsify each part

- **The new cases have headroom** if `with_skill` scores below 100% on at least one of evals 3–5.
  A second consecutive 44/44-style sweep — now 86/86 — means these fixtures are no sharper than the
  first three and the next round has to change the model or the arms, not the rubric.
- **The scope case works** if the arms separate on "read the git history before changing anything"
  or on scope discipline. If the baseline reads `git log` unprompted the way it read `ledger-repo`'s
  `CLAUDE.md`, Principle 5 is confirmed as something the model already does, and the section should
  shrink to a line.
- **The weak-test case works** if any run fails the hidden suite. If both arms pass it 3/3, then
  "preserve behaviour exactly" is not a behaviour this skill has to teach on this model.
- **The "don't" case works** if it separates the arms. If both decline, "When NOT to use" is not
  load-bearing and is the next thing to cut; if neither declines, it is the most valuable section in
  the file and should be hardened.
- **The checklist cut was safe** if assertions 1, 2 and the dead-code checks hold at their round-2
  rates.

## The strategic read

After two rounds the skill's measured contribution on Sonnet is the diffstat habit plus, since
round 2, not hunting for linters the project never configured — bought at ~1.6× the baseline's
tokens. If these three cases still fail to separate the arms, the honest conclusion is that on this
model class the skill is about two instructions wearing an 11 KB coat, and round 4 should be a hard
cut rather than another tuning pass.
