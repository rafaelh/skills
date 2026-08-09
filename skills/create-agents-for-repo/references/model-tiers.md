# Assigning work to a model tier

Read this when a candidate isn't obviously one tier or another. The expensive mistake is not
"assigned Sonnet where Haiku would do" — that just leaves money on the table. It is giving Haiku
work whose *criteria* are the hard part, because the output looks plausible and nothing catches it.

## Contents

- [The test that actually discriminates](#the-test-that-actually-discriminates)
- [Haiku](#haiku)
- [Sonnet with isolation](#sonnet-with-isolation)
- [Opus](#opus)
- [Archetypes](#archetypes)
- [Miscasting failure modes](#miscasting-failure-modes)
- [Turning the tier into frontmatter](#turning-the-tier-into-frontmatter)

## The test that actually discriminates

Ask: **when this agent returns something wrong, what notices?**

- A command exits non-zero, a schema rejects it, a test goes red → Haiku. The world checks the
  work, so the model only has to be a competent operator.
- Nothing notices until a human or the main thread reasons about it later → Sonnet at least. You
  are buying judgment, not throughput.

That single question resolves most cases. The rest of this file is what to do with the ones it
doesn't.

## Haiku

All four must hold.

**1. The success criterion is external.** Something outside the agent's own opinion decides whether
it succeeded. `pytest` exit 0. `pyright` clean. A JSON payload that parses against a schema. A diff
that applies. If the criterion is "did it pick the right ones", that is the agent judging itself.

**2. The instructions fit in the agent body.** You can write down the whole job. If you find
yourself writing "use your judgment about the house style", the house style either needs spelling
out or the work isn't Haiku's.

**3. Failure is loud.** A wrong answer surfaces immediately. Contrast: an agent that reports "no
other call sites" when there were three doesn't fail loudly — it fails silently, and the main
thread proceeds on a false premise. Search whose completeness matters is not automatically Haiku's,
even though search feels mechanical.

**4. One pass, clear stopping condition.** "Run these commands, fix what the fixer can fix, report
the residue" terminates. "Improve the naming in this module" does not.

A useful pattern that satisfies all four: **run a fixer loop, then report the residue.** The
autofixer does the deterministic part, the exit code proves the state, and the residue is exactly
what needs escalating. Cheap models are good at this and it recurs constantly.

## Sonnet with isolation

The judgment is genuine, so the tier is not a saving — the saving is the context. Use it when the
*evidence* is bulky and disposable:

- Reading many files to answer one question ("which module owns timing-related business logic?",
  "does this pattern appear anywhere else?").
- Triaging a noisy failure log into a short list of distinct causes.
- Auditing content or docs against the code and returning a list of drifts.
- Drafting something that gets reviewed anyway — scaffolding tests, a first-pass migration.

The return contract keeping unnecessary detail out of the main context window is what makes this pay. An agent that reads 40 files and hands back excerpts from 40 files has moved tokens, not saved them.

**Watch for the exception:** if the main thread will need the evidence itself — because it is about
to edit those files — delegating costs you a second read. Delegate the *question*, not the
*reading*, and only when a short answer genuinely closes it.

## Opus

An Opus agent saves nothing on cost. It buys one thing: the reasoning and the reading it consumed
stay out of the main context. That's real but it is a tradeoff the user should make, not you.

Genuine cases:

- Architecture and ADR conformance judgment, where being wrong means the codebase drifts.
- Security review, where a plausible miss is the whole risk.
- Multi-hypothesis debugging, where the work is holding several competing explanations at once.

Present these as a short list with the honest framing — same cost, cleaner main context — and let
the user choose. Two or three real ones beats a padded list.

## Archetypes

Starting points, not verdicts. The repo's specifics can move any of these a tier.

| Work | Tier | Because |
|---|---|---|
| Run test suite, report failures | haiku | Exit code is the criterion; failure is loud |
| Run linter/formatter autofix, hand-fix residue, report | haiku | Fixer is deterministic, re-run proves state |
| Typecheck and report errors verbatim | haiku | Compiler is the judge |
| Regenerate snapshots / lockfiles / generated code, confirm clean | haiku | Tool does the work; diff is the proof |
| Validate data files against a schema | haiku | Schema is the criterion |
| Extract a named subset from a large file or command output | haiku | Explicit selection, checkable |
| Enumerate matches for an explicit pattern | haiku | …but see below if completeness is load-bearing |
| Find every call site before a rename | sonnet | Completeness matters and failure is silent |
| "Which module owns X?" across an unfamiliar tree | sonnet | Needs judgment about relevance |
| Triage a failing CI log into distinct causes | sonnet | Grouping and de-duplication is judgment |
| Audit docs/content against the code for drift | sonnet | "Is this stale?" has no external checker |
| Scaffold tests for a module | sonnet | Reviewed downstream, so plausible-but-imperfect is fine |
| Decide whether an abstraction earns its keep | opus (ask) | Pure judgment, expensive to get wrong |
| Security review of a diff | opus (ask) | A plausible miss is the failure |
| Design an interface or record an ADR | opus (ask) | …and often shouldn't be delegated at all |

## Miscasting failure modes

**Giving Haiku the criteria, not the procedure.** "Find the code that violates the layering rules"
sounds mechanical and isn't — "violates" is the judgment. Rewrite it as a procedure with an
external check ("list every import in `models/` that names `modules/`; that pattern is the
violation") and it becomes Haiku work. If you can't rewrite it that way, it isn't Haiku work.

**Silent-incompleteness search.** Anything where "I found nothing" is an acceptable-looking wrong
answer. Either move it to Sonnet or give the agent an external completeness check.

**Delegating the user-facing step.** The subagent cannot see the user and the user cannot see it.
Interviews, approvals, and presenting choices stay in the main thread — always.

**An agent that edits without a verification step.** Any agent with `Edit` or `Write` needs a
command in its procedure that proves it didn't break anything, and an instruction to revert and
report rather than push through. This matters most on the cheap tier, where the reflex to keep
going is strongest.

**Delegating something two tool calls long.** Cold start plus round trip costs more than the work.
Fold it back into the main thread.

**One agent doing three jobs.** A wide brief pushes it up a tier — nothing in it is simple any
more — and makes the return contract vague. Split it, or admit it's Sonnet work.

## Turning the tier into frontmatter

`model` is the tier. Two neighbouring fields matter as much:

- **`maxTurns`** — a guardrail, most valuable on the cheap tier, where a misread brief turns into a
  loop. Set it a little above the expected turn count so a normal run never hits it. A run that
  does hit it is a signal the brief was wrong.
- **`effort`** — for mechanical Haiku work, `low` trims reasoning tokens that buy nothing. Leave it
  unset for Sonnet judgment work; that reasoning is what you're paying for. Available levels vary
  by model, so treat it as an optimisation to try rather than a default.
