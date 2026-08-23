# How evals work in this repo

An eval round measures whether a skill *changes what a model does*. Every round is an A/B: the
same case run twice, once with the skill in the system prompt and once without, graded against
the same rubric, and recorded in a dated benchmark so the next round is compared rather than read
in isolation. A score with no baseline beside it says nothing — the model may have been doing it
anyway.

This file is the format all the suites under `evals/` follow. Read it before adding a suite or
changing one.

## Three shapes, one skeleton

What a run leaves behind decides how it is graded, and nothing else about the suite differs.

| Kind | The run leaves | Graded from | Here |
|---|---|---|---|
| **Artifact** | Files in a staged repo | Diffs and file contents | `create-agents-for-repo/`, `refactor/` |
| **Conversation** | A transcript | Turns, questions, what was read | `plan/` |
| **Trigger** | Nothing | Whether the skill activated at all | `obsidian-metabind/` |

Artifact and conversation suites are the full thing: two arms, a rubric, a benchmark. A trigger
suite is a labeled query set graded by `skills/skill-audit/scripts/eval_triggers.py` — it measures
the `description`, not the body, so it has no arms and no fixtures.

## A suite's contents

```
evals/<skill>/
  README.md        how to run a round, why these cases, how to read the assertions
  evals.json       the cases: prompt, fixture, and the assertions unique to each
  benchmark.md     dated record of past rounds and rubric versions
  fixtures/        repos a run works against — copied per run, never mutated
  personas/        briefs for a simulated user (conversation suites)
  prepare.py       stages a workspace (artifact suites)
  drive_*.py       runs the case to completion and records it (conversation suites)
  run_case.py      drives one staged run to completion (artifact suites that need write tools)
  grade.py         scores one run directory, writes grading.json
```

Suites live here rather than inside `skills/<name>/`, so they do not travel with the published
plugin: measuring a skill means working from a clone of this repo. Nothing here is an agent tool —
every script carries `# agent-tool: false`, and `fixtures/` is excluded from ruff, pyright and
pytest in the root `pyproject.toml`.

## `evals.json`

```json
{
  "skill_name": "plan",
  "evals": [
    {
      "id": 0,
      "name": "rate-limit-in-repo",
      "fixture": "api-repo",
      "prompt": "…what the user says, verbatim, in their own register",
      "expected_output": "…what a good run looks like, for a human reading the round"
    }
  ]
}
```

`id`, `name` and `prompt` are required; `fixture` is `null` when the case has no repo.
`expected_output` is prose for the reader, never parsed. Beyond that a suite adds what its kind
needs — `assertions` (artifact), `judgement` and `persona` (conversation), and any case-specific
data a check reads, such as `plan`'s `repo_answers` patterns.

Assertion text that appears both here and in `grade.py` must match word for word: the JSON copy is
what the viewer shows, the code is what computes it, and a rubric that says two different things is
worse than one that says nothing. Where a check is parameterised per fixture, the JSON carries the
resolved text.

## Workspace layout

Every suite stages into the same shape, built by `shared/workspace.py`:

```
<workspace>/iteration-<n>/eval-<id>-<name>/<arm>/run-<k>/
    repo/                 the run's own copy of the fixture
    outputs/              artifacts the run was told to save
    eval_metadata.json    what this run is, written before it starts
    timing.json           what it cost
    grading.json          what it scored
```

Each level earns its place. `iteration-<n>` is the unit a benchmark round compares across.
`eval-<id>-<name>` and `<arm>` are the experiment. `run-<k>` is where repeats of one cell go — one
run per cell is a single observation, so treat a 20% swing in tokens or time as noise, and the
aggregator globs for this depth whether or not a suite currently repeats.

Workspaces are built outside the repo (`/tmp/...`) and are disposable, except for the artifacts a
benchmark cites — a stored `transcript.json` or `outputs/` is what lets a later rubric re-grade an
earlier round.

The three files a run leaves are contracts:

- **`eval_metadata.json`** — `eval_id`, `eval_name`, `arm`, `prompt`, `fixture`, `assertions`. The
  viewer reads the first and the fourth; the rest is so a run directory explains itself years later
  without the `evals.json` that produced it. `grade.py` reads it instead of taking the eval name
  and fixture as arguments.
- **`timing.json`** — `total_tokens`, `duration_ms`, `total_duration_seconds`, `cost_usd`, for the
  thing under test and nothing else. Harness overhead — a simulated user, a grader model — is
  recorded under its own keys so it cannot flatter or inflate a round.
