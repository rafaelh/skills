from __future__ import annotations

from nightly.report import build_report, top_services

TEAMS = {"checkout": "payments", "search": "discovery"}


def event(kind="deploy", service="checkout", at="01:00:00"):
    return {"at": at, "service": service, "kind": kind}


def test_one_event_renders_one_line():
    body = build_report([event()], TEAMS)
    assert body.startswith("Nightly activity\n================\n")
    assert body.splitlines()[2] == "01:00:00 checkout      payments    deploy"


def test_lines_follow_the_order_events_arrived():
    events = [
        event(at="02:00:00", service="search"),
        event(at="01:00:00", kind="incident"),
    ]
    lines = build_report(events, TEAMS).splitlines()[2:]
    assert [line.split()[0] for line in lines] == ["02:00:00", "01:00:00"]


def test_top_services_counts_events_per_service():
    events = [event(service="checkout")] * 3 + [event(service="search")]
    assert top_services(events) == [("checkout", 3), ("search", 1)]
