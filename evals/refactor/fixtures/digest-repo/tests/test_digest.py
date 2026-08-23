from __future__ import annotations

from notify.digest import format_digest


def event(subject, priority=1, actor="ada", **extra):
    return {"subject": subject, "priority": priority, "actor": actor, **extra}


def test_one_event_renders_one_line():
    assert format_digest([event("build failed")]) == "  ada: build failed"


def test_high_priority_lines_are_flagged():
    assert format_digest([event("outage", priority=2)]) == "! ada: outage"


def test_events_are_ordered_by_priority():
    body = format_digest([event("low", priority=0), event("high", priority=3)])
    assert body.splitlines()[0] == "! ada: high"


def test_muted_events_are_dropped():
    body = format_digest([event("seen", muted=True), event("build failed")])
    assert body == "  ada: build failed"


def test_children_are_rendered_under_their_parent():
    parent = event("release", priority=3, children=[event("step one", priority=1)])
    body = format_digest([parent])
    assert body.splitlines() == ["! ada: release", "  ada:   step one"]


def test_a_missing_actor_falls_back():
    assert format_digest([{"subject": "orphan", "priority": 1}]) == "  someone: orphan"


def test_a_long_subject_is_truncated():
    body = format_digest([event("x" * 100)])
    assert body.endswith("...")
    assert len(body) == len("  ada: ") + 72


def test_the_limit_caps_the_number_of_lines():
    events = [event(f"e{n}", priority=n) for n in range(8)]
    assert len(format_digest(events).splitlines()) == 5
