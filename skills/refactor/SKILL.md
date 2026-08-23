---
name: refactor
description: >
  Use this skill when code works but is harder to read, maintain, or extend than it should be:
  deeply nested logic, long functions, unclear names, duplicated logic, or complexity that
  accumulated from iterative changes. Also trigger during code review when readability issues
  are flagged, after a feature lands under time pressure, or when consolidating related logic
  scattered across files.
---

# Code Refactor

## Overview

Simplify code by reducing complexity while preserving exact behavior. The goal is not fewer lines —
it's code that is easier to read, understand, modify, and debug. Every simplification must pass a
simple test: "Would a new team member understand this faster than the original?"

## When to Use

- After a feature is working and tests pass, but the implementation feels heavier than it needs to
  be
- During code review when readability or complexity issues are flagged
- When you encounter deeply nested logic, long functions, or unclear names
- When refactoring code written under time pressure
- When consolidating related logic scattered across files
- After merging changes that introduced duplication or inconsistency
- At step 4 of a TDD cycle (you've reached GREEN — if you arrived from `/tdd`, skip scope discussion
  and go straight to Step 2 below)

**Only start when all tests pass.** Never refactor on RED — you can't tell whether a failing test is
due to the refactor or the original code.

**When NOT to use:**

- Code is already clean and readable — don't simplify for the sake of it. "Already clean" is a
  finding you reach by working Step 2's patterns over the code, not an impression you form while
  reading it: name the duplication you went looking for and did not find. A pass that changes
  nothing is a real answer, and so is a pass that changes one line.
- You don't understand what the code does yet — comprehend before you simplify
- The code is performance-critical and the "simpler" version would be measurably slower
- The module is being replaced — whether you are about to rewrite it, or a replacement has already
  landed beside it. Read the neighbouring modules and the recent commits before you accept a
  cleanup at face value: work on code that is scheduled for deletion is thrown away. Say what you
  found and ask, rather than polishing it. Do not finish the migration either — moving the last
  caller over and deleting the old module is a bigger change than the one you just declined, and
  nobody asked for it.
- The change moves code between architectural layers — that requires ADR review

## The Five Principles

### 1. Preserve Behavior Exactly

Don't change what the code does — only how it expresses it. All inputs, outputs, side effects, error
behavior, and edge cases must remain identical. If you're not sure a simplification preserves behavior, don't make it.

Note: Guard clauses are valid only when behavior is preserved exactly — the same input must still
reach the same outcome/exception as before. Restructuring conditionals is fine only when it does not
change which exception is raised for any input.

Error handling is behavior. Dropping a `try`/`except`, a fallback, or a warning because it makes the
code cleaner is not simplification — it moves the failure somewhere harder to see. Same for a
simplification that only passes once you edit a test: that is a behavior change wearing a refactor's
clothes.

### 2. Follow Project Conventions

Simplification means making code more consistent with the codebase, not imposing external
preferences. Read `CLAUDE.md` / `AGENTS.md` / `copilot-instructions.md`, then study how neighboring
code already handles the same problem — import ordering and module system, logging calls (`%s`
substitution, not f-strings), naming, error handling, how deep the type annotations go.

Simplification that breaks project consistency is not simplification — it's churn. Renaming things
to match your own preferences rather than the project's is the most common form of it.

Types don't get you out of this: they document structure, not intent. A well-named function explains
*why* in a way a signature cannot.

### 3. Prefer Clarity Over Cleverness

Explicit code is better than compact code when the compact version requires a mental pause to parse.

```python
# UNCLEAR: Dense conditional chain
status = "new" if is_new else "updated" if is_updated else "archived" if is_archived else "active"


# CLEAR: Readable early-return function
def get_status(item: Item) -> str:
    if item.is_new:
        return "new"
    if item.is_updated:
        return "updated"
    if item.is_archived:
        return "archived"
    return "active"
```

The same applies to a comprehension that has to carry an accumulation, a filter and a nested scan at
once: give the loop its name back.

### 4. Maintain Balance

Simplification has a failure mode: over-simplification. Watch for these traps:

- **Inlining too aggressively** — removing a helper that gave a concept a name makes the call site
  harder to read
- **Combining unrelated logic** — two simple functions merged into one complex function is not
  simpler
- **Removing "unnecessary" abstraction** — some abstractions exist for extensibility or testability,
  not complexity
- **Optimizing for line count** — fewer lines is not the goal; easier comprehension is

### 5. Scope to What Changed

Default to recently modified code, and leave the rest alone unless you were asked to broaden scope.

**Deletion test.** Before noting a piece of code as friction worth addressing, ask: "If I removed
this, would complexity concentrate somewhere else?" If the answer is no, it's a wish-list item —
skip it. If yes, it's real friction worth fixing. Apply this filter to keep the refactor focused on
genuine improvements rather than aesthetic preferences.


## The Simplification Process

