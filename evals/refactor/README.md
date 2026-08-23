# Eval harness for `refactor`

Everything needed to re-measure this skill after editing it. An **artifact** suite in the sense of
[eval-approach.md](../eval-approach.md): a run rewrites source files in a staged repo, and the
rubric is computed from those files, their AST, and one run of the fixture's own test suite.
Results from past rounds live in [benchmark.md](benchmark.md) — compare against those rather than
reading a new score in isolation.

This is a developer harness. Nothing here ships as an agent tool; all three scripts are marked
`# agent-tool: false`, and `fixtures/` and `hidden/` are excluded from ruff, pyright and pytest in
the repo root config.

## Contents

| Path | What it is |
|---|---|
| `evals.json` | The six cases: prompt, fixture, target, and the assertion list |
| `fixtures/` | Six repos a run refactors, each with a green test suite of its own |
| `hidden/` | Suites held back from a fixture, run by `grade.py` in a throwaway copy |
| `prepare.py` | Stages a workspace: fixture copies, `git init`, empty output dirs |
| `run_case.py` | Drives one staged run to completion and records what it left |
| `grade.py` | Scores one run against the assertions, writes `grading.json` |
| `benchmark.md` | Dated record of past rounds and rubric versions |

Unlike `create-agents-for-repo`, this suite drives its own runs rather than farming them to
subagents. A refactor run needs `Edit`, `Write` and `Bash` inside a throwaway copy, and
`run_case.py` grants exactly that under `--safe-mode` with `--permission-mode acceptEdits`, so a
round is reproducible from a shell and `timing.json` is captured rather than transcribed by hand.

## Why these six fixtures

Each one puts a different principle under load. All six ship green. The first three are round 1's;
the last three were added in round 3, once `with_skill` reached 44/44 and the rubric ran out of
headroom.

| Fixture | Situation | The principle it is there to break |
|---|---|---|
| `pricing-repo` | `quote()` is 83 lines, seven deep, with a copy-pasted accumulation loop | Do the work: untangle it without changing behaviour, keep the *why* comments, leave the frozen invoice renderer beside it alone |
| `toolkit-repo` | A package that is already close to clean | Restraint. "Don't simplify for the sake of it" — the failure here is churn, not sloppiness |
| `ledger-repo` | Three equally ugly modules, one of which landed in the last commit | Scope to what changed. `git log` is the only thing separating `reconcile.py` from `posting.py` |
| `inventory-repo` | Same shape as `ledger-repo`, with the prose signal removed and the ugliness inverted | Scope to what changed, for real this time — see below |
| `digest-repo` | `format_digest()` is nested and cryptic, and its suite tests the happy path only | Preserve behaviour exactly, when a green suite is not evidence that you did |
| `resample-repo` | The ugliest module in the repo is the one being replaced | "When NOT to use". The correct answer is to decline and say why |

`ledger-repo`, `inventory-repo` and `resample-repo` are the reason `prepare.py` builds two commits
instead of one: the case's `recent_files` land in the second, so a run told to tidy "the last thing
I committed" has to look the answer up. Each such case carries its own `history_messages`, because
the subject lines are part of what a run reads. The other fixtures get a single commit.

### What the three round-3 fixtures fix

`ledger-repo` leaks: its `CLAUDE.md` labels `posting.py` *"Stable since 2021"* and `export.py`
*"Frozen"*, so a run can read scope off the prose, and round 1's baseline did. **`inventory-repo`**
says nothing about module state, its prompt names no file, and `stocktake.py` — which is out of
scope — is measurably uglier than `restock.py`, which is in it (depth 8 and 45 lines against 6 and
33). Ugliness points away from the answer; only `git log` points at it.

**`digest-repo`** is the case a passing test suite cannot answer. Four behaviours are load-bearing
and untested: the sort-then-reverse tie order, `limit=0` as a no-limit sentinel that `daily.py`
depends on, the no-updates placeholder, and whitespace collapsing inside a subject. Each is
reachable — from the caller, from the docstring, or from reading the code before rewriting it — but
none of them from running pytest. The checks live in `hidden/digest-repo/`, which `grade.py` copies
into a throwaway copy of the run's repo *after* the run has finished. It is never staged into the
fixture: a run that can read it has been handed the answer.

