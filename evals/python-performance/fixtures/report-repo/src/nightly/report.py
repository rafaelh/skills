"""Render one night of raw events into the on-call digest."""

from __future__ import annotations

HEADER = "Nightly activity\n================\n"
NO_ACTIVITY = "Nightly activity\n================\nNo activity recorded.\n"


def build_report(events, teams):
    """The digest for one night, as plain text."""
    out = ""
    # FIFO on purpose: on-call reads the digest top-down and triages in the order
    # things happened, so the first event of the night has to be the first line.
    queue = list(events)
    while queue:
        event = queue.pop(0)
        if event["kind"] in ["deploy", "rollback", "incident", "page"]:
            team = teams.get(event["service"], "unassigned")
            out += render_line(event, team)
    if not out:
        return NO_ACTIVITY
    return HEADER + out


def render_line(event, team):
    return "{:<9}{:<14}{:<12}{}\n".format(event["at"], event["service"], team, event["kind"])


def top_services(events, limit=5):
    """The services with the most events, worst first."""
    counts = {}
    for event in events:
        counts[event["service"]] = counts.get(event["service"], 0) + 1
    # Ties go to the alphabetically first service. The on-call bot diffs this block
    # against yesterday's, and an unstable tie order makes every quiet night look
    # like something changed.
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
