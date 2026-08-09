"""Render validated widget configs to SVG strings."""

from __future__ import annotations

from .schema import WidgetConfig


def render_widget(config: WidgetConfig) -> str:
    """Render a single widget to an SVG string."""
    rx = f' rx="{config.border_radius}"' if config.border_radius else ""
    label_el = ""
    if config.label:
        cx = config.width // 2
        cy = config.height // 2
        label_el = (
            f'  <text x="{cx}" y="{cy}" text-anchor="middle" '
            f'dominant-baseline="central" font-size="14">{config.label}</text>\n'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{config.width}" height="{config.height}">\n'
        f'  <rect width="{config.width}" height="{config.height}" '
        f'fill="{config.fill}" stroke="{config.stroke}" '
        f'stroke-width="{config.stroke_width}"{rx}/>\n'
        f"{label_el}"
        f"</svg>\n"
    )


def render_batch(configs: list[WidgetConfig]) -> list[str]:
    """Render multiple widgets, returning one SVG string per config."""
    return [render_widget(c) for c in configs]
