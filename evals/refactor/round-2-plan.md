# Round 2 plan — acting on the round-1 findings

Round 1 scored 100% with the skill against 92% without, with the entire gap resting on one check.
This is the plan for the skill edits that follow from that, and for the round that measures them.
Read [benchmark.md](benchmark.md) for the numbers this reacts to and
[eval-approach.md](../eval-approach.md) for the rules it obeys.

## The three changes

**1. The Verification section is fitted to this repo, not the user's.** `SKILL.md` hardcodes
`.venv/bin/ruff check --fix skills/<skill>/scripts/` and `.venv/bin/pyright
skills/<skill>/scripts/<file>.py` — this marketplace's own paths, baked into a skill that ships as
a plugin into other repos. In `toolkit-repo`, which configures neither tool, it cost six trailing
Bash calls and a paragraph of reasoning about an irrelevant `ruff format --check` complaint: the
same one-line diff as the baseline for 430k tokens against 189k.

The literal command block is **deleted**, not genericised — a block of literal commands is what got
mimicked, and different literal commands invite the same failure. It becomes prose plus a discovery
order: `CLAUDE.md` → `README` → `pyproject.toml` / `package.json` → CI config, skipping whatever the
project does not configure.

**2. Roughly a fifth to a third of the body restates what the model already does.** Of Common
Rationalizations' seven rows, five restate Principles 3, 4, 5, Step 1 or Step 3. Of Red Flags'
seven bullets, six restate. Only two lines are unique anywhere in the file — *"don't remove error
handling because it makes the code cleaner"* and *"types document structure, not intent"* — and both
fold into Principles 1 and 2 as a line each.

Deleting all three sections is 19.8% of 14,040 characters. Reaching ~30% additionally requires
deduping the Verification checklist, which restates Principles 1, 2 and 5 as tickboxes.

**3. Harden the diffstat instruction only.** It was the sole check separating the arms, 3/3 against
0/3, and it is currently a soft paragraph at the end of Step 4.

The incrementality half of this change is **dropped**. Step 3 demonstrably already fires: 3 edits
and 3 test runs on `ledger-repo`, 3 and 2 on `pricing-repo`, against the baseline's 1 and 1.
Hardening an instruction that works only adds tokens.

## Decisions taken

| Decision | Choice | Why |
|---|---|---|
| Cut depth | Haiku control first, then cut | Whether the redundant prose is dead weight or scaffolding for weaker models is the one fact that decides this, and it costs ~$0.30 to learn |
| Cut rule | Haiku gap ≥ 15pp → cut to ~20%, else ~30% | Pre-committed, so the number cannot be rationalised after the fact. Roughly double Sonnet's 7.9pp |
| Rubric | v2: two new checks, all v1 checks kept, round 1 re-graded | Change 1 has no success metric under v1 — nothing could see the tool-hunting |
| Waste bar | At most one probe per absent tool | Discovering a tool is absent is fair; working through a checklist is not. A zero-call bar risks being a check nothing can satisfy |
| Arms | Two, compared against round 1 | Cheaper than a three-arm round. The risk it carries — model drift between rounds — is mitigated below |

## Sequence

**Phase 0 — rubric v2, before the skill is touched.** Two checks added to `grade.py`, both shared
across fixtures, inserted after assertion 8:

- *"No verification tool absent from the project was invoked more than once"* — Bash commands are
  matched against `ruff`/`pyright`/`mypy`/`black`/`eslint`/`prettier` and cross-checked against the
  fixture's config files.
- *"Changes were applied incrementally, with the suite run between them"* — mutation→verify cycles
  from `tool-calls.txt`. A run with fewer than two mutations passes outright, because
  `toolkit-repo`'s correct answer is a single edit and a floor demanding two cycles would fail the
  restraint case for being right.

Round 1's stored runs are re-graded under v2, their v1 gradings preserved as `grading-v1.json`.

**Phase 1 — Haiku control.** The three evals, both arms, on the *unedited* skill with
`--model claude-haiku-4-5-20251001`, graded under v2. Recorded as a labelled model control rather
than a round: its pass rates are not comparable to Sonnet's on the same axis.

**Phase 2 — the edits.** Changes 1, 2 and 3 above, at the depth the control dictates. The pre-edit
`SKILL.md` is snapshotted first.

**Phase 3 — round 2.** Fresh workspace at `--iteration 2`, both arms, `--model claude-sonnet-5`
pinned rather than the `sonnet` alias, so an alias repoint cannot silently confound the comparison.

## Known limitation

Round 1's `tool-calls.txt` records a bare `Bash` for every shell call — `_tool_summary` only began
capturing commands after that round. So the re-grade computes the incrementality check for round 1
(tool *names* are enough for that) but **cannot** compute the verification-waste check, which fails
there with `not computable — predates Bash command capture`. The denominator stays honest and the
check is not silently dropped, but change 1's "before" figure comes from the Haiku control and
round 2's baseline rather than from round 1.

## What would falsify each change

- **Change 1 worked** if `with_skill` invocations of unconfigured tools drop to ≤1 apiece and the
  `toolkit-repo` token premium narrows. It failed if tokens hold at ~2.3× the baseline.
- **Change 2 was safe** if the v1 checks stay at their round-1 pass rates. Any v1 check that
  regresses means the prose it removed was load-bearing after all.
- **Change 3 held** if the diffstat check stays at 3/3.
- **Drift did not confound the round** if `without_skill` scores within a point or two of round 1's
  86.4% under v2. A baseline that moves more than that means the cross-round comparison is the
  weak link, not the edit.
