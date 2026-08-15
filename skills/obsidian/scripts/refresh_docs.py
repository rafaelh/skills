#!/usr/bin/env python3
"""Fetch Obsidian's help and developer docs into references/.cache/.

Use this when the baked references in references/*.md are missing detail
the agent needs about a recent or obscure feature. The cache is plain
text (HTML stripped) so the agent can grep it.

Library API:
    parse_sitemap(xml_text)  -> list[str]
    url_to_cache_path(url, base_dir) -> Path
    extract_text(html_bytes) -> str
    refresh(sitemap_url, cache_dir, filter=None) -> dict

CLI:
    refresh_docs.py [--site help|dev|all]
                    [--filter SUBSTRING]      only fetch URLs containing this
                    [--cache-dir PATH]        default: references/.cache/

Network access required. Run from outside any sandbox that blocks
obsidian.md / docs.obsidian.md.
"""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
from typing import Any
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

SITES = {
    "help": "https://obsidian.md/help/sitemap.xml",
    "dev": "https://docs.obsidian.md/sitemap.xml",
}
DEFAULT_CACHE = Path(__file__).resolve().parent.parent / "references" / ".cache"
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def parse_sitemap(xml_text: str) -> list[str]:
    root = ET.fromstring(xml_text)  # noqa: S314
    urls: list[str] = []
    for url in root.findall(f"{{{SITEMAP_NS}}}url"):
        loc = url.find(f"{{{SITEMAP_NS}}}loc")
        if loc is not None and loc.text:
            urls.append(loc.text.strip())
    return urls


def url_to_cache_path(url: str, base_dir: Path) -> Path:
    parsed = urllib.parse.urlparse(url)
    parts = [urllib.parse.unquote(seg) for seg in parsed.path.split("/") if seg]
    if not parts:
        return base_dir / parsed.netloc / "index.txt"
    *folders, last = parts
    return base_dir.joinpath(parsed.netloc, *folders, f"{last}.txt")


class _TextExtractor(HTMLParser):
    SKIP: frozenset[str] = frozenset(
        {"script", "style", "noscript", "svg", "nav", "header", "footer"}
    )
    BLOCK: frozenset[str] = frozenset(
        {
            "p",
            "div",
            "br",
            "li",
            "ul",
            "ol",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "tr",
            "td",
            "th",
            "section",
            "article",
        }
    )

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self.skip_depth += 1
        elif tag in self.BLOCK and self.skip_depth == 0:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP:
            self.skip_depth = max(0, self.skip_depth - 1)
        elif tag in self.BLOCK and self.skip_depth == 0:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth == 0:
            self.parts.append(data)

    @property
    def text(self) -> str:
        joined = "".join(self.parts)
        # Collapse runs of blank lines
        lines = [line.rstrip() for line in joined.splitlines()]
        out: list[str] = []
        blank = 0
        for line in lines:
            if not line:
                blank += 1
                if blank > 1:
                    continue
            else:
                blank = 0
            out.append(line)
        return "\n".join(out).strip() + "\n"


def extract_text(html_bytes: bytes) -> str:
    parser = _TextExtractor()
    parser.feed(html_bytes.decode("utf-8", errors="replace"))
    return parser.text


def _http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "obsidian-skill"})  # noqa: S310
    with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310
        return response.read()


def refresh(
    sitemap_url: str,
    cache_dir: Path,
    filter: str | None = None,
    *,
    fetcher: Any = _http_get,
) -> dict[str, Any]:
    sitemap_xml: str = fetcher(sitemap_url).decode("utf-8")
    urls = parse_sitemap(sitemap_xml)
    if filter:
        urls = [u for u in urls if filter in u]

    summary: dict[str, Any] = {"sitemap": sitemap_url, "fetched": [], "skipped": [], "errors": []}
    for url in urls:
        out = url_to_cache_path(url, cache_dir)
        try:
            html = fetcher(url)
        except Exception as exc:
            summary["errors"].append({"url": url, "error": str(exc)})
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        text = extract_text(html)
        if out.exists() and out.read_text(encoding="utf-8") == text:
            summary["skipped"].append(url)
            continue
        out.write_text(text, encoding="utf-8")
        summary["fetched"].append(url)
    return summary


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--site", choices=("help", "dev", "all"), default="all")
    parser.add_argument("--filter", help="only fetch URLs containing this substring")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="emit JSON summary on stdout instead of progress lines",
    )
    args = parser.parse_args(argv)

    sites = [args.site] if args.site != "all" else list(SITES)
    overall: dict[str, Any] = {"cache_dir": str(args.cache_dir), "by_site": {}}
    exit_code = 0
    for site in sites:
        sitemap_url = SITES[site]
        try:
            summary = refresh(sitemap_url, args.cache_dir, filter=args.filter)
        except Exception as exc:
            msg = f"refresh_docs: {site} sitemap fetch failed: {exc}"
            if args.as_json:
                overall["by_site"][site] = {"error": str(exc)}
                exit_code = 1
                continue
            print(msg, file=sys.stderr)
            return 1
        overall["by_site"][site] = {
            "fetched": len(summary["fetched"]),
            "skipped": len(summary["skipped"]),
            "errors": len(summary["errors"]),
            "error_details": summary["errors"][:20],
        }
        if not args.as_json:
            print(
                f"{site}: fetched={len(summary['fetched'])} "
                f"skipped={len(summary['skipped'])} errors={len(summary['errors'])}"
            )
            for err in summary["errors"][:5]:
                print(f"  ERROR {err['url']}: {err['error']}", file=sys.stderr)

    if args.as_json:
        print(json.dumps(overall, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
