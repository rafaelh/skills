# imaging

Image processing for the asset pipeline.

## Commands

```bash
python -m pytest -q
python -m pytest tests/test_resample.py -q
```

## Conventions

- Pixels are `(r, g, b, a)` tuples of ints; buffers are flat row-major lists.
- Logging uses `%s` placeholders, never f-strings.
- `from __future__ import annotations` at the top of every module.
