# inventory

Warehouse stock for the distribution centres.

## Commands

```bash
python -m pytest -q
python -m pytest tests/test_restock.py -q
```

## Conventions

- Money is `Decimal`, never `float`.
- Logging uses `%s` placeholders, never f-strings.
- `from __future__ import annotations` at the top of every module.
- Quantities are whole units; packs are whole packs.
