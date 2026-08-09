# Wiring the call sites

Read this when writing the edits that make the agents get used.

An agent nothing references is the default outcome of this exercise. The definition gets written,
the description is fine, and then the main thread does the work itself anyway — because doing it
inline is always the path of least resistance. Wiring is what changes the default.

## Contents

- [Why the description isn't enough](#why-the-description-isnt-enough)
- [CLAUDE.md routing](#claudemd-routing)
- [SKILL.md call sites](#skillmd-call-sites)
- [Phrasing that survives](#phrasing-that-survives)
- [What not to do](#what-not-to-do)

## Why the description isn't enough

Automatic delegation works by the main thread noticing that a request matches an agent's
description. It fires reliably for broad, obviously-delegable categories. It fires poorly for
narrow repo-specific work, because the main thread is mid-task, holds the context already, and the
inline path looks cheaper in the moment.

So descriptions are the fallback and explicit call sites are the mechanism. Both, always.

## CLAUDE.md routing

The durable backbone. It is repo-local, committed, loaded every session, and survives skill
re-imports — which makes it the only safe home for delegation when a repo's skills came from a
plugin or a symlink.

It also loads every session, so it stays small. A table, near the top, under its own heading:

```markdown
## Delegation

Route these to their agent rather than doing them inline — the output is bulky and the main thread
only needs the conclusion.

| When the work is | Use | Instead of |
|---|---|---|
| Running the test suite | `test-runner` | `uv run pytest` inline |
| Clearing ruff failures | `build-green` | running the fixers inline |
| Finding every call site before a rename | `call-site-sweep` | a fan of Grep calls |
| Checking docs against the code | `docs-drift` | reading `docs/` inline |

Anything not listed stays inline. A subagent starts cold, so delegating two tool calls' worth of
work costs more than it saves.
```

The last line earns its place. Without it the table reads as "prefer agents", and the next session
delegates a one-line grep.

Three rules:

- **Name the agent exactly.** `test-runner`, not "the test agent".
- **Include the "instead of" column.** It tells the reader which inline habit to break, which is
  the actual behaviour change being asked for.
- **Don't restate the agent's body here.** The routing table says *when*; the agent says *how*. Two
  copies drift, and the CLAUDE.md copy is the one that gets stale.

## SKILL.md call sites

For repo-local skills — real files under the repo's `.claude/skills/`. Skip this for skills whose
origin is `plugin` (the next update reverts the edit) or `symlink` (the edit leaks back into the
source library and into every other repo using it) unless the user said otherwise.

Put the call at the step, not in a preamble. A skill that opens with "delegate where appropriate"
delegates nowhere.

**Before:**

```markdown
3. **Verify the change.** Run the test suite and confirm nothing regressed.
```

**After:**

```markdown
3. **Verify the change.** Delegate to the `test-runner` agent — the suite prints several hundred
   lines and only the failures matter here.

> **Agent prompt:** Run the suite. Report failures only.
```

Three things are doing work in that edit. The agent is **named**. The **reason** is one clause, so
a future reader can tell whether it still applies. And the prompt is **short** — the standing
instructions live in the agent body, and the call site carries only what varies. Repeating the
agent's instructions at the call site is how the two drift apart.

Where a step fans out — the same check across several targets — say so explicitly, because parallel
dispatch is a large part of the win and it doesn't happen unprompted:

```markdown
2. **Sweep the modules.** Dispatch one `call-site-sweep` agent per module in the same turn; they
   run in parallel and each returns a short list.
```

## Phrasing that survives

The reader of this text is an agent mid-task with its own momentum. Phrasing that works:

- **"Delegate to the `X` agent"** — an instruction.
- **"…because the output is bulky and only the conclusion matters"** — a reason it can evaluate
  against the situation in front of it, which is what lets it skip delegation sensibly when the
  situation is genuinely different.

Phrasing that doesn't:

- "Consider using a subagent" — invites the inline path.
- "You may wish to delegate this" — same.
- "ALWAYS DELEGATE THIS STEP" — followed until it's obviously wrong, then discarded wholesale along
  with the surrounding guidance.

## What not to do

**Don't wire an agent that doesn't exist yet.** Within a pair, the definition lands before its call
site — a reference to a missing agent is a dead end at the worst moment. Across pairs, finish one
before starting the next rather than batching all the definitions and then all the wiring.

**Don't wire the user-facing step.** Interviews, approvals, presenting options — the subagent
cannot see the user and the user cannot see it.

**Don't add a delegation note to every step.** The signal comes from the contrast. When most steps
carry a delegation banner, none of them read as an instruction.

**Don't leave the agent's own instructions in two places.** The body is the source of truth; the
call site is a pointer plus the varying input.
