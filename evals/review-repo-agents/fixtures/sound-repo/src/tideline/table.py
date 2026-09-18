"""Render a predicted series as a printable table."""

from __future__ import annotations


def render(rows: list[tuple[str, float]]) -> str:
    return "\n".join(f"{when:<16}{height:>7.2f}" for when, height in rows)
