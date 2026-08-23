"""Filesystem path helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


def ensure_dir(path: Path) -> Path:
    """Create `path` and its parents if they are absent, and return `path`."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def relative_to_root(path: Path, root: Path) -> Path:
    """`path` expressed relative to `root`, or unchanged when it lies outside `root`."""
    resolved = path.resolve()
    resolved_root = root.resolve()
    if resolved.is_relative_to(resolved_root):
        return resolved.relative_to(resolved_root)
    return path


def newest(paths: Iterable[Path]) -> Path | None:
    """The most recently modified of `paths` that exists, or None when none do."""
    existing = [path for path in paths if path.exists()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)
