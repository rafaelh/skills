"""Render the notification digest sent to watchers."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

EMPTY = "No updates."
WIDTH = 72


def _initials(name):
    out = ""
    for part in name.split():
        out = out + part[0].upper()
    return out


def format_digest(events, limit=5):
    """The digest body for `events`, or the no-updates placeholder when there are none."""
    rows = []
    for e in events:
        # Muted events still count towards the unread badge, so they are dropped here
        # rather than upstream where the badge counts are taken.
        if not e.get("muted"):
            s = e.get("subject") or ""
            s = " ".join(s.split())
            if len(s) > WIDTH:
                s = s[: WIDTH - 3] + "..."
            p = e.get("priority")
            if p is None:
                p = 0
            rows.append({"p": p, "s": s, "who": e.get("actor") or "someone"})
            k = e.get("children")
            if k:
                for c in k:
                    if not c.get("muted"):
                        cs = c.get("subject") or ""
                        cs = " ".join(cs.split())
                        if len(cs) > WIDTH:
                            cs = cs[: WIDTH - 3] + "..."
                        cp = c.get("priority")
                        if cp is None:
                            cp = 0
                        rows.append(
                            {"p": cp, "s": "  " + cs, "who": c.get("actor") or "someone"}
                        )
    if not rows:
        logger.info("nothing to send for %s event(s)", len(events))
        return EMPTY
    rows.sort(key=lambda r: r["p"])
    rows.reverse()
    if limit:
        rows = rows[:limit]
    lines = []
    for r in rows:
        if r["p"] >= 2:
            lines.append("! " + r["who"] + ": " + r["s"])
        else:
            lines.append("  " + r["who"] + ": " + r["s"])
    return "\n".join(lines)
