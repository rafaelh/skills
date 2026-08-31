# logscan

The on-call log sweep. `logscan.scanner` reads a day of service logs, keeps the lines the
rules file cares about, and attaches the team that owns each service.

## Commands

```bash
python -m pytest -q
```

## Conventions

- `from __future__ import annotations` at the top of every module.
- Logging uses `%s` placeholders, never f-strings.
- `config/rules.json` is generated from the service catalogue and is not edited by hand.
  It is read at scan time rather than imported, so a catalogue change takes effect on the
  next sweep without a redeploy.
