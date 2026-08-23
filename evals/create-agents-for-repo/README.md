# Eval harness for `create-agents-for-repo`

Everything needed to re-measure this skill after editing it. An **artifact** suite in the sense of
[eval-approach.md](../eval-approach.md): a run leaves files in a staged repo, and the rubric is
computed from those files. Results from past rounds live in [benchmark.md](benchmark.md) — compare
against those rather than reading a new score in isolation.

This is a developer harness. Nothing here ships as an agent tool; `grade.py` and `prepare.py` are
both marked `# agent-tool: false`, and `fixtures/` is excluded from ruff, pyright, pytest and
pre-commit in the repo root config.

## Contents

| Path | What it is |
|---|---|
| `evals.json` | The three eval cases: prompt, fixture, and the assertion list |
| `fixtures/` | Three target repos the skill runs against |
| `prepare.py` | Stages a workspace: fixture copies, `git init`, empty output dirs |
| `grade.py` | Scores one run against the assertions, writes `grading.json` |
| `benchmark.md` | Dated record of past rounds and rubric versions |

## Why these three fixtures

All three are snapshots of the same project at different stages of adopting delegation, which is
what makes them discriminating — the skill has to notice *which* situation it is in.

| Fixture | Situation | What it tests |
|---|---|---|
| `rich-repo` | Skills present, four agents on disk, none referenced from anywhere | Finds the orphans; toolchain is uv/pytest/ruff/**pyright** |
| `bare-repo` | No skills, no agents, commands documented only in CLAUDE.md | Lens B alone; toolchain is pytest/ruff/**mypy**, no `uv run` |
| `reimport-repo` | Has a `## Delegation` table and four agents already | Extends rather than replaces; adding nothing is a valid answer |

The type checker differs deliberately between `bare-repo` and the other two. An agent that writes
`pyright` into `bare-repo` was working from a template instead of reading the repo, and `grade.py`
fails it for that.

Fixtures ship without their `.git` directories; `prepare.py` runs `git init` and one commit on each
copy, because `scan_delegation_targets.py` shells out to git.

## Running a round

```bash
WS=/tmp/cafr-ws                       # anywhere outside this repo

python3 evals/create-agents-for-repo/prepare.py "$WS" --iteration 2
```

That prints the staged run directories as JSON —
`$WS/iteration-2/eval-<id>-<name>/<arm>/run-1/`, each with a git-initialised `repo/`, an empty
`outputs/`, and the `eval_metadata.json` the grader later reads.

Then launch six subagents **in the same turn** — one `with_skill` and one `without_skill` per eval.
Each gets the eval's `prompt` verbatim, the path to its own `run-1/repo` as the only directory it
may touch, and instructions to save `proposal.md`, `summary.md`, `agents/` and `CLAUDE.md` into its
`run-1/outputs/`. The with-skill arm additionally gets the skill path and is told to write its
proposal to disk and proceed as though approved, since no user is available to approve it.

Capture `total_tokens` and `duration_ms` from each completion notification into that run's
`timing.json` as they arrive — that data is not persisted anywhere else. The shape is in
[eval-approach.md](../eval-approach.md#workspace-layout).

Grade and aggregate:

```bash
find "$WS/iteration-2" -name eval_metadata.json -printf '%h\n' \
  | xargs -L1 python3 evals/create-agents-for-repo/grade.py

python -m scripts.aggregate_benchmark "$WS/iteration-2" --skill-name create-agents-for-repo
```

`grade.py` takes one run directory and reads the rest — which eval, which fixture — from that run's
`eval_metadata.json`.

## Reading the assertions

Fifteen apply everywhere; `reimport-repo` adds two about not clobbering what was already there.
They split into two groups, and only the second one still tells you anything.

**Structural** (1–10) — an agent exists, validates, is referenced, is tiered, has a tool grant, has
a return contract, matches the toolchain, is routed from CLAUDE.md, touched nothing outside
`.claude/`, and came with a proposal listing rejections. These saturated at round 1: 100% with the
skill against 97% without. Keep them as a regression floor, not as a signal.

**Judgement** (11–15) — the part an unaided run has no reason to do. No judgment-shaped agent cast
as haiku; every haiku agent capped with `maxTurns` or `effort`; a candidate justified by a real
measured line count; a rejected candidate replaced by a named concrete alternative; every
Bash-holding agent spelling its command out in backticks rather than describing it. These are where
the arms separate. Despite the name they are all mechanical — this suite grades files, and files
answer these questions without a grader model.

Assertions 11, 12 and 15 apply only to agents a run **authored or changed**, computed by diffing
against the fixture. Two of the fixtures ship agents of their own, and leaving those alone is
correct — grading a run on them inverts the signal.

## When you change the skill

Add assertions rather than rewriting them, and note the change in [benchmark.md](benchmark.md)
alongside the scores. A rubric edited between rounds makes the two rounds incomparable, which costs
more than the round was worth. If a check saturates in both arms, it has stopped measuring: leave
it as a floor and add a sharper one beside it.
