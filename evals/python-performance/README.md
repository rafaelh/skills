# Eval harness for `python-performance`

Everything needed to re-measure this skill after editing it. An **artifact** suite in the sense of
[eval-approach.md](../eval-approach.md): a run rewrites source files in a staged repo, and the
rubric is computed from those files, their AST, the skill's own static checker run over the result,
and two pytest runs — the fixture's suite, and the one it deliberately does not ship. Results from
past rounds live in [benchmark.md](benchmark.md); compare against those rather than reading a new
score in isolation.

This is a developer harness. Nothing here ships as an agent tool; all three scripts are marked
`# agent-tool: false`, and `fixtures/` and `hidden/` are excluded from ruff, pyright and pytest in
the repo root config.

## Contents

| Path | What it is |
|---|---|
| `evals.json` | The four cases: prompt, fixture, target, mechanical assertions, judgement statements |
| `snapshots/` | Past `SKILL.md` bodies, for pointing an `old_skill` arm at the version a round measured |
| `fixtures/` | Four repos a run works on, each with a green test suite of its own |
| `hidden/` | Suites held back from a fixture, run by `grade.py` in a throwaway copy |
| `prepare.py` | Stages a workspace: fixture copies, `git init`, empty output dirs |
| `run_case.py` | Drives one staged run to completion and records what it left |
| `grade.py` | Scores one run against the assertions, writes `grading.json` |
| `benchmark.md` | Dated record of past rounds and rubric versions |

Like `refactor`, this suite drives its own runs rather than farming them to subagents: a
performance fix needs `Edit`, `Write` and `Bash` inside a throwaway copy, and `run_case.py` grants
exactly that under `--safe-mode` with `--permission-mode acceptEdits`, so a round is reproducible
from a shell and `timing.json` is captured rather than transcribed by hand.

One thing this suite does that `refactor` does not: `run_case.py` resolves `${SKILL_DIR}` in the
skill body to the real `skills/python-performance/` path before appending it. The skill's first
step is to run a bundled script, and Claude Code substitutes that notation from
`${CLAUDE_SKILL_DIR}` at trigger time — leaving the literal in would measure the arm's ability to
guess a path rather than its use of the tool.

## Why these four fixtures

Each one breaks a different step of the skill. All four ship green, and all four are plausibly
slow-looking; what separates them is where the time actually is.

| Fixture | Situation | The step it is there to break |
|---|---|---|
| `report-repo` | The nightly digest is quadratic three ways over, at 400k events a night | Step 1 into step 3. The findings are there to be found; the question is whether the fix is proved with numbers and whether the digest still says the same thing |
| `ingest-repo` | The CRM import doesn't finish, and static analysis says nothing at all | Step 2. Nothing is findable by reading; only a measurement points at the per-row scan |
| `tidy-repo` | A module review called "full of slow patterns", tripping five LOW findings and nothing else | Restraint. "Don't spend the user's time on LOW findings in code that isn't the bottleneck" — the failure here is a busy diff and an unmeasured speed claim |
| `logscan-repo` | The user has diagnosed it themselves, and is wrong | Whose evidence wins. The regex they blame is 0.2% of the run; the JSON re-parsed per line is the rest |

Each fixture plants three things a rubric can read:

- **Comments that explain *why*** — a FIFO the on-call rota depends on, a tie-break the digest bot
  diffs against, the merged-account rule the ledger reconciles on, the pre-2021 log layout three
  services still emit. These must survive, and in two cases they are also the only warning that the
  obvious fast rewrite changes behaviour.
- **A behavioural trap the shipped suite does not pin** — see below.
- **Something out of scope and tempting** — `exports.py`'s four LOW findings, `textutil.py`'s
  regexes on the hot path, `config/rules.json` (shrinking the input is a way to move the number
  without making the program faster).

### The traps, and where they live

`hidden/<fixture>/` holds the checks a run cannot see. `grade.py` copies them into a throwaway copy
of the run's repo *after* the run has finished; they are never staged into a fixture, because a run
that can read them has been handed the answer. Every one is reachable from the repo itself — from a
docstring, a comment, or the code being rewritten — so a run that reads before it rewrites keeps
them all.

- **`report-repo`** — the empty-night placeholder, unreportable kinds being skipped, the
  `unassigned` fallback, and the alphabetical tie-break in `top_services`. The last one is the
  sharp one: `Counter(...).most_common(n)` is the obvious fast rewrite and breaks ties by insertion
  order, which is exactly what the comment above the sort says not to do.
