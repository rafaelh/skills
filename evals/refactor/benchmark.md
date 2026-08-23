# Eval benchmark — `refactor`

A dated record of what this skill scored, so a future round can be compared against it rather than
read in isolation. Append rounds; don't rewrite them. The harness that produces these numbers lives
beside this file — read [README.md](README.md) before re-measuring.

Three evals, two arms each (`with_skill`, `without_skill`), one run per cell. One run per cell means
the token and time figures are single observations, not distributions: treat a 20% swing as noise.
Pass rates are the durable signal because every check is mechanical — files on disk, their AST, and
one run of the fixture's own test suite.

## Rubric versions

| Version | Assertions | Introduced |
|---|---|---|
| v1 | 8 shared + 5 (`pricing`), 5 (`toolkit`), 4 (`ledger`) | Round 1 |
| v2 | 10 shared + the same per-fixture sets | Round 2, applied retroactively to round 1 |

v1 saturated on first contact — 100% against 92%, with the entire gap resting on one check — so it
measured almost nothing. v2 keeps all thirteen v1 checks as a regression floor and adds two that
read `outputs/tool-calls.txt` rather than the repo: **verification waste** (a tool the project does
not configure, invoked more than once) and **incrementality** (mutation→verify cycles, with runs of
fewer than two mutations passing outright so `toolkit-repo`'s correct single-edit answer is not
punished).

Round 1's v1 gradings are preserved as `grading-v1.json` beside each run. Under v2 round 1 becomes
**93.2% with the skill against 86.4% without**.

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
