# Writing the agent file

Read this while writing `.claude/agents/<name>.md`.

## Contents

- [The constraint everything follows from](#the-constraint-everything-follows-from)
- [Frontmatter](#frontmatter)
- [Choosing the tool grant](#choosing-the-tool-grant)
- [Writing the description](#writing-the-description)
- [Body template](#body-template)
- [Return contracts](#return-contracts)
- [A worked example](#a-worked-example)
- [Review checklist](#review-checklist)

## The constraint everything follows from

**A subagent receives its own body as the system prompt, plus the working directory. Nothing else.**
Not CLAUDE.md. Not the conversation. Not the files the main thread already read. Not the user.

Every mistake in agent authoring is a version of forgetting this. The agent that "just runs the
tests" doesn't know the project uses `uv`. The agent told to "follow the house style" has never
seen the house style. The agent asked to "check with the user first" has no user to check with.

Two escape hatches exist for repo knowledge, and both cost tokens on every invocation, so prefer
stating the two or three facts the agent actually needs:

- `skills: [name]` preloads a skill's full text into the agent at startup. Worth it when the
  agent's job *is* that skill's mechanical steps; wasteful otherwise.
- The agent can `Read` CLAUDE.md itself, if you tell it to and it has the tool. Reasonable for a
  Sonnet agent doing broad work; usually overkill for a Haiku agent with a three-step procedure.

## Frontmatter

`name` and `description` are required; everything else is optional. This skill always sets `model`
and `tools` too, since their defaults (inherit the session model, inherit every tool) discard both
of the wins you're chasing.

| Field | Use |
|---|---|
| `name` | Lowercase and hyphens. No `:` — that's reserved for plugin-scoped names and a file containing one won't load. Match the filename; nothing enforces it, but a mismatch makes the agent hard to find later |
| `description` | The dispatch surface — see [below](#writing-the-description) |
| `tools` | Comma-separated allowlist. Omitting it inherits everything |
| `disallowedTools` | Subtractive alternative to `tools`. Applied first when both are set |
| `model` | `haiku`, `sonnet`, `opus`, `fable`, a full model ID, or `inherit`. Defaults to `inherit` |
| `maxTurns` | Turn cap. A cheap guardrail against a cheap model looping |
| `effort` | `low`/`medium`/`high`/`xhigh`/`max`. `low` suits mechanical Haiku work |
| `skills` | Preload full skill text at startup |
| `permissionMode` | Leave alone unless the user asks. `acceptEdits` on an autonomous fixer is a real decision, not a convenience |
| `color` | Display colour in the task list. Free legibility — group by tier |
| `background`, `isolation`, `memory`, `mcpServers`, `hooks`, `initialPrompt` | Situational; reach for them only when the case is specific |

## Choosing the tool grant

Narrow grants cut the agent's own prompt, remove whole failure modes, and stop an eager cheap model
from "helpfully" editing files it was asked to report on.

| Agent shape | Grant |
|---|---|
| Read-only investigator | `Read, Grep, Glob` |
| Command runner / reporter | `Bash, Read, Grep` |
| Fixer that must verify its own work | `Bash, Read, Edit, Grep` |
| Broad worker that just shouldn't write | `disallowedTools: Write, Edit` |

Three rules worth holding:

- **`Bash` is all-or-nothing.** The `tools` field names tools, not commands — there is no way to
  grant `pytest` but withhold `rm`. An agent given Bash so it can run the tests can also run the
  formatter, install a package, or rewrite history. This is the largest grant on the list and the
  one most often handed out casually. What actually constrains it is the body's procedure and Do-not
  section, and the repo's `permissions` settings — not the frontmatter. Where reporting is the whole
  job and the command set is fixed, that gap is worth naming in the proposal.
- **`Write` is rarer than it looks.** Most agents report or amend; creating new files is a bigger
  grant than it appears and is usually the main thread's job.
- **Every entry must resolve.** If nothing in the list names a real tool, the agent generally
  refuses to launch. Typos here fail late and confusingly.

## Writing the description

This is what the main thread matches against when deciding to delegate unprompted. Write it as
*when to hand work over*, not as a job title.

Include: the trigger condition, the scope boundary, and "use proactively" if it should fire without
being asked. Exclusions carry weight — `Does not touch pyright errors` prevents both a bad
delegation and a scope creep once it's running.

```yaml
description: Clear ruff lint and format failures across src/ and tests/. Runs the autofixers, then
  hand-repairs the residue. Use proactively after a large edit or before a commit. Does not touch
  type errors and does not change behaviour.
```

Don't lean on this alone. Automatic delegation is real but unreliable for narrow repo-specific
work, which is why every agent also gets an explicit call site (see
[wiring.md](wiring.md)).

## Body template

Five sections. Skip one only when it genuinely doesn't apply.

```markdown
<One or two sentences: what this agent does and, pointedly, what it does not.>

## Procedure
1. <exact command, with the runner: `uv run …`, `npm …`>
2. <what to do with the result>
3. <the check that proves the work>

<Why the last step is mandatory, and what to do when it fails.>

## Repo facts
<The things the agent cannot know: paths in scope, conventions that bite, deliberate exceptions and
why they exist. Two or three that matter beat ten that don't.>

## Do not
- <the tempting out-of-scope action> — <why>
- <the shortcut that hides a problem> — <why>

## Report
<The return contract. See below.>
```

Two notes on tone. **Give reasons.** "Do not add `# noqa`" gets followed inconsistently; "Do not
add `# noqa` — suppressing a rule is a config decision for a human, not an inline escape hatch"
gets followed, and generalises to the case you didn't anticipate. And **open with the boundary**:
a first line like *"You clear ruff failures. Nothing else."* does more scope control than a long
Do-not list.

## Return contracts

The return contract is the mechanism. Isolation only pays if what comes back is much smaller than
what went in — an agent that pastes the log back has moved tokens, not saved them.

A good contract states the shape, the ceiling, and the empty case:

```markdown
## Report
State the number of failures, then for each: the test id and the assertion line. Nothing else —
no passing tests, no summary tables, no full tracebacks unless the failure is a crash, in which
case include the final frame only. If everything passes, reply with the single line
`All N tests pass.`
```

Patterns worth reusing:

| Pattern | Contract |
|---|---|
| Pass/fail runner | One line on green; on red, N items of id + reason |
| Investigator | The answer in a sentence, then at most 3 file:line citations |
| Fixer | What changed grouped by category, then what was deliberately left and why |
| Auditor | A findings list, severity-ordered, one line each; no restatement of the source |

The empty case matters more than it looks: without it, agents pad. "Return `No drift found.` and
nothing else" is the difference between a one-line answer and half a page of reassurance.

## A worked example

```markdown
---
name: test-runner
description: Run the test suite and report only what failed. Use proactively whenever a change
  needs verifying, before a commit, or when asked whether tests pass. Reports; does not fix.
tools: Bash, Read
model: haiku
maxTurns: 6
color: green
---

You run the tests and report what failed. You do not fix anything.

## Procedure
1. `uv run pytest -q`
2. If it exits 0, report the green line and stop.
3. If it exits non-zero, re-run only the failing files with `-n0` to get clean output, then read
   the assertion for each failure.

Step 3 matters because the suite runs parallel by default and interleaved output misattributes
failures to the wrong test.

## Repo facts
- `pytest` is configured in `pyproject.toml` with `-n auto` and `asyncio_mode = "auto"` — async
  tests need no marker.
- Snapshot tests under `tests/editor/` fail on any intentional restyle. Say so when they're the
  only failures; do not run `--snapshot-update` yourself, that's a human decision.

## Do not
- Do not edit source or test files — you have no Edit tool and should not work around it.
- Do not re-run the suite more than twice; a flake that survives one retry is a finding, not noise.

## Report
On green: `All N tests pass.` and nothing else.
On red: the failure count, then per failure the test id and the assertion line. No tracebacks
unless the failure is a crash, in which case the final frame only.
```

## Review checklist

Before writing the file:

- [ ] Could a competent stranger with no repo knowledge follow the procedure using only this body?
- [ ] Does the report section cap the output and cover the empty case?
- [ ] Does every `Do not` say why?
- [ ] If the agent can edit, does the procedure include a step that proves it didn't break anything?
- [ ] Is the tool grant the smallest that lets it finish?
- [ ] Does `name` match the filename and contain no `:`?
- [ ] Is the description about *when to delegate*, not about what the agent is?
