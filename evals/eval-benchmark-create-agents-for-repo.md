# Eval benchmark — `create-agents-for-repo`

A dated record of what this skill scored, so a future round can be compared against it rather than
read in isolation. Append rounds; don't rewrite them. The harness that produces these numbers lives
in [evals/create-agents-for-repo/](../evals/create-agents-for-repo/) — read its
README before re-measuring.

Three evals, two arms each (`with_skill`, `without_skill`), one run per cell. One run per cell means
the token and time figures are single observations, not distributions: treat a 20% swing as noise.
Pass rates are the durable signal because they come from mechanical checks over the files on disk.

## Rubric versions

| Version | Assertions | Introduced |
|---|---|---|
| v1 | 10 (+2 on `reimport-repo`) | Round 1 |
| v2 | 15 (+2 on `reimport-repo`) | Round 2, and applied retroactively to round 1 |

v1 saturated on first contact — 100% with the skill against 97% without — so it measured almost
nothing. v2 keeps all ten v1 checks as a regression floor and adds five that target the judgement
the skill teaches: tier correctness, capped haiku agents, measured rather than estimated volumes, a
named concrete alternative for a rejected candidate, and exact commands in backticks.

v2 also fixed two defects in v1 that were inverting the signal, both worth remembering:

- **"Wrote at least one new agent" punished the correct answer** on `reimport-repo`, a fixture that
  already has four agents. Adding nothing and fixing the wiring is right there; the check now
  accepts a justified no-op.
- **Tier and phrasing checks graded runs on the fixture's own pre-existing agents.** Rewriting those
  is scope creep, so a run was being marked down for behaving well. They now apply only to agents a
  run authored or changed, computed by diffing against the fixture. `eval-2 with_skill` scored 76%
  before this fix and 94% after — same artifacts, same round.

Scores below are v2 throughout, including the round-1 column, which was re-graded from the stored
artifacts. Round 1's v1 gradings are preserved as `grading-v1.json` beside each run.

## Round 1 — 2026-08-09

Skill at commit `ac9f348`. Phase 2 candidate-hunting ran inline; there was no adversarial review
phase yet.

| Eval | Fixture | with_skill | without_skill |
|---|---|---|---|
| 0 unreferenced-agents | `rich-repo` | 80% (12/15) | 73% (11/15) |
| 1 no-skills | `bare-repo` | 93% (14/15) | 73% (11/15) |
| 2 after-reimport | `reimport-repo` | 94% (16/17) | 71% (12/17) |
| **Mean** | | **89%** | **72%** |

| Cost | with_skill | without_skill |
|---|---|---|
| Tokens, mean | 96,943 | 163,417 |
| Tokens, spread | 82.6k – 109.6k | 75.5k – 321.4k |
| Wall clock, mean | 520s | 434s |
| Tool calls, mean | 40 | 29 |

The token comparison does not say the skill is cheaper. One unaided run on `bare-repo` cost 321k
against a 75–110k band everywhere else, and that single outlier is what moves the mean. What the
numbers do show is **variance**: 13.5k standard deviation with the skill against 137k without. The
skill's value here is a bounded, predictable run, not a smaller one — and it buys that with about
20% more wall clock.

### What failed, with the skill

All three runs missed the same check: **no rejected candidate was replaced with a named concrete
alternative**. Runs said "not worth an agent" and moved on, where the useful output is "add `-q` to
the pytest line in CLAUDE.md instead". `eval-0` additionally estimated rather than measured its
candidate volumes, and left one authored Bash agent describing its command instead of naming it.

These are the three findings that shaped the next round of skill edits.

### Qualitative signal the rubric doesn't capture

Two behaviours separated the arms more sharply than any assertion:

- **Toolchain fitting.** Unaided runs wrote `mypy src/` into repos that use pyright, or `uv run`
  into a repo that has no uv. Assertion 7 catches the blatant cases; it does not catch a command
  that is merely unidiomatic for the repo.
- **Tier discipline.** Unaided runs reached for haiku on anything that sounded mechanical,
  including audit and review work where nothing downstream would catch a wrong answer. This became
  assertion 11.

## Round 2 — 2026-08-10

Skill after three additions to Phase 6: an explicit scope constraint ("touch only `.claude/` and
`CLAUDE.md`"), a toolchain-grep extended to authored agent bodies, and a revert instruction for
source-file changes produced during smoke-testing. Run via Copilot subagents in VS Code.

| Eval | Fixture | with_skill | without_skill |
|---|---|---|---|
| 0 unreferenced-agents | `rich-repo` | 93% (14/15) | 53% (8/15) |
| 1 no-skills | `bare-repo` | 93% (14/15) | 73% (11/15) |
| 2 after-reimport | `reimport-repo` | 82% (14/17) | 76% (13/17) |
| **Mean** | | **89.4%** | **68.1%** |

No timing data captured (subagent notifications unavailable in this environment).

### What failed, with the skill

All three runs touched source files despite the new scope constraint — the subagents ran commands
(tests, linters) that auto-fixed code and didn't revert. This is the same assertion-9 failure from
round 1, now joined by an explicit instruction the agent didn't follow. Strengthening the prose
further is unlikely to help; the next step is a tool restriction (`disallowedTools: Write`) on the
hunting subagents, or a post-phase `git checkout -- .` guard.

`eval-2` additionally let `mypy` appear in an authored agent body (toolchain contamination from the
fixture's own pre-existing agents which mention mypy in their history), and missed naming a concrete
simpler alternative in the proposal.

### What failed, without the skill

The baseline's failures cluster in the judgement assertions as expected:

- **Measured volumes** (assertion 13): 0/3 — no run actually counted lines before proposing.
- **Concrete simpler alternative** (assertion 14): 0/3 — rejections stated as "not worth it" with
  no named replacement.
- **Tier discipline** (assertion 11): `eval-0` miscast `content-audit` as haiku.
- **Haiku turn caps** (assertion 12): `eval-0` left 3 haiku agents uncapped.
- **Exact commands** (assertion 15): `eval-0`'s `build-green` described rather than named its
  command.

### Delta analysis

The +21pp aggregate gap is driven almost entirely by `eval-0` (+40pp), where the without_skill arm
wrote no new agents and miscast existing ones. `eval-2` showed the smallest gap (+6pp) — both arms
handled the "extend, don't clobber" situation adequately, differing only on proposal quality.
