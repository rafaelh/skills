#!/usr/bin/env python3
"""Capture `az ... -h` from a real CLI into a shared help pack.

    capture_help.py fixtures/help/webapp-2.87.0.json --group webapp [--max-depth 3]

The help a run reads has to be authentic — `az-help.py` parses the CLI's own
column layout, and hand-written help would measure the fixture rather than the
skill — but it also has to be frozen, or a round run on a machine with a
different CLI version is a different experiment. So it is captured once from a
real `az`, stamped with the version it came from, and committed.

A pack is shared: tenants name it in their `help_packs` list rather than each
carrying a copy, because the same `az webapp` help answers a syntax question and
validates a flag named in an answer about a restart.

Re-run this only to move to a newer CLI, and record the version bump in
benchmark.md: it changes what every earlier round was measured against.

Developer harness, not something an agent calls — see README.md.
"""

# agent-tool: false

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

# "    config                  : Configure a web app."  — a subgroup or command
# entry in a group listing, at the fixed indent `az` renders them with.
LISTING_ENTRY = re.compile(r"^ {4}(\S+)(?: +\[\w+\])? +: ")


def az_help(path: list[str]) -> str | None:
    proc = subprocess.run(
        ["az", *path, "-h"], capture_output=True, text=True, timeout=60, check=False
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout


def sections(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line and not line.startswith(" "):
            current = line.strip()
            out.setdefault(current, [])
        elif current is not None:
            out[current].append(line)
    return out


def _capture(path: list[str]) -> tuple[list[str], str | None]:
    return path, az_help(path)


def walk(root: list[str], max_depth: int) -> dict[str, str]:
    """Every path beneath a group, breadth-first — the same shape `--tree` walks.

    Breadth-first with a bounded pool for the same reason `az-help.py` uses one:
    submitting child work from inside a running task deadlocks a pool once the
    tree is deeper than the worker count.
    """
    captured: dict[str, str] = {}
    level = [root]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for depth in range(max_depth + 1):
            if not level:
                break
            results: list[tuple[list[str], str | None]] = [
                (path, text) for path, text in pool.map(_capture, level)
            ]
            children: list[list[str]] = []
            for path, text in results:
                if text is None:
                    continue
                captured[" ".join(path)] = text
                parsed = sections(text)
                names = [
                    m.group(1)
                    for block in ("Subgroups:", "Commands:")
                    for line in parsed.get(block, [])
                    if (m := LISTING_ENTRY.match(line))
                ]
                if depth < max_depth:
                    children.extend([*path, name] for name in names)
            level = children
    return captured


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze real `az` help into a shared pack.")
    parser.add_argument("pack", type=Path, help="Help pack JSON to write.")
    parser.add_argument(
        "--group", action="append", required=True, help="Command group to walk (repeatable)."
    )
    parser.add_argument("--max-depth", type=int, default=3)
    args = parser.parse_args()

    version = subprocess.run(
        ["az", "version"], capture_output=True, text=True, timeout=60, check=False
    )
    if version.returncode != 0:
        print("error: no working `az` on PATH to capture from", file=sys.stderr)
        return 2
    cli_version = json.loads(version.stdout)["azure-cli"]

    help_block: dict[str, str] = {}
    for group in args.group:
        captured = walk(group.split(), args.max_depth)
        print(f"captured {len(captured)} path(s) under `az {group}`", file=sys.stderr)
        help_block.update(captured)

    pack: dict[str, Any] = {
        "captured_from": cli_version,
        "groups": args.group,
        "help": dict(sorted(help_block.items())),
    }
    args.pack.parent.mkdir(parents=True, exist_ok=True)
    args.pack.write_text(json.dumps(pack, indent=2) + "\n", encoding="utf-8")
    print(f"{args.pack}: {len(help_block)} help paths from azure-cli {cli_version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
