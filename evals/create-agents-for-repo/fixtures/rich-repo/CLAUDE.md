# Formwork

A data-pipeline CLI that reads CSV/Parquet, applies transform rules from YAML configs, and writes
output to Parquet or PostgreSQL.

## Commands

```bash
uv run pytest
uv run ruff check . --fix && uv run ruff format .
uv run pyright
```

## Quick Reference

- Tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Type-check: `uv run pyright`
- Run pipeline: `uv run formwork run <config.yaml>`

## Conventions

- Transform rules live in `transforms/`; each is a YAML file
- Pipeline orchestration in `src/formwork/pipeline.py`
- Database writes go through `src/formwork/sink.py`
- Never commit `.env` — credentials come from env vars at runtime
- Test fixtures in `tests/fixtures/`; keep them small (< 50 rows)
