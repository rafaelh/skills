---
name: docs-drift
description: Check whether documentation matches the current code.
model: sonnet
tools:
  - Read
  - Glob
  - Grep
---

# Docs Drift

Scan for drift between docs (README.md, CLAUDE.md, docstrings) and the actual code.

## Instructions

1. Read README.md, CLAUDE.md, and any docs/ files
2. For each documented command, verify it still works or the function still exists
3. For each documented convention, grep for violations

## Return contract

Return a bulleted list of drift findings (max 10). Each item: what the docs say vs what the code does. If nothing drifted, say "No drift found."
