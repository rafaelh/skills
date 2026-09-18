"""Build the search index from parsed notes."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Note:
    slug: str
    title: str
    body: str


def build(notes: list[Note]) -> dict[str, list[str]]:
    """Token -> slugs. Rebuilt whole every time; see CLAUDE.md."""
    index: dict[str, list[str]] = defaultdict(list)
    for note in notes:
        for token in {t.lower() for t in note.body.split() if len(t) > 2}:
            index[token].append(note.slug)
    return dict(index)
