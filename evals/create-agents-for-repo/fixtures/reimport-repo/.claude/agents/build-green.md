---
name: build-green
description: Run the full build pipeline and report pass/fail.
model: sonnet
tools:
  - Bash
  - Read
---

# Build Green

Run the full test/lint/type-check suite and report results.

## Instructions

Run these commands in order:
```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## Return contract

Return a short summary: pass or fail, and if fail, the specific failing commands with their first error line. Do not paste full logs.
