#!/usr/bin/env python3
"""Parse and rewrite Obsidian wikilinks, embeds, and tags in markdown text.

Library API:
    parse_links(text)  -> list[Wikilink]
    parse_tags(text)   -> list[Tag]
    rewrite_link_target(text, old, new) -> str

CLI:
    links.py extract NOTE          # JSON with wikilinks + tags
    links.py rewrite NOTE OLD NEW  # in-place rename of all [[OLD]] -> [[NEW]]

Wikilink forms recognized:
    [[Target]]               [[Target|display]]
    [[Target#Heading]]       [[Target#Heading|display]]
    [[Target#^block]]        [[Target#^block|display]]
    [[Folder/Target]]        [[#HeadingInThisNote]]
    ![[Target]]              (embed prefix)

Tag rules:
    - #word with [A-Za-z0-9_/-] characters
    - Must be preceded by start-of-line or whitespace
    - Must contain at least one non-digit character

Code-region awareness:
    Wikilinks and tags inside fenced code blocks (``` or ~~~), indented code
    blocks (4+ spaces / tab after a blank line), and inline backtick spans
    are ignored. Math blocks ($$ ... $$) and Obsidian comments (%% %%) are
    NOT yet skipped — open an issue if you hit one in the wild.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import re
import sys

from models import Tag, Wikilink

_WIKILINK_RE = re.compile(r"(!?)\[\[([^\[\]\n]+)\]\]")
_TAG_RE = re.compile(
    r"(?:(?<=^)|(?<=\s))(#[A-Za-z0-9_][A-Za-z0-9_/\-]*)",
    re.MULTILINE,
)


def _build_code_mask(text: str) -> list[bool]:
    """Return list[bool] of len(text); True where the position is in code."""
    n = len(text)
    mask = [False] * n

    # Fenced code: ```...``` or ~~~...~~~
    fence_re = re.compile(
        r"(?:^|\n)( {0,3})(`{3,}|~{3,})[^\n]*\n.*?(?:\n {0,3}\2[ \t]*(?=\n|$)|\Z)",
        re.DOTALL,
    )
    for m in fence_re.finditer(text):
        # Skip the leading \n we may have matched
        s = m.start()
        if s < n and text[s] == "\n":
            s += 1
        for i in range(s, m.end()):
            mask[i] = True

    # Indented code blocks (4+ spaces or tab, after blank line or already in block)
    lines = text.split("\n")
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line) + 1)
    prev_blank = True
    in_block = False
    for idx, line in enumerate(lines):
        start = offsets[idx]
        if start >= n:
            break
        if line.strip() == "":
            in_block = False
            prev_blank = True
            continue
        is_indent = line.startswith(("    ", "\t"))
        if is_indent and (prev_blank or in_block) and not mask[start]:
            for i in range(start, min(start + len(line), n)):
                mask[i] = True
            in_block = True
        else:
            in_block = False
        prev_blank = False

    # Inline backtick code: matched runs `+...`+ of equal length
    i = 0
    while i < n:
        if text[i] != "`" or mask[i]:
            i += 1
            continue
        run = 0
        while i + run < n and text[i + run] == "`":
            run += 1
        # Search for matching closing run of the same length
        j = i + run
        close_at = -1
        while j < n:
            if text[j] != "`":
                j += 1
                continue
            close_run = 0
            while j + close_run < n and text[j + close_run] == "`":
                close_run += 1
            if close_run == run:
                close_at = j
                break
            j += close_run
        if close_at >= 0:
            for k in range(i, close_at + run):
                mask[k] = True
            i = close_at + run
        else:
            i += run

    return mask


def _in_code(mask: list[bool], start: int, end: int) -> bool:
    return any(mask[start:end])


def _parse_wikilink_body(body: str) -> tuple[str, str | None, str | None, str | None]:
    """Return (target, heading, block, display) from the inside of [[...]]."""
    display = None
    if "|" in body:
        body, display = body.split("|", 1)
        display = display.strip()
    body = body.strip()

    heading = None
    block = None
    if "#" in body:
        target, _, rest = body.partition("#")
        if rest.startswith("^"):
            block = rest[1:]
        else:
            heading = rest
    else:
        target = body

    return target, heading, block, display


def parse_links(text: str) -> list[Wikilink]:
    mask = _build_code_mask(text)
    out: list[Wikilink] = []
    for m in _WIKILINK_RE.finditer(text):
        if _in_code(mask, m.start(), m.end()):
            continue
        body = m.group(2).strip()
        if not body:
            continue
        target, heading, block, display = _parse_wikilink_body(body)
        out.append(
            Wikilink(
                target=target,
                heading=heading,
                block=block,
                display=display,
                is_embed=m.group(1) == "!",
                raw=m.group(0),
                span=(m.start(), m.end()),
            )
        )
    return out


def parse_tags(text: str) -> list[Tag]:
    mask = _build_code_mask(text)
    out: list[Tag] = []
    for m in _TAG_RE.finditer(text):
        if _in_code(mask, m.start(1), m.end(1)):
            continue
        name = m.group(1)[1:]
        if name.replace("/", "").replace("-", "").replace("_", "").isdigit():
            continue
        out.append(
            Tag(
                name=name,
                raw=m.group(1),
                span=(m.start(1), m.end(1)),
            )
        )
    return out


def rewrite_link_target(text: str, old: str, new: str) -> str:
    """Rewrite every wikilink whose target matches `old` to `new`.

    Matching is case-insensitive (Obsidian's resolver is also case-insensitive).
    The replacement uses `new` as written, so the canonical case is whatever
    the caller provided. Heading, block, alias, and embed prefix are preserved.
    """
    links = parse_links(text)
    if not links:
        return text
    old_lower = old.lower()
    pieces: list[str] = []
    cursor = 0
    for link in links:
        if link.target.lower() != old_lower:
            continue
        pieces.append(text[cursor : link.span[0]])
        prefix = "!" if link.is_embed else ""
        body = new
        if link.heading is not None:
            body += "#" + link.heading
        elif link.block is not None:
            body += "#^" + link.block
        if link.display is not None:
            body += "|" + link.display
        pieces.append(f"{prefix}[[{body}]]")
        cursor = link.span[1]
    pieces.append(text[cursor:])
    return "".join(pieces)


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_extract = sub.add_parser("extract", help="emit wikilinks + tags as JSON")
    p_extract.add_argument("note")

    p_rewrite = sub.add_parser("rewrite", help="rewrite [[OLD]] to [[NEW]] in place")
    p_rewrite.add_argument("note")
    p_rewrite.add_argument("old")
    p_rewrite.add_argument("new")

    args = parser.parse_args(argv)
    path = Path(args.note)
    text = path.read_text(encoding="utf-8")

    if args.cmd == "extract":
        result = {
            "wikilinks": [asdict(w) for w in parse_links(text)],
            "tags": [asdict(t) for t in parse_tags(text)],
        }
        print(json.dumps(result, indent=2))
        return 0
    if args.cmd == "rewrite":
        new_text = rewrite_link_target(text, args.old, args.new)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
