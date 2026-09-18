# Sparkfile

Turns a directory of markdown notes into a searchable static site.

## Commands

```bash
uv run pytest
uv run pytest --cov=src/sparkfile --cov-report=term-missing
uv run ruff check . --fix && uv run ruff format .
uv run pyright
```

## Delegation

| When | Agent |
|---|---|
| Before a release | `coverage-gate` |
| Asked what changed in a release | `changelog-reader` |
| Working through a design problem | `pair-programmer` |

## Conventions

- Note front matter is YAML; anything else is a parse error, not a warning
- The index is rebuilt whole, never patched
- Coverage must not drop below 85% on `src/sparkfile`
