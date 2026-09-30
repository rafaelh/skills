import pytest

from sparkfile.index import Note, build
from sparkfile.parse import ParseError, split_front_matter


def test_index_maps_tokens_to_slugs():
    index = build([Note("a", "A", "harbour tide table")])
    assert index["harbour"] == ["a"]


def test_short_tokens_are_dropped():
    assert "of" not in build([Note("a", "A", "of the harbour")])


def test_missing_front_matter_raises():
    with pytest.raises(ParseError):
        split_front_matter("no front matter here")
