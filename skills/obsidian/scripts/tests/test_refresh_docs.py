from pathlib import Path
import subprocess
import sys

from refresh_docs import extract_text, parse_sitemap, refresh, url_to_cache_path

SCRIPT = Path(__file__).resolve().parent.parent / "refresh_docs.py"

SAMPLE_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://obsidian.md/help/syntax</loc></url>
  <url><loc>https://obsidian.md/help/Plugins/Tasks</loc></url>
  <url>
    <loc>https://docs.obsidian.md/Reference/Vault</loc>
  </url>
</urlset>
"""


class TestParseSitemap:
    def test_extracts_locs(self):
        urls = parse_sitemap(SAMPLE_SITEMAP)
        assert urls == [
            "https://obsidian.md/help/syntax",
            "https://obsidian.md/help/Plugins/Tasks",
            "https://docs.obsidian.md/Reference/Vault",
        ]

    def test_handles_empty_sitemap(self):
        empty = '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>'
        assert parse_sitemap(empty) == []


class TestUrlToCachePath:
    def test_simple_help_url(self, tmp_path: Path):
        p = url_to_cache_path("https://obsidian.md/help/syntax", tmp_path)
        assert p == tmp_path / "obsidian.md" / "help" / "syntax.txt"

    def test_nested_dev_url(self, tmp_path: Path):
        p = url_to_cache_path("https://docs.obsidian.md/Reference/Vault", tmp_path)
        assert p == tmp_path / "docs.obsidian.md" / "Reference" / "Vault.txt"

    def test_root_url(self, tmp_path: Path):
        p = url_to_cache_path("https://docs.obsidian.md/", tmp_path)
        assert p == tmp_path / "docs.obsidian.md" / "index.txt"


class TestExtractText:
    def test_strips_tags(self):
        html = b"<html><body><h1>Title</h1><p>Hello world</p></body></html>"
        text = extract_text(html)
        assert "Title" in text
        assert "Hello world" in text
        assert "<" not in text

    def test_skips_script_and_style(self):
        html = (
            b"<html><head><script>var x = 1;</script>"
            b"<style>p{color:red}</style></head>"
            b"<body><p>Hello</p></body></html>"
        )
        text = extract_text(html)
        assert "Hello" in text
        assert "var x" not in text
        assert "color:red" not in text

    def test_handles_entities(self):
        html = b"<p>R&amp;D &lt; 5</p>"
        text = extract_text(html)
        assert "R&D" in text
        assert "< 5" in text


class TestRefreshOffline:
    def test_refresh_with_injected_fetcher(self, tmp_path: Path):
        sample_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://obsidian.md/help/syntax</loc></url>
</urlset>
"""

        def fake_fetcher(url: str, timeout: int = 30) -> bytes:
            if url.endswith("sitemap.xml"):
                return sample_xml
            return b"<html><body><h1>Hi</h1></body></html>"

        result = refresh(
            "https://obsidian.md/help/sitemap.xml",
            tmp_path,
            fetcher=fake_fetcher,
        )
        assert len(result["fetched"]) == 1
        assert (tmp_path / "obsidian.md" / "help" / "syntax.txt").exists()


class TestCli:
    def _run(self, *args: str):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_help_works(self):
        result = self._run("--help")
        assert result.returncode == 0
        assert "--json" in result.stdout
