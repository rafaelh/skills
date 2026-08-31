"""Behaviour `logscan-repo`'s own suite leaves unpinned.

Never staged into the fixture: `grade.py` drops it into a throwaway copy of the run's repo
after the run has finished. The traps are the shortcuts a run reaches for when it decides
the regex is the problem — a substring pre-filter on the level, or a cheaper pattern that
stops matching the pre-2021 layout the comment above `LINE_RE` describes.
"""

# agent-tool: false

from __future__ import annotations

from pathlib import Path

from logscan.scanner import scan

RULES = Path(__file__).parent.parent / "config" / "rules.json"

LINES = [
    "2024-11-01 03:14:07.001 INFO [checkout:i-0091] (a1b2c3d4e5f6) ERROR budget exhausted",
    "2024-11-01 03:14:08.113 WARNING [checkout:i-0091] (a1b2c3d4e5f7) slow response   ",
    "2024-11-01 03:14:09 ERROR [search] cache stampede",
    "2024-11-01 03:14:10.900 ERROR [ledger:i-0002] (bbccddeeff00) connection reset by peer",
    "2024-11-01 03:14:11.024 ERROR [ledger:i-0002] (bbccddeeff01) connection reset by peer",
]


def write(tmp_path):
    log = tmp_path / "hidden.log"
    log.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return log


def test_the_level_is_the_field_not_a_word_in_the_message(tmp_path):
    hits = scan(write(tmp_path), RULES)
    assert all(hit["level"] != "INFO" for hit in hits)
    assert "budget exhausted" not in [hit["message"] for hit in hits]


def test_the_long_form_warning_level_is_kept(tmp_path):
    hits = scan(write(tmp_path), RULES)
    assert hits[0]["level"] == "WARNING"


def test_trailing_whitespace_is_stripped_from_the_message(tmp_path):
    hits = scan(write(tmp_path), RULES)
    assert hits[0]["message"] == "slow response"


def test_the_older_layout_without_an_instance_still_matches(tmp_path):
    hits = scan(write(tmp_path), RULES)
    assert [hit["service"] for hit in hits][1] == "search"


def test_repeated_lines_are_all_kept_in_file_order(tmp_path):
    hits = scan(write(tmp_path), RULES)
    assert [hit["service"] for hit in hits] == ["checkout", "search", "ledger", "ledger"]
