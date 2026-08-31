# nightly

The on-call activity digest. A cron job collects the night's events and `nightly.report`
renders them into the plain-text digest that gets posted to the on-call channel.

## Commands

```bash
python -m pytest -q
```

## Conventions

- `from __future__ import annotations` at the top of every module.
- Logging uses `%s` placeholders, never f-strings.
- The digest text is a contract: the on-call bot diffs each night's digest against the
  previous one, so the rendered layout and line order are behaviour, not formatting.
