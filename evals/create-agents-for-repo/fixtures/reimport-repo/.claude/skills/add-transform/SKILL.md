---
name: add-transform
description: "Add a new transform type to the pipeline. Use when the user wants to add a new data transformation (e.g. join, aggregate, deduplicate) to the formwork pipeline."
---

# Add Transform

## Steps

1. Define the transform schema in `transforms/` as a new YAML example
2. Write a failing test for the new transform type in `tests/test_pipeline.py`
3. Add the handler to `apply_transforms()` in `src/formwork/pipeline.py`
4. Run `uv run pytest tests/test_pipeline.py` to confirm green
5. Run `uv run pyright` to confirm types
6. Update the README if the transform has non-obvious config
