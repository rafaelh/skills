"""Downsample RGBA buffers to a target size."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def resample(pixels, width, height, target_w, target_h):
    if target_w <= 0 or target_h <= 0:
        raise ValueError("target dimensions must be positive")
    out = []
    xs = width / target_w
    ys = height / target_h
    for ty in range(target_h):
        row = []
        for tx in range(target_w):
            r = 0
            g = 0
            b = 0
            a = 0
            n = 0
            y0 = int(ty * ys)
            y1 = int((ty + 1) * ys)
            # A non-integer ratio can collapse the window to zero rows, and a zero-high
            # box drops the last scanline of the image — widen it instead of skipping.
            if y1 <= y0:
                y1 = y0 + 1
            x0 = int(tx * xs)
            x1 = int((tx + 1) * xs)
            if x1 <= x0:
                x1 = x0 + 1
            for y in range(y0, y1):
                if y < height:
                    for x in range(x0, x1):
                        if x < width:
                            p = pixels[y * width + x]
                            r = r + p[0]
                            g = g + p[1]
                            b = b + p[2]
                            a = a + p[3]
                            n = n + 1
            if n == 0:
                row.append((0, 0, 0, 0))
            else:
                row.append((r // n, g // n, b // n, a // n))
        out.append(row)
    logger.debug("resampled %sx%s to %sx%s", width, height, target_w, target_h)
    return out


def thumbnail(pixels, width, height, box):
    s = width
    if height > s:
        s = height
    f = box / s
    tw = int(width * f)
    th = int(height * f)
    if tw < 1:
        tw = 1
    if th < 1:
        th = 1
    return resample(pixels, width, height, tw, th)
