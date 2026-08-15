#!/usr/bin/env python3
# agent-tool: false
"""Resolve wikilink targets to vault notes.

A `Resolver` builds a name index for a vault: every note's basename, its
vault-relative path, and each frontmatter alias maps (case-insensitively)
to that note. Multiple notes can share a name; resolve() returns the set.

Library API:
    Resolver(vault)
        .resolve(target)    -> set[Path]   notes that the target resolves to
        .names_for(note)    -> set[str]    lowercase names that resolve to note
        .matches(target, note) -> bool

The index is built lazily on the first query and cached for the lifetime
of the Resolver. Construct a fresh Resolver after the vault changes.

This module owns the case-insensitivity and alias-inclusion semantics that
were previously implicit in `backlinks.py` and `rename_note.py`. Callers
get correctness; tests have a single surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from vault import iter_notes, relpath_no_ext
from vault_frontmatter import FrontmatterError, read

PathLike = str | Path


class Resolver:
    def __init__(self, vault: PathLike):
        self.vault = Path(vault)
        self._forward: dict[str, set[Path]] = {}
        self._reverse: dict[Path, set[str]] = {}
        self._built = False

    def _collect_names(self, note: Path) -> set[str]:
        names: set[str] = {note.stem.lower(), relpath_no_ext(self.vault, note).lower()}
        try:
            fm, _ = read(note)
        except FrontmatterError, OSError:
            return names
        aliases: Any = fm.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        elif not isinstance(aliases, list):
            return names
        for alias in cast("list[Any]", aliases):
            if isinstance(alias, str):
                names.add(alias.lower())
        return names

    def _build(self) -> None:
        if self._built:
            return
        for note in iter_notes(self.vault):
            note_resolved = note.resolve()
            names = self._collect_names(note)
            self._reverse[note_resolved] = names
            for name in names:
                self._forward.setdefault(name, set()).add(note_resolved)
        self._built = True

    def resolve(self, target: str) -> set[Path]:
        self._build()
        return set(self._forward.get(target.lower(), set()))

    def names_for(self, note: PathLike) -> set[str]:
        self._build()
        return set(self._reverse.get(Path(note).resolve(), set()))

    def matches(self, target: str, note: PathLike) -> bool:
        return Path(note).resolve() in self.resolve(target)
