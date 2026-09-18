---
name: docs-drift
description: Check README.md and CLAUDE.md against the code under src/ and report what has gone stale. Use after changing a documented command or convention.
model: sonnet
tools:
  - Read
  - Glob
  - Grep
---

# Docs Drift

Find places where the documentation and the code disagree.

## Instructions

1. Collect every documented command and every documented convention from README.md and CLAUDE.md
2. For each command, confirm the entry point still exists
3. For each convention, grep `src/` for violations

## Return contract

Return at most ten findings, each one line: what the docs claim, and what the code does instead. If nothing has drifted, return `No drift found.` and stop.
