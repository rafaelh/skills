# Tideline

Generates printable tide tables for a harbour from a station's harmonic constituents.

## Commands

```bash
uv run pytest
uv run ruff check . --fix && uv run ruff format .
uv run pyright
```

## Delegation

Three subagents carry work that does not belong in the main context:

| When | Agent | Why |
|---|---|---|
| Before a commit, or after any change to `src/` | `build-green` | The suite prints ~900 lines on a green run; only the verdict matters here |
| After changing a documented command or convention | `docs-drift` | Reading every doc to find one stale command is a whole context window for a one-line answer |
| Before accepting a change to `predict.py` or a station's constituents | `harmonic-review` | The prediction maths is the part of this repo a wrong answer is expensive in |

## Conventions

- Heights are metres above chart datum, `float` is fine — the source data is 2dp
- Constituent amplitudes and phases ship in `stations/*.json`; never inline them in `src/`
- `predict.py` is the only module allowed to import `numpy`
