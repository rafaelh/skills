"""Export renditions for the download bundle."""

from __future__ import annotations

from imaging.resample import resample

RENDITIONS = {"web": (4, 4), "print": (8, 8)}


def rendition(pixels, width, height, name):
    """The named rendition of `pixels`, as a row-major list of rows."""
    target_w, target_h = RENDITIONS[name]
    return resample(pixels, width, height, target_w, target_h)
