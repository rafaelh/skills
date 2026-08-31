from __future__ import annotations

from ingest.textutil import normalize_name


def test_whitespace_is_collapsed():
    assert normalize_name("north   harbour") == "North Harbour"


def test_a_company_suffix_is_dropped():
    assert normalize_name("granite quill Ltd.") == "Granite Quill"
