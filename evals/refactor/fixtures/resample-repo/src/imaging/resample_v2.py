"""Box-filter resampling with the alpha plane averaged rather than dropped.

Replaces `resample.py`. `thumbnails.py` is on this path already; `exports.py` is the
last caller left on the old module, and the old module goes when that call site moves.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

TRANSPARENT = (0, 0, 0, 0)


def _window(index, ratio, extent):
    """The half-open source span one target row or column averages over."""
    start = int(index * ratio)
    stop = max(int((index + 1) * ratio), start + 1)
    return start, min(stop, extent)


def _average(pixels, width, xs, ys):
    """The mean of every channel across the pixels in `xs` x `ys`, alpha included."""
    channels = [0, 0, 0, 0]
    count = 0
    for y in range(*ys):
        for x in range(*xs):
            pixel = pixels[y * width + x]
            channels = [total + value for total, value in zip(channels, pixel)]
            count += 1
    if not count:
        return TRANSPARENT
    return tuple(total // count for total in channels)


def resample(pixels, width, height, target_width, target_height):
    """`pixels` box-filtered down to `target_width` x `target_height`, row-major."""
    if target_width <= 0 or target_height <= 0:
        raise ValueError("target dimensions must be positive")
    x_ratio = width / target_width
    y_ratio = height / target_height
    logger.debug("resampling %sx%s to %sx%s", width, height, target_width, target_height)
    return [
        [
            _average(pixels, width, _window(tx, x_ratio, width), _window(ty, y_ratio, height))
            for tx in range(target_width)
        ]
        for ty in range(target_height)
    ]