### Step 1: Understand Before Touching (Chesterton's Fence)

Before changing or removing anything, understand why it exists. This is Chesterton's Fence: if you
see a fence across a road and don't understand why it's there, don't tear it down. First understand
the reason, then decide if the reason still applies.

```
BEFORE SIMPLIFYING, ANSWER:
- What is this code's responsibility?
- What calls it? What does it call?
- What are the edge cases and error paths?
- Are there tests that define the expected behavior?
- Why might it have been written this way? (Performance? Platform constraint? Historical reason?)
- Check git blame: what was the original context for this code?
```

If you can't answer these, you're not ready to simplify. Read more context first.

### Step 2: Identify Simplification Opportunities

Scan for these patterns — each one is a concrete signal, not a vague smell:

**Structural complexity:**

| Pattern | Signal | Simplification |
|---------|--------|----------------|
| Deep nesting (3+ levels) | Hard to follow control flow | Extract conditions into guard clauses or helper functions |
| Long functions (50+ lines) | Multiple responsibilities | Split into focused functions with descriptive names |
| Nested ternaries | Requires mental stack to parse | Replace with if/else chains or lookup dicts |
| Boolean parameter flags | `do_thing(True, False, True)` | Replace with keyword-only arguments, an enum, or separate functions |
| Repeated conditionals | Same `if` check in multiple places | Extract to a well-named predicate function |
| Shallow modules | Thin pass-through that just delegates to another function without adding any logic | Inline the pass-through, or deepen it by moving caller-side logic inside |
| Feature envy | A function that repeatedly accesses another object's data | Move the logic to where the data lives |
| Primitive obsession | Raw `str`/`dict` used everywhere to represent a concept that has validation rules | Introduce a Pydantic model or named type to carry the concept and its constraints |

**Naming and readability:**

| Pattern | Signal | Simplification |
|---------|--------|----------------|
| Generic names | `data`, `result`, `temp`, `val`, `item` | Rename to describe the content: `user_profile`, `validation_errors` |
| Abbreviated names | `usr`, `cfg`, `btn`, `evt` | Use full words unless the abbreviation is universal (`id`, `url`, `api`) |
| Misleading names | Function named `get` that also mutates state | Rename to reflect actual behavior |
| Comments explaining "what" | `# increment counter` above `count += 1` | Delete the comment — the code is clear enough |
| Comments explaining "why" | `# Retry because the API is flaky under load` | Keep these — they carry intent the code can't express |

**Redundancy:**

| Pattern | Signal | Simplification |
|---------|--------|----------------|
| Duplicated logic | The same block written out twice, in one file or across several — two lines is enough when they encode one decision | Extract to a shared function, or call the one that already exists |
| Dead code | Unreachable branches, unused variables, commented-out blocks | Remove (after confirming it's truly dead) |
| Unnecessary abstractions | Wrapper that adds no value | Inline the wrapper, call the underlying function directly |
| Over-engineered patterns | Factory-for-a-factory, strategy-with-one-strategy | Replace with the simple direct approach |

### Step 3: Apply Changes Incrementally

Make one simplification at a time. Run tests after each change. **Submit refactoring changes
separately from feature or bug fix changes.**

```
FOR EACH SIMPLIFICATION:
1. Make the change
2. Run the test suite
3. If tests pass → commit (or continue to next simplification)
4. If tests fail → revert and reconsider
```

Avoid batching multiple simplifications into a single untested change. If something breaks, you need
to know which simplification caused it.

**The Rule of 500:** If a refactoring would touch more than 500 lines, invest in automation
(codemods, sed scripts, AST transforms) rather than making the changes by hand. Manual edits at that
scale are error-prone and exhausting to review.

### Step 4: Verify the Result

**Always finish by running `git diff --stat`, and report both numbers.** Not "I simplified
`quote()`" — the actual added and deleted line counts. A pass that only adds is a claim that
nothing became obsolete: if that is genuinely true, say so; if it isn't, you have missed a deletion,
so go and find it. This is a prompt to look, not a target to hit — a pass that adds lines and
genuinely reads better is still a success (Principle 4).

Then step back and read the whole diff as a reviewer would: is it genuinely easier to understand,
does it introduce patterns the codebase doesn't use, would a teammate approve it? If the
"simplified" version is harder to follow or harder to review, revert. Not every simplification
attempt succeeds.


## Verification

Run **the project's own checks** — not a standard list. Find them in this order: `CLAUDE.md` /
`AGENTS.md`, then `README`, then `pyproject.toml` / `package.json` / `Makefile`, then the CI config.
Use the commands you find there, scoped to the files you touched, then once across the suite.

**Skip what the project does not configure.** A repo with no `[tool.ruff]` section has not adopted
ruff; running it anyway produces findings about code you did not write, against conventions the
project never agreed to. One probe to establish a tool is absent is fine — working down a checklist
of tools nobody set up is how a refactor pass turns into noise.
