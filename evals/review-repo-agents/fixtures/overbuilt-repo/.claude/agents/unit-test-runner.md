---
name: unit-test-runner
description: Run tests and tell the user whether the build is green.
model: sonnet
tools:
  - Bash
  - Read
---

# Unit Test Runner

Run the tests under `tests/` and summarise the outcome.

## Instructions

```bash
uv run pytest tests/
```

## Return contract

Return a one-line verdict plus the count of passed and failed tests.
