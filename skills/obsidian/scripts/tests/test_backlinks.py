import json
from pathlib import Path
import subprocess
import sys

from backlinks import find_backlinks
import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "backlinks.py"


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / "notes").mkdir()
    (tmp_path / "archive").mkdir()
    return tmp_path


def write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestFindBacklinks:
    def test_one_inbound(self, vault: Path):
        write(vault / "notes" / "Alpha.md", "")
        write(vault / "notes" / "Linker.md", "see [[Alpha]]\n")
        backlinks = find_backlinks(vault / "notes" / "Alpha.md")
        assert len(backlinks) == 1
        assert backlinks[0].source.name == "Linker.md"

    def test_multiple_inbound_from_same_file(self, vault: Path):
        write(vault / "notes" / "Alpha.md", "")
        write(
            vault / "notes" / "Linker.md",
            "[[Alpha]] and again [[Alpha|disp]] and ![[Alpha]]\n",
        )
        backlinks = find_backlinks(vault / "notes" / "Alpha.md")
        assert len(backlinks) == 3
        assert {b.is_embed for b in backlinks} == {True, False}

    def test_no_inbound(self, vault: Path):
        write(vault / "notes" / "Alpha.md", "")
        write(vault / "notes" / "Other.md", "[[Different]]\n")
        assert find_backlinks(vault / "notes" / "Alpha.md") == []

    def test_skips_self_links(self, vault: Path):
        write(vault / "notes" / "Alpha.md", "I link to [[Alpha]] myself\n")
        assert find_backlinks(vault / "notes" / "Alpha.md") == []

    def test_path_form_link_matches(self, vault: Path):
        write(vault / "notes" / "Alpha.md", "")
        write(vault / "Other.md", "[[notes/Alpha]]\n")
        backlinks = find_backlinks(vault / "notes" / "Alpha.md")
        assert len(backlinks) == 1
        assert backlinks[0].source.name == "Other.md"

    def test_ignores_partial_name_match(self, vault: Path):
        write(vault / "notes" / "Alpha.md", "")
        write(vault / "notes" / "L.md", "[[AlphaBeta]] not [[Alpha]]\n")
        backlinks = find_backlinks(vault / "notes" / "Alpha.md")
        assert len(backlinks) == 1

    def test_ignores_links_in_code(self, vault: Path):
        write(vault / "notes" / "Alpha.md", "")
        write(
            vault / "notes" / "L.md",
            "real [[Alpha]]\n```\n[[Alpha]]\n```\n",
        )
        assert len(find_backlinks(vault / "notes" / "Alpha.md")) == 1

    def test_target_not_in_vault_raises(self, vault: Path, tmp_path: Path):
        outside = tmp_path.parent / "outside.md"
        outside.write_text("")
        try:
            with pytest.raises(Exception):  # noqa: B017
                find_backlinks(outside)
        finally:
            outside.unlink()

    def test_records_heading_and_block_metadata(self, vault: Path):
        write(vault / "notes" / "Alpha.md", "")
        write(
            vault / "notes" / "L.md",
            "[[Alpha#Section]] [[Alpha#^abc]]\n",
        )
        backlinks = find_backlinks(vault / "notes" / "Alpha.md")
        headings = [b.heading for b in backlinks]
        blocks = [b.block for b in backlinks]
        assert "Section" in headings
        assert "abc" in blocks

    def test_alias_link_counts_as_backlink(self, vault: Path):
        write(
            vault / "notes" / "Alpha.md",
            "---\naliases: [the-alpha]\n---\nbody\n",
        )
        write(vault / "notes" / "L.md", "see [[the-alpha]]\n")
        backlinks = find_backlinks(vault / "notes" / "Alpha.md")
        assert len(backlinks) == 1
        assert backlinks[0].target_form == "the-alpha"

    def test_case_insensitive_match(self, vault: Path):
        write(vault / "notes" / "Alpha.md", "")
        write(vault / "notes" / "L.md", "[[alpha]] [[ALPHA]] [[AlPhA]]\n")
        backlinks = find_backlinks(vault / "notes" / "Alpha.md")
        assert len(backlinks) == 3


class TestCli:
    def _run(self, *args: str):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_outputs_json(self, vault: Path):
        write(vault / "notes" / "Alpha.md", "")
        write(vault / "notes" / "L.md", "[[Alpha]]\n")
        result = self._run(str(vault / "notes" / "Alpha.md"))
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["source"].endswith("L.md")

    def test_exits_nonzero_when_target_missing(self, vault: Path):
        result = self._run(str(vault / "notes" / "missing.md"))
        assert result.returncode != 0
