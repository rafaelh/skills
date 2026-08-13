# Eval harness for `plan`

Everything needed to re-measure the plan skill after editing it.

`plan` is a conversation, not a file transform, so there is no artifact to diff. What the
skill claims — one decision per turn, a recommendation attached to every question, roots
before leaves, read the code rather than ask about it, stop when the plan is handoff-ready —
is only visible across a whole interview. So a round runs a real multi-turn interview and
grades the transcript.

This is a developer harness. Nothing here ships as an agent tool; all three scripts are
marked `# agent-tool: false`, and `fixtures/` is excluded from ruff, pyright and pytest in
the repo root config. It does travel with the published `plan` plugin, since the plugin is
the whole skill directory — that costs installers a few hundred KB and buys anyone who
forks the skill the ability to measure their fork.

## Contents

| Path | What it is |
|---|---|
| `evals.json` | The four cases: prompt, fixture, persona, and the assertions unique to each |
| `fixtures/` | Two repos the interviewer reads instead of asking |
| `personas/` | Briefs for the simulated user — what they have decided, what they have not |
| `drive_interview.py` | Runs one interview to its end and records the transcript |
| `grade.py` | Scores one transcript, writes `grading.json` |
| `transcript_lib.py` | CLI invocation and the text analysis both scripts share |
| `benchmark.md` | Dated record of past rounds — compare against it, don't read a new score alone |

## How a run works

`drive_interview.py` alternates two Claude CLI sessions:

- **The interviewer** — a resumed session with read-only access (`Read`, `Grep`, `Glob`)
  to its own copy of the fixture repo. This is the thing under test.
- **The user** — a fresh, tool-less call each turn, given the persona brief and the
  conversation so far, told to answer only what was asked in a sentence or two.

The interview ends when the interviewer's turn contains no question, which is the harness's
reading of "the plan is settled". A run that hits `--max-turns` (12) is recorded with
`stop_reason: max_turns` and fails the termination assertion.

The two arms differ in **exactly one thing**: `with_skill` appends the body of
`../SKILL.md` to the interviewer's system prompt, `without_skill` does not. Everything
else — model, tools, fixture, persona, situation preamble — is identical.

Both arms run `--safe-mode`, so no global `CLAUDE.md`, skills, MCP servers or hooks from
the machine leak into a run. Without it, results depend on whose laptop produced them, and
the no-skill arm can load the plan skill on its own and stop being a baseline. The `Skill`
tool is blocked as well, for the same reason.

## Why these four cases

| Eval | Fixture | The claim it is there to break |
|---|---|---|
| `rate-limit-in-repo` | `api-repo` | Reading beats asking. The repo answers stack, Redis, the existing limiter, tenant identity and deployment; every one of those is a question the interviewer must not ask |
| `postmortem-rollout-no-code` | none | The negative branch of the TDD handoff. A plan that produces no code must not end with an offer to implement it |
| `stress-test-webhook-plan` | `payments-repo` | Hidden assumptions. The prompt hands over a plan containing "obviously we'd…" and "we'll figure out X later", plus an ordering hazard only visible in `handlers.py` |
| `slow-api-vague` | `api-repo` | Decision-forcing over exploratory. A vague complaint with no diagnosis is the case where an unaided model returns a list of eight fixes |

The personas are the other half of each case. They carry decisions already made, decisions
genuinely open, and one or two behaviours that put pressure on the skill — Priya pushes
back on new infrastructure, Marcus is defensive about the plan he wrote, Elena refuses to
invent data she does not have.

## Running a round

```bash
WS=/tmp/plan-evals/iteration-1

python3 - "$WS" <<'EOF' > /tmp/plan-jobs
import json, sys
ws = sys.argv[1]
for c in json.load(open("skills/plan/evals/evals.json"))["evals"]:
    for arm in ("with_skill", "without_skill"):
        # the run-N level is what skill-creator's aggregator globs for
        print(f"{c['name']} {arm} {ws}/eval-{c['id']}-{c['name']}/{arm}/run-1")
EOF

xargs -P 8 -L1 sh -c 'python3 skills/plan/evals/drive_interview.py $0 --arm $1 --out $2' \
  < /tmp/plan-jobs

find "$WS" -name transcript.json -printf '%h\n' \
  | xargs -P 8 -L1 python3 skills/plan/evals/grade.py
```

Then aggregate and review with skill-creator's tooling:

```bash
python -m scripts.aggregate_benchmark "$WS" --skill-name plan
python <skill-creator>/eval-viewer/generate_review.py "$WS" --skill-name plan \
  --benchmark "$WS/benchmark.json"
```

Timing and token counts are captured by the driver into `timing.json` per run — the
interviewer's cost only. The simulated user is harness overhead and is recorded separately
so it cannot flatter or inflate a round.

Everything defaults to `sonnet`. Override with `--model` (the interviewer, i.e. the thing
under test), `--persona-model`, and `--grader-model`. Keep the model fixed across arms and
across rounds you intend to compare.

## Reading the assertions

**Mechanical** — computed by `grade.py` from the transcript. Deterministic and free to
rerun, but every one is a proxy, so each reports what it matched.

| Check | Passes when | The proxy in it |
|---|---|---|
| Opens by asking | First turn ≤ 350 words and contains a question | A word budget stands in for "did not just deliver the plan" |
| Questions leave the door open | ≥ half of question turns invite an answer that wasn't listed | Keyword match on a narrow phrasing set, hence the lower bar |
| Questions carry a recommendation | ≥ 2 in 3 question turns match a recommendation phrasing | Keyword match; a clean sweep would measure vocabulary, not behaviour |
| Holds a real interview and stops on its own | `stop_reason` is `no_question` after ≥ 3 turns | The turn floor is what stops "here is your plan, no questions" from counting as a finished interview |
| Reads the repo before its first question | Turn 1 made a read tool call | Deliberately strict: enumerating decisions in a codebase means looking at it |
| Asks nothing the repo answers | ≥ 3 turns, and no question sentence matches the eval's `repo_answers` patterns | The turn floor again: a run that asks nothing can't ask badly |
| Offers to write the plan out | An offer naming a file or markdown | Anchored on a file, so "write it up" in a postmortem interview doesn't count |
| TDD handoff | `/tdd` offered for code-bearing plans, no build offer for the others | — |

Note what is deliberately *not* here: a one-question-per-turn check. Bundling is fine when the
decisions are real and independent — see round 1's notes in `benchmark.md`. What replaced it is the
judgement pair about strawman options and about bundling a decision with the thing it depends on.

**Judgement** — the six shared statements in `grade.py` plus the per-eval ones in
`evals.json`, sent to a grader model with the transcript, the arm label stripped and tool
calls removed so it cannot tell which version it is reading.

The mechanical checks are the regression floor; the judgement ones are where the arms
should separate. If a check passes in both arms across a round, it has stopped measuring —
leave it as a floor and add a sharper one next to it.

## When you change the skill

Add assertions rather than rewriting them. A rubric edited between rounds makes the rounds
incomparable, which costs more than the round was worth. Note what changed alongside the
scores.

If you edit a fixture, every earlier round becomes a different experiment. Prefer adding a
fifth eval to bending an existing one.
