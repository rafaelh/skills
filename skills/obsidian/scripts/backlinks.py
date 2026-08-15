#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyyaml>=6.0",
# ]
# ///
"""Find every note in a vault that wikilinks to a target note.

Library API:
    find_backlinks(target_path) -> list[Backlink]

CLI:
    backlinks.py NOTE          # JSON list of inbound links

A wikilink counts as a backlink to NOTE if its target resolves to NOTE:
NOTE's basename, its vault-relative path (both without .md), or any of
its frontmatter aliases, matched case-insensitively (see resolver.py).
Links inside code are skipped (handled by links.py). Self-references
inside NOTE itself are excluded.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys

from links import parse_links
from resolver import Resolver
from vault import NotInVaultError, iter_notes, locate_vault


@dataclass
class Backlink:
    source: Path
    target_form: str  # the literal target in the wikilink
    is_embed: bool
    heading: str | None
    block: str | None
    display: str | None
    span: tuple[int, int]


def find_backlinks(target_path: str | Path) -> list[Backlink]:
    target = Path(target_path).expanduser()
    if not target.exists():
        raise FileNotFoundError(f"target does not exist: {target}")

    vault = locate_vault(target)
    resolver = Resolver(vault)

    out: list[Backlink] = []
    for md in iter_notes(vault):
        if md.resolve() == target.resolve():
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        out.extend(
            Backlink(
                source=md,
                target_form=link.target,
                is_embed=link.is_embed,
                heading=link.heading,
                block=link.block,
                display=link.display,
                span=link.span,
            )
            for link in parse_links(text)
            if resolver.matches(link.target, target)
        )
    return out


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("note")
    args = parser.parse_args(argv)

    try:
        backlinks = find_backlinks(args.note)
    except (FileNotFoundError, NotInVaultError) as exc:
        print(f"backlinks: {exc}", file=sys.stderr)
        return 1

    payload = [
        {
            "source": str(b.source),
            "target_form": b.target_form,
            "is_embed": b.is_embed,
            "heading": b.heading,
            "block": b.block,
            "display": b.display,
            "span": list(b.span),
        }
        for b in backlinks
    ]
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
