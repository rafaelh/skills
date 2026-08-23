from __future__ import annotations

import pytest

from imaging.resample import resample, thumbnail


def solid(width, height, pixel):
    return [pixel] * (width * height)


def test_a_solid_image_downsamples_to_the_same_colour():
    pixels = solid(4, 4, (10, 20, 30, 255))
    assert resample(pixels, 4, 4, 2, 2) == [[(10, 20, 30, 255)] * 2] * 2


def test_a_two_by_two_block_averages():
    pixels = [(0, 0, 0, 0), (10, 10, 10, 10), (20, 20, 20, 20), (30, 30, 30, 30)]
    assert resample(pixels, 2, 2, 1, 1) == [[(15, 15, 15, 15)]]


def test_the_output_has_the_requested_shape():
    out = resample(solid(6, 4, (1, 2, 3, 4)), 6, 4, 3, 2)
    assert len(out) == 2
    assert all(len(row) == 3 for row in out)


def test_a_non_positive_target_is_rejected():
    with pytest.raises(ValueError):
        resample(solid(2, 2, (0, 0, 0, 0)), 2, 2, 0, 1)


def test_thumbnail_keeps_the_aspect_ratio():
    out = thumbnail(solid(8, 4, (1, 1, 1, 1)), 8, 4, 4)
    assert len(out) == 2
    assert len(out[0]) == 4
