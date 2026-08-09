---
name: content-audit
description: Audit content for consistency and quality issues.
model: opus
tools:
  - Read
  - Glob
  - Grep
---

# Content Audit

Review source files for naming consistency, dead code, and structural issues.

## Instructions

1. Walk `src/` and identify unused imports, unreachable code, inconsistent naming
2. Check for functions >50 lines that should be split
3. Flag any `# TODO` or `# HACK` comments older than the last release

## Return contract

Return a prioritised list of findings (max 15), each with file path, line, and one-sentence description.
