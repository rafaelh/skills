---
name: tdd
description: "Use this skill when the user wants to build features or fix bugs using TDD (test-driven development), mentions red-green-refactor, or asks for test-first development."
---

# TDD

Red-green-refactor workflow for this repo.

## Steps

1. Write a failing test that captures the requirement
2. Run `uv run pytest` and confirm it fails for the right reason
3. Write the minimum code to make it pass
4. Run `uv run pytest` again — confirm green
5. Refactor while staying green
6. Run `uv run pyright` to confirm types still check
