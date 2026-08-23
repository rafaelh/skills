# Eval harness for `refactor`

Everything needed to re-measure this skill after editing it. An **artifact** suite in the sense of
[eval-approach.md](../eval-approach.md): a run rewrites source files in a staged repo, and the
rubric is computed from those files, their AST, and one run of the fixture's own test suite.
Results from past rounds live in [benchmark.md](benchmark.md) — compare against those rather than
reading a new score in isolation.

This is a developer harness. Nothing here ships as an agent tool; all three scripts are marked
`# agent-tool: false`, and `fixtures/` is excluded from ruff, pyright and pytest in the repo root
config.

## Contents

| Path | What it is |
|---|---|
| `evals.json` | The three cases: prompt, fixture, target, and the assertion list |
| `fixtures/` | Three repos a run refactors, each with a green test suite of its own |
| `prepare.py` | Stages a workspace: fixture copies, `git init`, empty output dirs |
| `run_case.py` | Drives one staged run to completion and records what it left |
| `grade.py` | Scores one run against the assertions, writes `grading.json` |
| `benchmark.md` | Dated record of past rounds and rubric versions |

Unlike `create-agents-for-repo`, this suite drives its own runs rather than farming them to
subagents. A refactor run needs `Edit`, `Write` and `Bash` inside a throwaway copy, and
`run_case.py` grants exactly that under `--safe-mode` with `--permission-mode acceptEdits`, so a
round is reproducible from a shell and `timing.json` is captured rather than transcribed by hand.

## Why these three fixtures

Each one puts a different principle under load. All three ship green.

| Fixture | Situation | The principle it is there to break |
|---|---|---|
| `pricing-repo` | `quote()` is 83 lines, seven deep, with a copy-pasted accumulation loop | Do the work: untangle it without changing behaviour, keep the *why* comments, leave the frozen invoice renderer beside it alone |
| `toolkit-repo` | A package that is already close to clean | Restraint. "Don't simplify for the sake of it" — the failure here is churn, not sloppiness |
| `ledger-repo` | Three equally ugly modules, one of which landed in the last commit | Scope to what changed. `git log` is the only thing separating `reconcile.py` from `posting.py` |

`ledger-repo` is the reason `prepare.py` builds two commits instead of one: the case's
`recent_files` land in the second, so a run told to tidy "the last thing I committed" has to look
the answer up. The other two fixtures get a single commit.

Each fixture plants three things a rubric can read:

- **Comments that explain *why*** — a rounding incident, an unvalidated CRM import, a tie-break
  finance depends on. These must survive. `pricing-repo` also plants five that merely narrate the
  next line, and at least two of those must go.
- **A behavioural trap the tests pin** — coupon tie-break order, the inclusive date window,
  `_sleep` as a monkeypatched seam. A run that "simplifies" one of these turns the suite red.
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

Eight apply everywhere, then four or five per fixture. Every check is mechanical; there is no
grader model in this suite, because files answer these questions on their own.

**Shared (1–8).** Tests still pass; no test file was edited; the target actually changed; no
f-string logging call appeared; every *why* comment survived; nothing outside scope moved; no
nested ternary remains; the summary reports both an added and a deleted line count.

Two of those carry the load. **Assertion 3 is the floor** — without it, every "did not do X" check
below passes for free for a run that did nothing, which on `toolkit-repo` is otherwise worth 10 of
13. **Assertion 8 wants both halves**: a run reporting only what it added has dodged exactly the
question the skill's instruction asks.

**Per fixture.**

- `pricing-repo` — depth and function length both came down against the measured baseline (7 deep,
  83 lines); `_legacy_round` and the unused `math` import are gone; the duplicated accumulation
  loop appears once; at least two of the five narrating comments were deleted; no `float()`.
- `toolkit-repo` — at most 60 changed lines across `src/`; no public function renamed or removed;
  the `_sleep` seam not inlined; no new module invented; the summary names something it
  deliberately left unchanged. This is the only case where a *smaller* diff scores better.
- `ledger-repo` — depth and length down against 7 and 39; the abandoned `_collect` helper gone; the
  hand-rolled `x = -x` block no longer repeated four times; no `float()`.

Every check reports what it matched, pass or fail, because every one is a proxy. The *why*-comment
checks anchor on the load-bearing phrase (`off-by-one-cent`, `posting order`) rather than the whole
sentence, so a faithful reword still counts as preserved. The duplication checks anchor on a log
string and a syntactic idiom, so renaming variables does not fake a pass.

## When you change the skill

Add assertions rather than rewriting them, and note the change in [benchmark.md](benchmark.md)
alongside the scores. A rubric edited between rounds makes the two rounds incomparable. If a check
passes in both arms across a round it has stopped measuring — leave it as a regression floor and
add a sharper one beside it.

The baselines in `grade.py` (`PRICING_BASELINE`, `LEDGER_BASELINE`, `TOOLKIT_DIFF_BUDGET`) are
measured from the untouched fixtures. Editing a fixture invalidates them and makes every earlier
round a different experiment — prefer adding a fourth case.
