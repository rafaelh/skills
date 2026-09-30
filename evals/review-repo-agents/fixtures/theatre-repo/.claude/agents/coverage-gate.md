---
name: coverage-gate
description: Run the coverage suite and return the single total percentage plus any file that fell below the floor. Use before a release.
model: haiku
tools:
  - Bash
  - Read
---

# Coverage Gate

Check coverage against the 85% floor in CLAUDE.md.

## Instructions

```bash
uv run pytest --cov=src/sparkfile --cov-report=term-missing
```

## Return contract

Return the total percentage on one line, then any file under 85% with its percentage — at most ten lines in total. The term-missing report runs to several hundred lines; none of it belongs in the caller's context.
