#!/usr/bin/env python3
# agent-tool: false
"""Data shapes passed between this skill's scripts.

Every dataclass lives here so a reader has one place to look for the shape
of a result. The functions that build them stay in their owning module:

    Wikilink, Tag     <- links.parse_links / links.parse_tags
    Backlink          <- backlinks.find_backlinks
    ValidationResult  <- base_validate.validate_base,
                         canvas_validate.validate_canvas
    RenameResult      <- rename_note.rename_note
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Wikilink:
    target: str
    heading: str | None
    block: str | None
    display: str | None
    is_embed: bool
    raw: str
    span: tuple[int, int]


@dataclass
class Tag:
    name: str
    raw: str
    span: tuple[int, int]


@dataclass
class Backlink:
    source: Path
    target_form: str  # the literal target in the wikilink
    is_embed: bool
    heading: str | None
    block: str | None
    display: str | None
    span: tuple[int, int]


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list[str])


@dataclass
class RenameResult:
    moved: bool
    updated_files: list[Path] = field(default_factory=list[Path])
    canvas_warnings: list[Path] = field(default_factory=list[Path])
