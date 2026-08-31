"""Behaviour `report-repo`'s own suite leaves unpinned.

Never staged into the fixture: a run that can read these has been handed the answer, and
"the digest still says the same thing" stops being the thing under test. `grade.py` drops
this file into a throwaway copy of the run's repo once the run has finished.

Every case here is reachable from the repo itself — the placeholder and the allowed-kind
list from `build_report`, the tie order from the comment above the sort, the fallback team
from the `.get` call — so a run that reads before it rewrites keeps all of them.
"""

# agent-tool: false

from __future__ import annotations

from nightly.report import build_report, top_services

TEAMS = {"checkout": "payments", "search": "discovery"}


def event(kind="deploy", service="checkout", at="01:00:00"):
    return {"at": at, "service": service, "kind": kind}


def test_a_night_with_no_events_renders_the_placeholder():
    assert build_report([], TEAMS) == "Nightly activity\n================\nNo activity recorded.\n"


def test_a_night_of_only_unreportable_kinds_renders_the_placeholder():
    body = build_report([event(kind="heartbeat"), event(kind="heartbeat")], TEAMS)
    assert body == "Nightly activity\n================\nNo activity recorded.\n"


def test_unreportable_kinds_are_dropped_from_a_mixed_night():
    body = build_report([event(kind="heartbeat"), event(kind="page")], TEAMS)
    assert [line.split()[-1] for line in body.splitlines()[2:]] == ["page"]


def test_a_service_with_no_team_falls_back_to_unassigned():
    body = build_report([event(service="ledger")], TEAMS)
    assert "unassigned" in body.splitlines()[2]


def test_ties_in_top_services_go_to_the_alphabetically_first():
    events = [event(service="search"), event(service="billing"), event(service="auth")]
    assert [name for name, _ in top_services(events)] == ["auth", "billing", "search"]


def test_top_services_honours_the_limit():
    events = [event(service=name) for name in ("a", "b", "c", "d", "e", "f")]
    assert len(top_services(events, limit=5)) == 5
