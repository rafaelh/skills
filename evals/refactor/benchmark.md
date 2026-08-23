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
