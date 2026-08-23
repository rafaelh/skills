from __future__ import annotations

from imaging.thumbnails import thumbnail


def test_a_small_thumbnail_fits_the_box():
    out = thumbnail([(2, 2, 2, 2)] * (64 * 32), 64, 32, "small")
    assert len(out) == 16
    assert len(out[0]) == 32
