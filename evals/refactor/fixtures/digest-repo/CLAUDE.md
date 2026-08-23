# notify

Notification digests for the watcher service.

## Commands

```bash
python -m pytest -q
python -m pytest tests/test_digest.py -q
```

## Conventions

- Logging uses `%s` placeholders, never f-strings.
- `from __future__ import annotations` at the top of every module.
- Rendering functions return strings; nothing in `notify/` sends anything.
