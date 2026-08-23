from __future__ import annotations

import pytest

from imaging.resample_v2 import resample


def solid(width, height, pixel):
    return [pixel] * (width * height)


def test_a_solid_image_downsamples_to_the_same_colour():
    pixels = solid(4, 4, (10, 20, 30, 255))
    assert resample(pixels, 4, 4, 2, 2) == [[(10, 20, 30, 255)] * 2] * 2


def test_a_two_by_two_block_averages_every_channel():
    pixels = [(0, 0, 0, 0), (10, 10, 10, 10), (20, 20, 20, 20), (30, 30, 30, 30)]
    assert resample(pixels, 2, 2, 1, 1) == [[(15, 15, 15, 15)]]


def test_alpha_is_averaged_rather_than_dropped():
    pixels = [(0, 0, 0, 0), (0, 0, 0, 255), (0, 0, 0, 0), (0, 0, 0, 255)]
    assert resample(pixels, 2, 2, 1, 1)[0][0][3] == 127


def test_a_non_positive_target_is_rejected():
    with pytest.raises(ValueError):
        resample(solid(2, 2, (0, 0, 0, 0)), 2, 2, 1, 0)
