---
name: refactor
description: "Refactor code for clarity, maintainability, and reduced complexity. Use when code works but is harder to read, maintain, or extend than it should be."
---

# Refactor

## Steps

1. Identify the target: function, module, or class to improve
2. Run `uv run pytest` to confirm current tests pass
3. Apply the refactoring (extract, rename, inline, simplify)
4. Run `uv run pytest` to confirm nothing broke
5. Run `uv run pyright` to confirm types
6. Run `uv run ruff check .` to confirm lint
