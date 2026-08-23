from __future__ import annotations

from imaging.exports import rendition


def test_the_web_rendition_is_four_by_four():
    out = rendition([(1, 1, 1, 1)] * 64, 8, 8, "web")
    assert len(out) == 4
    assert len(out[0]) == 4
