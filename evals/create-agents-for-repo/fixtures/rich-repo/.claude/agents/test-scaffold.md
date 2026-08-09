---
name: test-scaffold
description: Generate test scaffolding for untested modules.
model: haiku
tools:
  - Bash
  - Read
  - Write
---

# Test Scaffold

Find modules in `src/` without corresponding tests and generate starter test files.

## Instructions

1. List all `.py` files under `src/formwork/`
2. For each, check if a matching `tests/test_<module>.py` exists
3. For missing ones, generate a test file with one placeholder test per public function

## Return contract

Return: list of test files created, one line each. If all modules are covered, say "All modules have tests."
