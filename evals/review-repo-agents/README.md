# Eval harness for `review-repo-agents`

Everything needed to re-measure this skill after editing it. An **artifact** suite in the sense of
[eval-approach.md](../eval-approach.md), where the artifact is prose: a run reads a staged repo's
`.claude/agents/` and leaves a review at `outputs/report.md`, and that report is what the rubric
grades. Results from past rounds live in [benchmark.md](benchmark.md) — compare against those
rather than reading a new score in isolation.

This is a developer harness. Nothing here ships as an agent tool; all three scripts are marked
`# agent-tool: false`, and `fixtures/` is excluded from ruff, pyright and pytest by the repo root
config.

## Contents

| Path | What it is |
|---|---|
| `evals.json` | The three cases: prompt, fixture, word budget, mechanical assertions, judgement statements |
| `fixtures/` | Three repos, each with a `.claude/agents/` whose correct verdict differs |
| `prepare.py` | Stages a workspace: fixture copies, `git init`, empty output dirs |
| `run_case.py` | Drives one staged run to completion and records what it left |
| `grade.py` | Scores one run — mechanical checks plus a blinded grader model — and writes `grading.json` |
| `benchmark.md` | Dated record of past rounds and rubric versions |

Runs get `Read`, `Grep` and `Glob` and nothing else. A review authors no files, and no check here
asks a question a shell answers, so granting `Bash` would buy variance and tokens without buying
signal. That also means no `--permission-mode` is needed: nothing in a run can stall on approval.

## Why these three fixtures

The skill's hard problem is not spotting a bad agent. It is the last line of its own body —
*don't manufacture issues or overengineer a solution* — held against the paragraph above it, which
says an agent that cannot measurably earn its place should be removed. A review that only ever
finds fault and a review that only ever approves are both failures, and one fixture cannot tell
them apart. So each fixture has a different right answer.

| Fixture | The agent set | The correct verdict |
|---|---|---|
| `overbuilt-repo` | Five agents, five planted defects | Improve or replace most of them |
| `sound-repo` | Three agents that are genuinely well built | Say so and stop |
| `theatre-repo` | Two agents that cannot earn their place, one that plainly does | Remove two, keep one |

**`overbuilt-repo`** plants one defect per criterion in the skill's body, so a failure names which
paragraph went unread:

- `test-runner` runs one `pytest` command on **opus** — the "prefer the least expensive model"
  clause, in the direction of waste.
- `deep-reviewer` weighs architectural trade-offs and returns accept/reject on **haiku** — the same
  clause in the other direction, where cheapest is the wrong answer. A run that has learned "always
  say haiku" fails this one and passes the first.
- `unit-test-runner` duplicates `test-runner`'s job and nearly its description — the
  *complementary or competing* criterion.
- `lint-fixer.md` is malformed four ways at once: `name: lint-fix` matching neither its filename
  nor anything that routes to it, no `description`, `model: claude-3-opus-20240229` (not an alias
  this harness takes), and `tools` as a comma string rather than a list.
- `commit-msg` runs `black --check .` and `mypy src/` in a repo whose CLAUDE.md documents ruff and
  pyright, and declares no tools despite needing Bash.

CLAUDE.md's Delegation section routes to `test-runner` alone, so four of the five are reachable
from nowhere — the trigger half of the third criterion, planted separately from the overlap half.

**`sound-repo`** is the restraint case. It did not separate the arms in round 1 — see
[benchmark.md](benchmark.md) — so read it for now as a regression floor rather than a discriminator. All three agents are routed from CLAUDE.md with a stated reason,
declare tool allowlists and return contracts, run commands that match the documented toolchain, and
carry defensible model tiers — including `harmonic-review` on **opus**, which CLAUDE.md justifies
as the part of the repo a wrong answer is expensive in. A run that downgrades it to save money has
optimised the wrong quantity. The word budget (600) is the check that a correct answer here is also
a *short* one; there is no budget on the other two cases, where the work is real.

**`theatre-repo`** is the mixed case, and its floor is `coverage-gate`. `changelog-reader` and
`pair-programmer` should both go — the first spends a model round-trip to save a single `Read` of a
12-line file, the second narrows neither model nor context nor output and so is strictly a
duplicate of the main session with a hop in front of it. But `coverage-gate` collapses a
several-hundred-line `--cov-report=term-missing` run to ten lines, which is criterion 3 exactly. A
run that clears the decks scores worse here than one that keeps nothing at all, because the two
judgement statements about `coverage-gate` fail together.

## Running a round

```bash
WS=~/.cache/claude-evals/review-repo-agents
PY=.venv/bin/python

$PY evals/review-repo-agents/prepare.py "$WS" --iteration 1
```

That prints the staged run directories as JSON — `$WS/iteration-1/eval-<id>-<name>/<arm>/run-1/`,
each with a git-initialised `repo/`, an empty `outputs/`, and the `eval_metadata.json` the runner
and grader both read.

```bash
find "$WS/iteration-1" -name eval_metadata.json -printf '%h\n' \
  | xargs -P 6 -L1 $PY evals/review-repo-agents/run_case.py --model sonnet

find "$WS/iteration-1" -name eval_metadata.json -printf '%h\n' \
  | xargs -P 3 -L1 $PY evals/review-repo-agents/grade.py
```