**`resample-repo`** is the only case whose correct answer is to change nothing. `resample_v2.py`
landed in the last commit, its docstring says it replaces `resample.py` once `exports.py` moves,
and the prompt pushes hard the other way. Migrating the last caller would also score badly here,
and deliberately: it is a rewrite the user did not ask for, which Principle 5 rules out as firmly
as the wasted cleanup does.

Each fixture plants three things a rubric can read:

- **Comments that explain *why*** — a rounding incident, an unvalidated CRM import, a tie-break
  finance depends on. These must survive. `pricing-repo` also plants five that merely narrate the
  next line, and at least two of those must go.
- **A behavioural trap** — coupon tie-break order, the inclusive date window, `_sleep` as a
  monkeypatched seam. A run that "simplifies" one of these turns the suite red, except in
  `digest-repo`, where the traps are the ones the suite does *not* pin.
- **A conventions section in `CLAUDE.md`** — `Decimal` not `float`, `%s` logging not f-strings.
  Both are graded, because imposing external preferences is churn, not simplification.

## Running a round

```bash
WS=/tmp/refactor-ws                   # anywhere outside this repo
PY=.venv/bin/python                   # needs pytest — grade.py runs the fixture suites

$PY evals/refactor/prepare.py "$WS" --iteration 2
```

That prints the staged run directories as JSON — `$WS/iteration-2/eval-<id>-<name>/<arm>/run-1/`,
each with a git-initialised `repo/`, an empty `outputs/`, and the `eval_metadata.json` the runner
and grader both read.

```bash
find "$WS/iteration-2" -name eval_metadata.json -printf '%h\n' \
  | xargs -P 6 -L1 $PY evals/refactor/run_case.py --model sonnet

find "$WS/iteration-2" -name eval_metadata.json -printf '%h\n' \
  | xargs -L1 $PY evals/refactor/grade.py
```

