"""Text normalisation helpers."""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_UNSAFE = re.compile(r"[^a-z0-9]+")


def collapse_whitespace(text: str) -> str:
    """Every run of whitespace in `text` reduced to one space, with the ends trimmed."""
    return _WHITESPACE.sub(" ", text).strip()


def slugify(text: str) -> str:
    """A lowercase, hyphen-separated slug of `text`."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return _UNSAFE.sub("-", folded.lower()).strip("-")


def truncate(text: str, limit: int, suffix: str = "...") -> str:
    """`text` cut to at most `limit` characters, with `suffix` marking the cut."""
    if limit < len(suffix):
        raise ValueError("limit must leave room for the suffix")
    if len(text) <= limit:
        return text
    return text[: limit - len(suffix)] + suffix


def title_words(text: str) -> list[str]:
    """The words of `text`, whitespace-collapsed and capitalised."""
    cleaned = _WHITESPACE.sub(" ", text).strip()
    return [word.capitalize() for word in cleaned.split(" ") if word]
