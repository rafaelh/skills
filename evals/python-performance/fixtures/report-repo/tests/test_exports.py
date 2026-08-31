from __future__ import annotations

from nightly.exports import as_csv, group_by_team, team_is_known


def test_group_by_team_collects_rows():
    rows = [{"team": "payments", "n": 1}, {"team": "payments", "n": 2}]
    assert len(group_by_team(rows)["payments"]) == 2


def test_as_csv_writes_a_header_row():
    rows = [{"service": "checkout", "n": 3}]
    assert as_csv(rows, ["service", "n"]) == "service,n\ncheckout,3\n"


def test_team_is_known():
    assert team_is_known({"payments": []}, "payments")
    assert not team_is_known({"payments": []}, "discovery")
