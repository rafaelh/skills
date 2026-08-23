"""Behaviour `digest-repo`'s own suite leaves unpinned.

Never copied into the fixture: a run that can read these has been handed the answer,
and "preserve behaviour exactly" stops being the thing under test. `grade.py` drops
this file into a throwaway copy of the run's repo after the run has finished.

Each case is reachable from the repo without seeing this file — the sentinel from
`daily.py`, the placeholder from `format_digest`'s own docstring, the tie order and
the whitespace handling from reading the code before rewriting it.
"""

# agent-tool: false

from __future__ import annotations

from notify.digest import format_digest


def event(subject, priority=1, actor="ada", **extra):
    return {"subject": subject, "priority": priority, "actor": actor, **extra}


def test_a_tie_on_priority_keeps_the_order_the_fixture_produces():
    # sort-then-reverse, not sorted(reverse=True): equal priorities come out backwards.
    body = format_digest([event("first"), event("second")])
    assert body.splitlines() == ["  ada: second", "  ada: first"]


def test_limit_zero_means_no_limit():
    # daily.py depends on this sentinel; `rows[:0]` would render nothing.
    events = [event(f"e{n}") for n in range(9)]
    assert len(format_digest(events, limit=0).splitlines()) == 9


def test_no_events_render_the_placeholder():
    assert format_digest([]) == "No updates."


def test_events_that_are_all_muted_render_the_placeholder():
    assert format_digest([event("seen", muted=True)]) == "No updates."


def test_whitespace_inside_a_subject_is_collapsed():
    assert format_digest([event("build\n\tfailed  twice")]) == "  ada: build failed twice"


def test_whitespace_inside_a_child_subject_is_collapsed_too():
    parent = event("release", priority=3, children=[event("step\n one")])
    assert format_digest([parent]).splitlines()[-1] == "  ada:   step one"
