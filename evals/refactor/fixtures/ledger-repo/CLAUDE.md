# ledger

Double-entry bookkeeping for the finance back office.

| Module | State |
|---|---|
| `posting.py` | Stable since 2021. Every change here needs a finance sign-off. |
| `export.py` | Frozen — the finance team's macros parse the exact column order. |
| `reconcile.py` | Landed today. Statement-to-ledger matching. |

## Commands

```bash
python -m pytest -q
python -m pytest tests/test_reconcile.py -q
```

## Conventions

- Money is `Decimal`, never `float`.
- Logging uses `%s` placeholders, never f-strings.
- `from __future__ import annotations` at the top of every module.
