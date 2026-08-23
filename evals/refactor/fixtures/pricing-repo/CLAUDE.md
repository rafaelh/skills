# storefront

Order pricing for the storefront checkout. `pricing.py` is the live path; `legacy_invoice.py`
renders for the old back-office and is frozen pending its retirement.

## Commands

```bash
python -m pytest -q          # the whole suite
python -m pytest tests/test_pricing.py -q
```

## Conventions

- **Money is `Decimal`, never `float`.** Anything that converts to `float` mid-calculation is a
  bug — the 2019 rounding incident came from exactly that.
- **Logging uses `%s` placeholders, never f-strings.** `logger.warning("bad tier %s", tier)`, not
  `logger.warning(f"bad tier {tier}")`. The log pipeline groups on the format string.
- `from __future__ import annotations` at the top of every module.
- Public helpers are named for what they return; private ones take a leading underscore.
