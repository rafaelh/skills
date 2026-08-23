# toolkit

Shared helpers used by four services in this org. Small on purpose: anything that grows a second
responsibility moves out into its own package.

## Commands

```bash
python -m pytest -q
```

## Conventions

- Every public function carries a one-line docstring saying what it returns.
- `from __future__ import annotations` at the top of every module; imports used only in
  annotations go under `TYPE_CHECKING`.
- Logging uses `%s` placeholders, never f-strings.
- Public names are stable — four services import from here, so renaming an exported function is a
  breaking change and needs its own deprecation cycle.