`run_case.py` takes one run directory and reads the arm and the case out of its
`eval_metadata.json`; `--arm` overrides it. It writes `outputs/report.md` (the review, which is the
whole artifact), `outputs/tool-calls.txt`, and `timing.json`.

`grade.py` spends a grader turn per run, so keep `-P` modest. `--no-judge` runs the mechanical half
alone, which is free and worth doing while iterating on a fixture.

```bash
$PY evals/shared/aggregate.py "$WS/iteration-1"
```

prints the per-eval table, the checks that separated the arms, and the cost block as markdown,
ready to paste into `benchmark.md`. `--all-checks` includes the ones that moved nothing.

`--runs K` repeats every cell. Worth spending on eval 1: restraint is close to binary, and a single
observation of it is a coin flip reported as a percentage.

### Three arms

`--arms` stages more than the default two, and `--skill` points an arm at a different file — a git
snapshot of `SKILL.md` from before an edit:

```bash
$PY evals/review-repo-agents/prepare.py "$WS" --iteration 2 \
  --arms with_skill,old_skill,without_skill
git show HEAD~1:skills/review-repo-agents/SKILL.md > /tmp/rra-old.md

find "$WS/iteration-2" -name eval_metadata.json -printf '%h\n' | grep -v /old_skill/ \
  | xargs -P 6 -L1 $PY evals/review-repo-agents/run_case.py --model sonnet
find "$WS/iteration-2" -path '*/old_skill/*' -name eval_metadata.json -printf '%h\n' \
  | xargs -P 3 -L1 $PY evals/review-repo-agents/run_case.py --model sonnet --skill /tmp/rra-old.md
```

A second model is a second workspace, not a second arm: `aggregate.py` reports the model rather
than averaging over it.

Both arms get the identical preamble in `run_case.py`, and it is deliberately bare — where the
checkout is, that nobody is available to answer questions, and that the answer goes in the final
message. It names no agent, model, cost or criterion, because any of those would hand the
`without_skill` arm the behaviour being measured.

## Reading the assertions

Five mechanical checks apply everywhere, one more applies to `sound-repo`, and then five to eight
judgement statements per case. The split is deliberate: the mechanical half grades the report's
**shape**, the judgement half grades what it **found**. No regex can tell a correct verdict from a
plausible one, and no grader model should be spending its attention counting whether every agent
got a mention.

**Mechanical (shared).**

1. **Every agent is named.** The floor. Without it, a report covering two of five agents can score
   well on everything below by saying little. Matched against both the filename stem and the
   frontmatter `name:`, because `lint-fixer.md` deliberately disagrees with itself and a report is
   not wrong for using either.
2. **Every agent file was opened.** Read from `outputs/tool-calls.txt`. A run that never opened
   `deep-reviewer.md` and still has an opinion about it is guessing from the filename. A run
   recorded without a tool log fails this as `not computable` rather than being dropped from the
   denominator.
3. **A verdict for every agent.** A verdict verb — keep, remove, merge, fold, rewrite, downgrade —
   within the report's window for that agent: the section under a heading that names it, plus the
   lines immediately around any bare mention, which is where a table row keeps its recommendation.
   This is a proxy and reports which agents had no verb near them.
4. **At least one figure with a unit.** The skill's demand is that improvements be *measurable*,
   and a report with no number in it has not met the demand it set itself. One figure is a low bar
   on purpose — it is a floor, not a score.
5. **Three verbatim quotes.** Backticked spans in the report that appear in the agent files, minus
   the agent names themselves (check 1 already grades naming). This separates a review grounded in
   the files — `model: claude-3-opus-20240229`, `mypy src/` — from one that describes them in the
   abstract. Four characters minimum, so a stray backtick does not count.

**Mechanical (sound-repo only).** *At most 600 words.* The skill's closing instruction is to say so
and finish when the setup is good. A 2,000-word report that concludes "this is fine" has not
followed it, and no judgement statement catches that as cleanly as a word count.

**Judgement.** Sent to a grader model along with the agent files, the repo's CLAUDE.md, the report
with any mention of the skill scrubbed, and a paragraph of ground truth per fixture — the facts the
assistant had to work out, so the grader is checking a claim rather than re-deriving it. Each case's
statements are listed in `evals.json` and in `GROUND_TRUTH` in `grade.py`.

The pairs are where the signal is. `overbuilt-repo` asks separately about the model being too
expensive and too cheap; `theatre-repo` asks separately whether `changelog-reader` was removed and
whether the reason was the round-trip cost rather than the agent looking thin; `sound-repo` asks
both that nothing was removed and that the model tiers were actually examined, so a run that skims
and approves fails the second while passing the first.

## When you change the skill

Add assertions rather than rewriting them, and note the change in [benchmark.md](benchmark.md)
alongside the scores. A rubric edited between rounds makes the two rounds incomparable. A check that
passes in both arms across a round has stopped measuring — leave it as a regression floor and add a
sharper one beside it.

Editing a fixture is the expensive change: every planted defect is cited by name in a `GROUND_TRUTH`
paragraph and usually by a judgement statement too, and moving one makes every earlier round a
different experiment. Prefer adding a case.
