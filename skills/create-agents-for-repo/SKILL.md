---
name: create-agents-for-repo
description: "Audit a repository for work that should run on a cheaper model or in an isolated context, then write .claude/agents/*.md subagent definitions fitted to that repo's toolchain and wire them into its CLAUDE.md and skill workflows so they actually get invoked instead of sitting unused. Use when the user wants to cut token cost, route work to Haiku or Sonnet, keep verbose test/build/search output out of the main context, add or review subagents for a project, fit portable skills to a specific repo, or asks \"which parts of this repo could a cheaper model handle\", \"add subagents to my repo\", \"why is this session burning so many tokens\", \"make my skills delegate\", or \"stop Opus doing work Haiku could do\". Also trigger on complaints about the context window filling up or compaction happening too often. NOT for writing Python or TypeScript CLI scripts that agents call as tools — use agent-tool-builder. NOT for auditing, validating, or trigger-tuning an individual SKILL.md — use skill-optimizer."
compatibility: Claude Code (subagents are a Claude Code feature — .claude/agents/*.md, the Agent tool, and the model/tools/maxTurns frontmatter fields). Scripts require Python 3.14+, stdlib only.
metadata:
  version: "0.1"
  author: Rafe Hart
---

# Create agents for this repo

Find the work in a repository that should not be running on the main thread's model in the main
thread's context window, write subagents for it, and — the part that decides whether any of this
pays off — name those subagents at the exact points where the work happens.

This runs in a **target repo**, not in a skills library. Skills travel between repos; agents don't,
because a useful agent hardcodes the things that make it cheap — `uv run pytest -n0`, the strict
pyright paths, which directories hold generated code. That local knowledge is the whole product
here. Expect to run this again after the repo's skills are re-imported or its toolchain shifts.

## Why delegate at all

Two wins are on the table and they are independent:

- **Downshift** — a cheaper model does the work correctly. Buys cost and latency.
- **Isolation** — the work produces tokens the main thread never needs again (a test log, a file
  sweep, a raw API response). Keeping them out of the main context is what decides how long a
  session stays sharp before compaction starts eating it.

Isolation pays even at the same tier: a Sonnet agent called from a Sonnet session still wins.
Downshift always arrives bundled with isolation, because routing work to Haiku *means* spawning a
subagent. So every candidate gets isolation; the classification decides only the model.

Against that, the cost that keeps this from becoming agent spam: **a subagent starts cold.** No
conversation history, no CLAUDE.md, none of the files already read. It re-derives context the main
thread already holds, and you pay for that plus a round trip. Below roughly a handful of tool
calls, delegation loses money and wall-clock. Be ready to say a candidate isn't worth it — a
proposal with nothing rejected means the bar wasn't real.

## Workflow

| Phase | What happens | Runs in |
|---|---|---|
| 1 | [Inventory the delegation surface](#1-inventory-the-delegation-surface) | main thread (one script call) |
| 2 | [Hunt candidates](#2-hunt-candidates) | subagents, in parallel |
| 3 | [Challenge the candidates](#3-challenge-the-candidates) | a subagent, adversarially |
| 4 | [Assign a tier](#4-assign-a-tier) | main thread |
| 5 | [Propose, and stop for approval](#5-propose-and-stop-for-approval) | main thread |
| 6 | [Write, wire, verify](#6-write-wire-verify) | main thread |

Phases 2 and 3 are delegated for the same reason this skill exists: hunting candidates means
reading whole skill bodies and running commands to see how much they print, and none of that
evidence is worth a slot in the main context once the conclusion is drawn. Running this skill
without delegating its own bulky phases would be an odd advertisement.

---

## 1. Inventory the delegation surface

```bash
python3 "${SKILL_DIR}/scripts/scan_delegation_targets.py" <repo-root> --format json
```

`${SKILL_DIR}` is the directory holding this SKILL.md (`${CLAUDE_SKILL_DIR}` on Claude Code). One
call returns: the repo's skills with descriptions, headings and **where each one's SKILL.md
actually lives**; agents that already exist with their models and tool grants; slash commands; the
build/test/lint commands declared in `pyproject.toml` / `package.json` / `Makefile`; the fenced
commands in CLAUDE.md; and whether the agents directory is gitignored. Exit `3` means no delegation
surface at all — say so and stop rather than inventing candidates.

Read the scan's output, not the files behind it. Reading the skill bodies and measuring command
output is Phase 2's job, and it happens in subagents — pulling that material into the main context
here is the mistake this whole skill is about.

**Check where the skills came from, because it decides what you're allowed to edit in Phase 6.**
The scan reports `origin` per skill:

| Origin | Editing its SKILL.md | Consequence |
|---|---|---|
| `repo` — real files under the repo's `.claude/skills/` | Fine. Commit the edit. | Wiring survives, travels with the repo |
| `plugin` — installed from a marketplace under `~/.claude/plugins/` | Don't. | The next plugin update silently reverts it — route through CLAUDE.md instead |
| `symlink` — points outside the repo | Ask first. | The edit lands in the *source* library and leaks into every other repo using it |

**Existing agents are part of the inventory, not a no-go zone.** An agent on `opus` doing
mechanical work is a finding, as is one with no tool restrictions, or one nothing ever calls. So is
wiring from a previous run of this skill that a re-import has since wiped out — restoring it is
usually the highest-value thing on the list.

## 2. Hunt candidates

Two lenses catch different things, and they read different material, so dispatch them as separate
subagents **in the same turn** and let them run in parallel. Hand each one the inventory from Phase
1 rather than making it rediscover the repo. When Lens A has more than about four skills to walk,
split it further — one agent per skill — since each reads a different file and nothing is shared.

Both lenses want a general-purpose subagent: Lens A reads a file end to end and the built-in
`Explore` samples excerpts, which loses the step order the walk depends on; Lens B has to run
commands.

> **Lens A prompt — one per skill (or one for a few small ones):**
> Read `<skill-path>/SKILL.md` and walk its workflow step by step. For each step decide whether the
> main thread needs that step's **output** or only its **conclusion**. Steps that run validators,
> execute test suites, sweep files for evidence, or fetch reference material produce bulk that gets
> read once and never cited again — those are candidates. Steps that decide, design, **interview
> the user**, or write the deliverable are not: a subagent cannot see the user and the user cannot
> see it, so delegating a user-facing step breaks the skill.
>
> This skill was written to be portable, so its steps name commands generically ("run the test
> suite", "check types"). Where a step's command does not match what this repo actually uses, say
> so — that mismatch is a finding in its own right, not just a candidate.
>
> Return the table below and nothing else. No file contents, no quoted steps, no reasoning.

> **Lens B prompt — one agent:**
> Read the repo's CLAUDE.md and this toolchain list: `<toolchain from Phase 1>`. These are the
> things the user asks for in plain language between skill invocations — run the tests, check
> types, lint, find every call site of X, regenerate the snapshots. This is the only lens that
> applies in a repo with no skills.
>
> **Measure, do not estimate.** Actually run each read-only command and count the lines it prints
> (`<command> 2>&1 | wc -l`). Do not run anything that writes, installs, or mutates state; for
> those, report the cost as unmeasured. A measured 3,709 lines beats a guessed "a lot" — the whole
> proposal is built on these numbers.
>
> Return the table below and nothing else.

Both hunters return the same shape, which is all the main thread keeps:

```markdown
| Work | Where | Measured cost today | What the main thread actually needs |
|---|---|---|---|
| Run the test suite | CLAUDE.md Quick Reference; tdd step 4 | 3,709 lines, ~2s, several times a session | pass/fail plus the failing test ids |
```

**Do not delegate the hunt in a repo where the hunt is small.** A repo with one CLAUDE.md, no
skills and three commands is three reads — spawning agents for that costs more than it saves, by
exactly the bar this skill applies to everything else. Delegate when there are skills to walk or
commands whose output needs measuring.

## 3. Challenge the candidates

Hand the combined candidate table to a fresh subagent whose only job is to argue against it. Give
it the Phase 1 toolchain list too, so it can check a tool's `--help` for a quieter flag instead of
guessing one exists. This is separate from the hunt on purpose: an agent that just produced a list is invested in it, and the
failure this phase prevents — a tidy set of agents that nobody needed — is the expensive one.

> **Reviewer prompt:**
> Below is a list of proposed subagent candidates for this repo. For each one, answer two questions
> and nothing more.
>
> **1. Would a subagent actually be good at this?** A subagent starts cold: no conversation
> history, no CLAUDE.md, none of the files already read. It cannot ask the user anything. Its
> answer arrives as prose the main thread has to trust. Ask what happens when it gets this wrong —
> if nothing external catches the error, the work needs judgment and a cheap agent will produce
> confident nonsense. Ask whether the brief can even be written down completely; if it depends on
> taste the repo has never written anywhere, the agent cannot inherit it.
>
> **2. Is a subagent genuinely cheaper than the simplest thing that would work?** Check these
> before accepting any candidate — each is cheaper than an agent and several are free:
>
> - **A quieter flag.** `-q`, `--quiet`, `--format json`, `--no-header`, `--tb=line`. Often removes
>   most of the volume for zero architecture, and then the candidate evaporates.
> - **A line in CLAUDE.md.** "Always run pytest with `-q`" costs a few tokens once per session and
>   solves the same problem as a test-runner agent, for repos where the failures are short.
> - **A pre-commit hook or CI job.** Runs with no model in the loop at all.
> - **A script or Makefile target.** Collapses six tool calls into one Bash call the main thread
>   makes directly — no cold start, no round trip.
> - **A built-in agent.** `Explore` already covers general codebase search; a bespoke
>   search agent has to be clearly better to be worth defining.
> - **Nothing at all.** Below roughly a handful of tool calls, delegation costs more than it saves.
>
> Return one row per candidate: `KEEP`, `SIMPLER: <the specific alternative>`, or `DROP: <reason>`,
> plus one sentence of justification. Be blunt — a review that keeps everything told us nothing.

Carry the verdicts forward honestly. A `SIMPLER` verdict is a result, not a failure: put the flag
or the hook in the proposal instead of an agent, and say why it beat one. Overrule the reviewer
only where you can name what it missed.

## 4. Assign a tier

**Haiku** — every one of these must hold, not most:

1. **The success criterion is external.** An exit code, a schema, a diff that applies or doesn't.
   The agent is not the judge of its own work.
2. **The instructions fit in the agent body.** No implicit repo taste required.
3. **Failure is loud.** A wrong answer surfaces immediately rather than quietly poisoning a
   decision three steps later.
4. **One pass, clear stopping condition.** Not "keep going until it looks right".

**Sonnet with isolation** — the judgment is real but the evidence is bulky and disposable: reading
many files to answer one question, triaging a noisy failure log into a short list of causes,
drafting something that gets reviewed anyway. What makes this pay is the return contract; without
one the agent hands back the evidence and you have saved nothing.

**Opus** — buys no cost saving at all, only isolation, so it is the user's call rather than yours.
Collect the genuine cases (architecture and ADR conformance judgment, security review, multi-
hypothesis debugging) and ask once, honestly: *these need Opus either way; an agent keeps their
reading out of your main context but costs the same — want them?* Don't pad the list to look
thorough.

Worked examples of each tier, and the failure modes that get work miscast, are in
[references/model-tiers.md](references/model-tiers.md). Read it before classifying anything
non-obvious — the common error is giving Haiku work whose *criteria* are the hard part.

## 5. Propose, and stop for approval

Present one table and wait. Writing agent files and editing skill bodies changes tracked source;
the user approves the batch before any of it lands.

```markdown
| Agent | Model | Replaces | Called from | Why this tier | What it saves |
|---|---|---|---|---|---|
| test-runner | haiku | `uv run pytest` inline | CLAUDE.md routing; tdd SKILL.md step 3 | exit code decides pass/fail; nothing to judge | ~3,700 lines/run, ~3 runs/session |
```

Below the table, four things:

- **Rejected candidates and why**, one line each — including the ones the reviewer replaced with
  something simpler, stated as the concrete change (`add -q to the pytest line in CLAUDE.md`)
  rather than a non-event. This is what shows the bar was applied.
- **Opus candidates as a question**, if any (see above).
- **Any skill you propose editing whose origin is `plugin` or `symlink`** — name the tradeoff and
  let the user pick between editing it, routing through CLAUDE.md only, or copying the skill into
  the repo first.
- **Anything else the inventory flagged**: a gitignored agents directory means the agents stay on
  this machine and never reach the repo — offer the `.gitignore` fix. An existing miscast or
  unreferenced agent belongs here too, as a proposed change rather than a silent edit.

## 6. Write, wire, verify

**Scope: touch only `.claude/`, its contents, and `CLAUDE.md`.**

### Write the agents

One file per agent at `.claude/agents/<name>.md`. Required frontmatter is `name` and `description`;
this skill also always sets `model` and `tools`, because the defaults (inherit the session model,
inherit every tool) throw away both wins.

The body is the agent's entire system prompt. **Subagents do not receive CLAUDE.md, the
conversation, or the files already read** — only this body plus the working directory. Whatever the
agent needs to know, the body says: exact commands with their runner, which paths are in scope,
which repo conventions bite. This is where the local fitting actually happens, and it is why a
generic agent copied between repos is worthless while a fitted one is cheap and reliable.

Every body carries a **return contract** — what to return and roughly how much. This is the whole
mechanism of isolation: an agent that pastes the log back has saved nothing.

Field-by-field guidance, a body template, tool-allowlist recipes, and return-contract examples are
in [references/agent-authoring.md](references/agent-authoring.md).

### Wire the call sites

**Write each agent and its call site together, then move to the next.** Doing all the definitions
first and all the wiring after leaves a window where every agent is an orphan, and anything that
interrupts you — a limit, a compaction, a changed mind — closes on that window. One agent finished
beats three agents half-done, because a half-done one is indistinguishable from the failure this
skill exists to fix.

Automatic delegation from the `description` field is real but unreliable for narrow repo-specific
work — the main thread has to notice the match unprompted, and mostly it just does the work itself.
So the agents get named explicitly at the point of use:

- **In CLAUDE.md**, a compact routing table. This is the durable backbone: it is repo-local,
  committed, loaded every session, and survives skill re-imports. When Phase 1 found `plugin` or
  `symlink` skills, this is the only place their delegation can safely live.
- **In repo-local SKILL.md bodies**, at the specific step, with a short call-site prompt carrying
  only the varying inputs. Standing instructions belong in the agent body, not repeated at every
  call site.

Before/after examples of both, and the phrasing that survives an agent re-reading it, are in
[references/wiring.md](references/wiring.md).

**When you correct a generic command that an imported skill got wrong, grep the whole file for the
old tool's name before moving on.** These skills mention their toolchain in more than one place —
the command itself, a verification checklist, a gotchas note — and fixing only the command leaves
`- [ ] mypy passes` sitting three lines below a repo that runs pyright. A half-corrected file is
worse than an uncorrected one, because it now looks fitted.

**The same grep applies to agent bodies you author.** Before finishing any agent, confirm it names
only tools from Phase 1's toolchain list — not tools from other repos you have seen. An agent that
says `mypy` in a pyright repo was written from memory instead of from the inventory.

### Verify

```bash
python3 "${SKILL_DIR}/scripts/validate_agent_def.py" <repo-root>/.claude/agents --check-references <repo-root>
```

Checks frontmatter against the current spec (name shape, valid `model` value, tool names that
resolve) and — the check that matters — that every agent is named somewhere a reader will hit. An
agent nothing references is the default failure of this whole exercise; the validator exits
non-zero on it rather than letting it pass quietly.

Then smoke-test at least one new agent for real: invoke it on an actual task and confirm what comes
back is the size the return contract promised. A contract that reads well and returns 400 lines is
the failure worth catching, and only a live call catches it. If the smoke-test writes or fixes
source files, revert those changes — this skill's deliverable is the agents and their wiring, not
application-code edits that happened to occur during verification.

Report what landed: agents written, call sites wired, and the ones you rejected.
