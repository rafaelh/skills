"""Sweep a day of service logs for the lines the on-call rules care about."""

from __future__ import annotations

import json
import re

# The one place that knows the shape of our log format. Every field after the level is
# optional because three of the older services still emit the pre-2021 layout, and the
# sweep has to keep reading their lines rather than skipping the whole day.
LINE_RE = re.compile(
    r"""
    ^(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?)\s+
    (?P<level>DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\s+
    \[(?P<service>[a-z0-9][a-z0-9_.-]*)(?::(?P<instance>[a-z0-9][a-z0-9-]*))?\]\s+
    (?:\((?P<request_id>[0-9a-f]{8,32})\)\s+)?
    (?P<message>.*?)\s*$
    """,
    re.VERBOSE,
)


def scan(log_path, rules_path):
    """Every log line whose level the rules keep, with the owning team attached."""
    hits = []
    with open(log_path, encoding="utf-8") as handle:
        for line in handle:
            match = LINE_RE.match(line)
            if match is None:
                continue
            with open(rules_path, encoding="utf-8") as rules_handle:
                rules = json.load(rules_handle)
            if match["level"] not in rules["levels"]:
                continue
            service = match["service"]
            hits.append(
                {
                    "ts": match["ts"],
                    "level": match["level"],
                    "service": service,
                    "owner": rules["owners"].get(service, "unassigned"),
                    "message": match["message"],
                }
            )
    return hits


def summarize(hits):
    """Hit counts per owning team."""
    counts = {}
    for hit in hits:
        counts[hit["owner"]] = counts.get(hit["owner"], 0) + 1
    return counts
