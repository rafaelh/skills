# Widgetly

A CLI tool for generating SVG widget previews from TOML config files.

## Commands

```bash
pytest tests/ -v
ruff check . --fix && ruff format .
mypy src/
```

## Quick Reference

- Tests: `pytest tests/`
- Lint: `ruff check .`
- Format: `ruff format .`
- Type-check: `mypy src/`

## Conventions

- All public functions have type annotations
- Tests mirror `src/` layout under `tests/`
- Config schema lives in `src/widgetly/schema.py`; validate before rendering
- SVG output goes through `src/widgetly/render.py`; never write raw SVG strings inline