`run_case.py` takes one run directory and reads the arm and the case out of its
`eval_metadata.json`; `--arm` overrides it, which is how an `old_skill` arm against a snapshot is
run. It writes `outputs/summary.md` (the run's own narration, which assertion 8 is graded from),
`outputs/tool-calls.txt`, and `timing.json`.

Grade sequentially rather than with `-P`: `grade.py` runs a pytest suite per call.

Both arms get the identical preamble in `run_case.py`, and it is deliberately terse. It says where
the run is and how to invoke pytest, and nothing about diffstats, scope or restraint — naming any
of those would hand the `without_skill` arm the behaviour being measured.

## Reading the assertions

Ten apply everywhere, then five per fixture. Every check is mechanical; there is no grader model in
this suite, because files answer these questions on their own.

**Shared (1–10).** Tests still pass; no test file was edited; the target actually changed; no
f-string logging call appeared; every *why* comment survived; nothing outside scope moved; no
nested ternary remains; the summary reports both an added and a deleted line count; no tool the
project does not configure was invoked more than once; changes were applied incrementally.

Two of those carry the load. **Assertion 3 is the floor** — without it, every "did not do X" check
below passes for free for a run that did nothing, which on `toolkit-repo` is otherwise worth 10 of
13. **Assertion 8 wants both halves**: a run reporting only what it added has dodged exactly the
question the skill's instruction asks.

`resample-repo` is the one fixture that skips shared checks — 3, 8 and 10, named in its `Spec.skip`.
All three presume a run that changed something, and its correct answer is a run that did not. Its
floor moves to the summary checks below: a run that quietly does nothing and says nothing scores
worse than one that declines and explains.

Assertions 9 and 10 arrived in rubric v2, after v1 saturated in round 1. Both read
`outputs/tool-calls.txt` rather than the repo:

- **9, verification waste** cross-checks Bash commands against the fixture's config files. One probe
  per absent tool is fine — discovering `ruff` is not set up is reasonable; working through a
  checklist of five is the behaviour that cost `toolkit-repo`'s run 2.3× the baseline's tokens for
  an identical one-line diff. Runs recorded before `_tool_summary` captured Bash commands fail this
  with `not computable`, rather than being quietly dropped from the denominator.
- **10, incrementality** counts mutation→verify cycles. A run with fewer than two mutations passes
  outright: `toolkit-repo`'s correct answer *is* one edit, and a floor demanding two cycles would
  fail the restraint case for being right. This one is a guard, not a discriminator — it passed in
  both arms in round 1, and its job is to catch a regression if the skill's Step 3 is ever trimmed.

**Per fixture.**

- `pricing-repo` — depth and function length both came down against the measured baseline (7 deep,
  83 lines); `_legacy_round` and the unused `math` import are gone; the duplicated accumulation
  loop appears once; at least two of the five narrating comments were deleted; no `float()`.
- `toolkit-repo` — at most 60 changed lines across `src/`; no public function renamed or removed;
  the `_sleep` seam not inlined; no new module invented; the summary names something it
  deliberately left unchanged. This is the only case where a *smaller* diff scores better.
- `ledger-repo` — depth and length down against 7 and 39; the abandoned `_collect` helper gone; the
  hand-rolled `x = -x` block no longer repeated four times; no `float()`.
- `inventory-repo` — depth and length down against 6 and 33; the dead `_totals` helper gone; the
  pack-rounding block that `plan()` and `top_up()` both carry appears once; no `float()`; and **the
  git history was read before the first edit**. That last one is new in v3 and is the case's point:
  nothing else in the repo says which module is in scope.
- `digest-repo` — **the hidden suite passes**; depth and length down against 6 and 43; the dead
  `_initials` helper gone; the shared subject-normalisation block appears once; a caller of the
  target was read before the first edit.
- `resample-repo` — at most 15 changed lines in `resample.py`; the summary says the module is being
  replaced rather than refactored; the summary names `resample_v2`; the replacement module was read
  before deciding; no new module under `src/`. The budget is not zero, because deleting the dead
  `thumbnail()` wrapper is a defensible tidy and a zero-line bar would measure tidiness rather than
  restraint.

The two "read it first" checks (`inventory-repo`, `digest-repo`) and `resample-repo`'s all use the
same rule: evidence found *after* the first `Edit` or `Write` does not count, because Step 1's
questions are the ones that decide whether there is anything to do. A run that never mutates is
graded on its whole call list — the only reading under which a correct refusal can pass.

Every check reports what it matched, pass or fail, because every one is a proxy. The *why*-comment
checks anchor on the load-bearing phrase (`off-by-one-cent`, `posting order`) rather than the whole
sentence, so a faithful reword still counts as preserved. The duplication checks anchor on a log
string and a syntactic idiom, so renaming variables does not fake a pass.

## When you change the skill

Add assertions rather than rewriting them, and note the change in [benchmark.md](benchmark.md)
alongside the scores. A rubric edited between rounds makes the two rounds incomparable. If a check
passes in both arms across a round it has stopped measuring — leave it as a regression floor and
add a sharper one beside it.

The baselines in `grade.py` (`PRICING_BASELINE`, `LEDGER_BASELINE`, `RESTOCK_BASELINE`,
`DIGEST_BASELINE`, `TOOLKIT_DIFF_BUDGET`, `RESAMPLE_DIFF_BUDGET`) are measured from the untouched
fixtures. Editing a fixture invalidates them and makes every earlier round a different experiment —
prefer adding a case, which is what round 3 did.

A new shared check is the expensive kind of change: rounds 1 and 2 left no stored workspaces, so
they cannot be re-graded, and a check that applies to the original three fixtures would break the
comparison with them permanently. v3's new checks are per-fixture, on the new fixtures only, which
is why the ten shared checks still read exactly as they did in round 2.
