from __future__ import annotations

from pathlib import Path

from logscan.scanner import scan, summarize

DATA = Path(__file__).parent / "data" / "sample.log"
RULES = Path(__file__).parent.parent / "config" / "rules.json"


def test_only_the_kept_levels_come_back():
    hits = scan(DATA, RULES)
    assert [hit["level"] for hit in hits] == ["ERROR", "WARN", "FATAL"]


def test_a_hit_carries_the_owning_team():
    hits = scan(DATA, RULES)
    assert hits[0]["service"] == "checkout"
    assert hits[0]["owner"] == "payments"


def test_the_older_layout_without_an_instance_still_matches():
    hits = scan(DATA, RULES)
    assert hits[1]["service"] == "search"
    assert hits[1]["message"] == "cache miss, falling back to origin"


def test_summarize_counts_hits_per_team():
    assert summarize(scan(DATA, RULES)) == {"payments": 1, "discovery": 1, "unassigned": 1}