- **`ingest-repo`** — first-wins on a duplicated customer ref. The fast rewrite of a linear scan is
  a dict keyed on the ref, and `{c["ref"]: c for c in customers}` keeps the *last* record where the
  scan returned the first. `find_customer`'s docstring says which one billing reconciles against.
- **`logscan-repo`** — the level is the level field, not a word in the message; the long-form
  `WARNING` still counts; the pre-2021 layout without an instance id still matches. These are what
  a substring pre-filter or a "simplified" pattern breaks.

`tidy-repo` has no hidden suite: its correct answer changes nothing, so there is no behaviour to
preserve. Its floor is the summary instead — see the assertions below.

## Running a round

```bash
WS=~/.cache/claude-evals/python-performance   # outside this repo, and kept: a stored
PY=.venv/bin/python                           # workspace is what lets a later rubric re-grade

$PY evals/python-performance/prepare.py "$WS" --iteration 1
```

That prints the staged run directories as JSON — `$WS/iteration-1/eval-<id>-<name>/<arm>/run-1/`,
each with a git-initialised `repo/`, an empty `outputs/`, and the `eval_metadata.json` the runner
and grader both read.

```bash
find "$WS/iteration-1" -name eval_metadata.json -printf '%h\n' \
  | xargs -P 8 -L1 $PY evals/python-performance/run_case.py --model sonnet

find "$WS/iteration-1" -name eval_metadata.json -printf '%h\n' \
  | xargs -L1 $PY evals/python-performance/grade.py
```

Run `grade.py` sequentially: each call runs two pytest suites and the static checker, and one of
the fixtures' timing work is CPU-bound. `--no-judgement` drops the grader model and makes a round
fully deterministic — worth using when you are debugging a check rather than measuring a skill.

`run_case.py` takes one run directory and reads the arm and the case out of its
`eval_metadata.json`; `--arm` overrides it. It writes `outputs/summary.md` (the run's own
narration, which several assertions are graded from), `outputs/tool-calls.txt`, and `timing.json`.

Then

```bash
$PY evals/shared/aggregate.py "$WS/iteration-1"
```

prints the per-eval table, the checks that separated the arms, and the cost block as markdown,
ready to paste into `benchmark.md`. `--all-checks` includes the ones that moved nothing (the
regression floors), `--json` gives the same numbers for a script.

`--runs K` repeats every cell; `--arms with_skill,old_skill,without_skill` stages a third arm for
measuring an edit to the skill rather than the skill's existence, with `--skill` pointing that arm
at `snapshots/skill-v1.0-round-1.md` or another past body. As in `refactor`, `old_skill` needs
`--skill` and the other two must not get it, so a three-arm round runs in two passes rather than
one `xargs`:

```bash
find "$WS/iteration-2" -name eval_metadata.json -printf '%h\n' | grep -v /old_skill/ \
  | xargs -P 8 -L1 $PY evals/python-performance/run_case.py --model sonnet

find "$WS/iteration-2" -path '*/old_skill/*' -name eval_metadata.json -printf '%h\n' \
  | xargs -P 8 -L1 $PY evals/python-performance/run_case.py --model sonnet \
      --skill evals/python-performance/snapshots/skill-v1.0-round-1.md
```

A snapshot is a whole past `SKILL.md`, frontmatter included; `run_case.py` strips it and resolves
`${SKILL_DIR}` against the live `scripts/` either way, so an `old_skill` arm measures the prose
that changed rather than a stale copy of the checker.

Both arms get the identical preamble in `run_case.py`, and it is deliberately terse: where the
repo is, which interpreter to use, how to run the tests. It says nothing about checking, profiling
or proving a fix, because naming any of those hands the `without_skill` arm the behaviour being
measured.

## Reading the assertions

Two halves, as [eval-approach.md](../eval-approach.md) describes. The mechanical half is the floor
and costs nothing to re-run; the judgement half grades the write-up, which no regex reads fairly.

`grade.py` keys every check by its own assertion text and then takes the ones each case names in
`evals.json`. A rubric that has drifted from the code fails the run loudly (`grade.rubric.drift`)
rather than quietly grading something else.

**Shared mechanical checks.** Tests still pass; no shipped test file was modified; `perf_check.py`
ran before the first edit; a measurement was actually executed; the summary carries a before and an
after; files outside scope are byte-identical; every *why* comment survives; the target actually
changed.

Three of those carry the load:

- **"perf_check.py was run before the first edit"** is a floor for the skill arm, not a
  discriminator between arms: the baseline has no way to know the script exists, so it fails this
  by construction. What it catches is a `with_skill` run that skips its own step 1 — which is worth
  catching, because that is where a slow-looking file gets rewritten on instinct.
- **"A measurement was actually executed"** is the one the baseline can pass on its own, and the
  one worth watching. It reads `outputs/tool-calls.txt` for a profile or a timer, and — because a
  run that writes a timing script and then runs it shows only a file name in the call log — also
  reads any `.py` file the run added to the repo. That is why a leftover `bench.py` is not a scope
  violation: it is evidence.
- **"The target module actually changed"** is the floor under every "did not do X" check. Without
  it a run that did nothing scores well on restraint for free. `tidy-repo` is the one case that
  does not carry it, because its correct answer is a run that changed nothing — and for the same
  reason it does not carry the before-and-after check either. A single measured number is the right
  report when there is no "after".

**Per fixture.**

- `report-repo` — no HIGH finding remains in the target; the digest is joined once rather than
  accumulated with `+=`; the list is no longer drained from the front; the kind check is a set;
  the hidden suite passes.
- `ingest-repo` — the measurement came *before* the first edit (this is the case where guessing is
  the failure mode); the export is indexed once; `import_rows` no longer calls the per-row scan;
  the hidden suite passes.
- `tidy-repo` — at most 15 changed lines across `src/`; the summary says this module is not where
  the time goes; the summary quotes a concrete measured runtime; no new module under `src/`. This
  is the only case where a *smaller* diff scores better.
- `logscan-repo` — the measurement came before the first edit; the rules file is read once rather
  than per line; **`LINE_RE`'s pattern is byte-identical**; the summary says the regex is not where
  the time goes; the hidden suite passes.

Every check reports what it matched, pass or fail, because every one is a proxy. The *why*-comment
checks anchor on the load-bearing phrase (`first event of the night`, `superseded`, `pre-2021`)
rather than the whole sentence, so a faithful reword still counts as preserved. The prose checks
("not where the time goes") match a bank of registers rather than one phrasing; widening one can
only turn a fail into a pass, which is what keeps earlier rounds comparable.

**Judgement checks** are graded by a model from the run's final summary alone — no diff, no tool
calls, no arm label — because what they ask is whether the write-up would convince the person who
asked. Three or four per case. Two are shared:

- *Every speed claim has a measured number beside it.* The grader is told a number counts only
  when the write-up says what was measured and at what input size, so "roughly 100x faster" on its
  own fails.
- *The run says how it knows the code still returns the same answers* — on the three cases that
  change something. This is the judgement half of what the hidden suites grade mechanically: a run
  can pass the hidden suite by luck, and this asks whether it had a reason to expect to.

The rest are per case: whether the measurement was taken at a size where the claimed effect is
visible, whether the run resisted rewriting LOW findings to look busy, whether it told the user
their hypothesis was wrong.

## When you change the skill

Add assertions rather than rewriting them, and note the change in [benchmark.md](benchmark.md)
alongside the scores. A rubric edited between rounds makes the two rounds incomparable. If a check
passes in both arms across a round it has stopped measuring — leave it as a regression floor and
add a sharper one beside it.

Editing a fixture invalidates every earlier round: the traps, the frozen files and `tidy-repo`'s
15-line budget are all measured against the fixture as it ships. Prefer adding a case.

Two things about this suite in particular:

- **`grade.py` calls the skill's own `perf_check.py`** for `report-repo`'s severity check. That is
  an outcome measure — a HIGH finding is a quadratic shape, whoever spots it — but it does mean a
  change to the checker's categories can move a score without the skill's prose changing. The three
  rewrite checks beside it are computed from the source directly for exactly that reason.
- **`report-repo` writes its membership test as `in [...]`, not `not in [...]`.** The natural way
  to write that filter is the negated form, and it is there in the positive form because
  `perf_check.py` did not flag `not in` when the fixture was built — a gap this suite found, fixed
  in skill v1.1. The fixture stays as it is: editing it would make round 1 a different experiment.
- **The fixtures are sized so a run can measure them.** `ingest-repo` at the scale the prompt
  describes would take half an hour per timing run; at 5k rows against 20k customers it is 0.8s and
  still obviously quadratic. A run picking a tractable slice is doing the right thing, and the
  judgement check about input size is what grades whether it picked a fair one.
