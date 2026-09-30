# Ledgerline

A CLI that reconciles bank exports against an invoice ledger and emits a settlement report.

## Commands

```bash
uv run pytest
uv run ruff check . --fix && uv run ruff format .
uv run pyright
```

## Quick Reference

- Tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Type-check: `uv run pyright`
- Reconcile: `uv run ledgerline reconcile <export.csv>`

## Delegation

- Running the suite → `test-runner`

## Conventions

- Money is `Decimal`, never `float` — bank exports carry four decimal places
- Matching rules live in `src/ledgerline/reconcile.py`
- Settlement output is newline-delimited JSON, one row per matched pair
