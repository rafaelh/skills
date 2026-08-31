# checkout

The checkout review page. `checkout.summarize` builds the summary block the page renders;
`checkout.pricing_client` fetches the live prices it is built from.

## Commands

```bash
python -m pytest -q
```

## Conventions

- `from __future__ import annotations` at the top of every module.
- Logging uses `%s` placeholders, never f-strings.
- An order carries at most 200 line items. The API rejects anything larger, so nothing
  downstream of it needs to handle a bigger basket.
