"""TOML config schema validation for widget definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class WidgetConfig:
    name: str
    width: int
    height: int
    fill: str = "#ffffff"
    stroke: str = "#000000"
    stroke_width: float = 1.0
    border_radius: float = 0.0
    label: str = ""


class ValidationError(Exception):
    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(f"{field}: {message}")


def validate(raw: dict[str, Any]) -> WidgetConfig:
    """Validate a raw TOML dict into a WidgetConfig."""
    required = {"name", "width", "height"}
    missing = required - raw.keys()
    if missing:
        raise ValidationError("root", f"missing required fields: {sorted(missing)}")

    if not isinstance(raw["name"], str) or not raw["name"].strip():
        raise ValidationError("name", "must be a non-empty string")

    for dim in ("width", "height"):
        val = raw[dim]
        if not isinstance(val, int) or val <= 0:
            raise ValidationError(dim, "must be a positive integer")

    return WidgetConfig(
        name=raw["name"],
        width=raw["width"],
        height=raw["height"],
        fill=str(raw.get("fill", "#ffffff")),
        stroke=str(raw.get("stroke", "#000000")),
        stroke_width=float(raw.get("stroke_width", 1.0)),
        border_radius=float(raw.get("border_radius", 0.0)),
        label=str(raw.get("label", "")),
    )
