---
name: commit-msg
description: Write a conventional-commit message for the staged changes.
model: sonnet
---

# Commit Message

Draft a commit message for what is currently staged.

## Instructions

1. Run `git diff --cached`
2. Check the change is clean first:

```bash
black --check .
mypy src/
```

3. Write a conventional-commit subject and body

## Return contract

Return the commit message and nothing else.
