# ingest

The nightly CRM import. `ingest.importer` joins the night's transaction rows against the
customer export and writes the entries the billing ledger reconciles against.

## Commands

```bash
python -m pytest -q
```

## Conventions

- `from __future__ import annotations` at the top of every module.
- Logging uses `%s` placeholders, never f-strings.
- The CRM export is read as-is. We do not clean, dedupe or re-order it on the way in —
  finance reconciles against the vendor's own file and any reshaping upstream of the
  ledger has to be reproducible from it.
