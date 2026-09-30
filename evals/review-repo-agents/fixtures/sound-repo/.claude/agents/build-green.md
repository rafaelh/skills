---
name: build-green
description: Run the full test, lint and type-check pipeline and return only the verdict. Use before a commit or after any change under src/.
model: haiku
tools:
  - Bash
  - Read
---

# Build Green

Run the project's checks and report whether they pass.

## Instructions

Run these three, in order, and stop at the first that fails:

```bash
uv run pytest -q
uv run ruff check .
uv run pyright
```

## Return contract

Return one of:

- `GREEN` — all three passed.
- `RED <command>` — followed by the failing test ids or the first five diagnostics, at most 20 lines.

Never paste a full log; the caller wants the verdict, not the run.
