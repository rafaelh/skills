"""Parse a note file into front matter and body."""

from __future__ import annotations


class ParseError(ValueError):
    pass


def split_front_matter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        raise ParseError("note has no front matter")
    end = text.find("\n---\n", 3)
    if end == -1:
        raise ParseError("unterminated front matter")
    return text[4:end], text[end + 5 :]