- **`grading.json`** — `expectations` and `summary`, plus `execution_metrics` when the suite can
  see how the run was produced. Counts live under `summary` and nowhere else.

## The two arms

The arms differ in **exactly one thing**: whether the skill's body is appended to the system
prompt. Same model, tools, fixture, prompt and preamble either way.

Runs go through `--safe-mode`, so no global `CLAUDE.md`, skills, MCP servers or hooks from whoever's
laptop it is leak into a round. The `Skill` tool is blocked for the same reason: without it the
`without_skill` arm can load the skill under test on its own and stop being a baseline. That block,
with `Task`, `SlashCommand` and the web tools, is `ISOLATION_BLOCKED_TOOLS` in `shared/claude_cli.py`
— the floor a suite starts from however much it then grants. A suite whose runs edit files grants
`EDITING_TOOLS` on top and passes `permission_mode="acceptEdits"`, because nobody is at the terminal
to answer a prompt and the run would otherwise stall until its timeout. A third arm (`old_skill`,
pointed at a snapshot) is available where a suite supports it, for measuring an edit rather than the
skill's existence.

Whatever a suite tells both arms in its preamble stops being measurable. Say where the run is and
how to invoke its tools; say nothing the skill itself is supposed to supply, or the baseline gets
the behaviour for free and the check that grades it flatlines at 100% in both arms.

## The rubric

Two halves, both landing as `{text, passed, evidence}` records.

**Mechanical** checks are computed by `grade.py` from what the run left on disk. Cheap,
deterministic, and free to re-run over stored artifacts. Every one is a proxy — a regex for a
recommendation is not a recommendation — so each reports *what it matched*, pass or fail, and a
human can see what tripped it.

**Judgement** checks are statements sent to a grader model along with the run, the arm label
stripped and tool calls removed so it cannot tell which version it is reading. This is where
behaviour no regex reaches gets graded, and where the arms usually separate.

Rules that have already cost a round when broken:

- **A check that passes in both arms has stopped measuring.** Leave it as a regression floor and
  add a sharper one beside it, rather than rewriting it.
- **A check nothing can satisfy is a broken check, not a finding.** Three rounds of 0/3 means
  reading the transcripts, not believing the number.
- **Grade only what the run did.** Where a fixture ships artifacts of its own, leaving them alone
  is correct; checks that grade a run on them invert the signal. Compute what was authored by
  diffing against the fixture.
- **A run that did almost nothing cannot do it badly.** Checks phrased as "never does X" need a
  floor — a minimum number of turns, or a file that must exist — or an empty run passes for free.
- **Add assertions rather than rewriting them.** A rubric edited mid-flight makes two rounds
  incomparable, which costs more than the round was worth. When you do retire one, bump the rubric
  version in `benchmark.md` and re-grade the previous round's stored runs under the new rubric so
  the two still line up.
- **Editing a fixture makes every earlier round a different experiment.** Prefer adding a case.

## `shared/`

Plumbing every suite needs, imported flatly the way skill scripts import their siblings — each
script puts `evals/shared` on `sys.path` because it is run by path, not as a package.

| Module | What it holds |
|---|---|
| `claude_cli.py` | One CLI turn in and out: `run_claude`, the tool allow/block lists, `--safe-mode`, token accounting, `extract_json_array` |
| `grading.py` | `expectation`, the `grading.json` writer, and `judge` — the model-graded half, including the index alignment that fails a skipped statement instead of dropping it from the denominator |
| `workspace.py` | The run-directory layout, fixture staging, case lookup, and the `eval_metadata.json` / `timing.json` writers |

What deliberately stays in a suite: the grader prompt (it has to describe what the grader is
reading), every mechanical check, and any analysis of the artifact under test — `plan`'s
`transcript_lib.py` knows what a question is, and that is not general knowledge.

## Adding a suite

1. `evals/<skill>/` with `evals.json`, a `README.md`, and fixtures if the cases need a repo.
2. A stager or a driver on top of `shared/workspace.py`, writing `eval_metadata.json` per run.
3. A `grade.py` taking one run directory, writing `grading.json` through
   `shared/grading.write_grading`.
4. Mechanical checks first — they are the floor and cost nothing to re-run. Add judgement
   statements for what they cannot see.
5. Run a round, then start `benchmark.md` with it. A suite with no recorded round is untested
   machinery.
6. Add per-file lint exceptions to `pyproject.toml` with a comment, never inline `# noqa`.
