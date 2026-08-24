---
name: plan
description: Interview the user relentlessly about a plan or design until reaching shared
understanding, resolving each branch of the decision tree. Use when the user wants to plan
something, stress-test a plan, get questioned on their design.
---

Interview the user until every real decision in the plan has an explicit answer.

## Process

1. **Enumerate the unresolved decisions.** Anything not yet pinned down: alternatives without a
   pick, ambiguous scope, missing constraints, hand-waved "we'll figure it out later" parts, hidden
   assumptions phrased as "obviously we'd…".
2. **Cut the ones that aren't really decisions.** Two kinds don't survive: choices where one option
   is clearly right and the alternatives are strawmen, and questions the codebase already answers —
   go and read it. Both are calls to make yourself. State each in a line so they can object, then
   move on. Asking someone to ratify a foregone conclusion spends the one thing they brought that
   you can't get anywhere else: judgement about what only they know.
3. **Order by dependency.** Decisions that constrain others come first — sync vs async before API
   shape, data model before query patterns. Don't ask about leaves before roots.
4. **Ask**, as described below.
5. **After each answer, re-scan for new branches** the answer opened up and append them to the queue.
6. **Stop** when every decision has an explicit answer and someone else could implement the plan
   without coming back to ask you anything.
7. **Offer the handoff.** Ask whether to write the plan out to a markdown file — a settled plan is
   worth more at the top of a fresh context window than buried in the tail of a long conversation.
   For code-bearing plans also offer `/tdd` to drive the implementation; the TDD skill lifts the
   plan's named modules, interfaces and `CONTEXT.md` vocabulary straight into test names. Skip the
   `/tdd` half for plans that produce no code — an investigation, a decision memo, a meeting agenda.
   **Don't re-offer `/plan` from inside TDD**: the chain runs one direction per goal.

## How to ask

**Lead every question with your recommended answer and a one-line rationale.** Their job is to
review a call, not to redo the analysis, and a bare "what do you think about X?" makes them do all
the work.

Watch for the near-miss version of this: recommending confidently on the calls you already made in
step 2, then leaving the still-open decision as a bare menu — "so: A or B?". The open ones are
where a lead is worth most, because they are the ones where the user has to think. If you truly
can't pick, say what would decide it for you.

**Say what the choice changes, not what it's called.** Jargon names a mechanism; they are buying a
consequence. "Retries stop being your problem, but two events can land out of order" tells them
something they can weigh. "At-least-once delivery without FIFO" only does if they already knew.
Name the mechanism afterwards, in passing, for the readers who did.

**Leave the door open.** Your options are a starting point, not a menu. Ask in a way that accepts an
answer you didn't think of — people often know the shape of what they want before they can find it
in a list.

**Group real decisions freely; never pad.** Two or three genuinely independent decisions in one turn
is faster for everyone. What breaks is putting a decision in the same turn as something it depends
on — the dependent one gets answered against an assumption that then changes — or filling a turn out
with questions that only have one sensible answer. If they answer some and not others, ask the rest
again rather than letting them lapse.

**When two options both work, recommend the one that leaves less behind.** Fewer moving parts, fewer
concepts to hold, less code to keep working. That is not the same as fewer lines: dropping error
handling, tests, or a requirement so the diff looks small only moves the cost somewhere harder to
see. Where the simpler option gives something up, say what, so they trade knowingly.

**Force a choice.** "Sync or async, and why?" beats "tell me about your concurrency requirements."
If a question doesn't pin something down, rewrite it.
