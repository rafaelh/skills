# Tideline

Printable tide tables for a harbour, predicted from the station's harmonic constituents.

```bash
uv run tideline table whitby --days 7
```

Stations live in `stations/`. Each file is the set of constituents the hydrographic office
publishes for that station, with Greenwich phase lags in degrees.

## Development

```bash
uv run pytest
uv run ruff check . --fix && uv run ruff format .
uv run pyright
```
