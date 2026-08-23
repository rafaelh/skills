"""Thumbnail sizes for the asset browser."""

from __future__ import annotations

from imaging.resample_v2 import resample

SIZES = {"small": 32, "medium": 64}


def thumbnail(pixels, width, height, size="small"):
    """`pixels` scaled so its longest side is `SIZES[size]`, aspect ratio kept."""
    box = SIZES[size]
    scale = box / max(width, height)
    return resample(pixels, width, height, max(int(width * scale), 1), max(int(height * scale), 1))
