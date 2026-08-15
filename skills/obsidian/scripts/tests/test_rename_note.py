from pathlib import Path
import subprocess
import sys

import pytest
from rename_note import RenameError, rename_note

SCRIPT = Path(__file__).resolve().parent.parent / "rename_note.py"


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Build a minimal vault inside tmp_path and return its root."""
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / ".obsidian" / "app.json").write_text("{}")
    (tmp_path / "notes").mkdir()
    (tmp_path / "archive").mkdir()
    return tmp_path


def write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestRenameSameFolder:
    def test_moves_file(self, vault: Path):
        old = write(vault / "notes" / "Alpha.md", "# Alpha\n")
        result = rename_note(old, vault / "notes" / "Beta.md")
        assert not old.exists()
        assert (vault / "notes" / "Beta.md").exists()
        assert result.moved is True

    def test_rewrites_bare_inbound_wikilink(self, vault: Path):
        write(vault / "notes" / "Alpha.md", "# Alpha\n")
        linker = write(vault / "notes" / "Linker.md", "see [[Alpha]] for details\n")
        rename_note(vault / "notes" / "Alpha.md", vault / "notes" / "Beta.md")
        assert linker.read_text() == "see [[Beta]] for details\n"

    def test_preserves_alias_heading_block_on_rewrite(self, vault: Path):
        write(vault / "notes" / "Alpha.md", "# Alpha\n")
        linker = write(
            vault / "notes" / "L.md",
            "[[Alpha|disp]] [[Alpha#Sec]] [[Alpha#^abc]] ![[Alpha]]\n",
        )
        rename_note(vault / "notes" / "Alpha.md", vault / "notes" / "Beta.md")
        assert linker.read_text() == "[[Beta|disp]] [[Beta#Sec]] [[Beta#^abc]] ![[Beta]]\n"

    def test_does_not_touch_unrelated_links(self, vault: Path):
        write(vault / "notes" / "Alpha.md", "")
        linker = write(vault / "notes" / "L.md", "[[Other]] and [[Alpha]] and [[AlphaX]]\n")
        rename_note(vault / "notes" / "Alpha.md", vault / "notes" / "Beta.md")
        assert linker.read_text() == "[[Other]] and [[Beta]] and [[AlphaX]]\n"

    def test_case_insensitive_rewrite(self, vault: Path):
        write(vault / "notes" / "Alpha.md", "")
        linker = write(
            vault / "notes" / "L.md",
            "[[alpha]] [[ALPHA]] [[AlPhA]]\n",
        )
        rename_note(vault / "notes" / "Alpha.md", vault / "notes" / "Beta.md")
        assert linker.read_text() == "[[Beta]] [[Beta]] [[Beta]]\n"

    def test_does_not_touch_links_in_code(self, vault: Path):
        write(vault / "notes" / "Alpha.md", "")
        linker = write(
            vault / "notes" / "L.md",
            "real [[Alpha]]\n```\n[[Alpha]] not real\n```\n",
        )
        rename_note(vault / "notes" / "Alpha.md", vault / "notes" / "Beta.md")
        text = linker.read_text()
        assert "real [[Beta]]" in text
        assert "```\n[[Alpha]] not real\n```" in text


class TestRenameAcrossFolders:
    def test_moves_file_across_folders(self, vault: Path):
        old = write(vault / "notes" / "Alpha.md", "")
        rename_note(old, vault / "archive" / "Alpha.md")
        assert (vault / "archive" / "Alpha.md").exists()
        assert not old.exists()

    def test_path_form_link_is_rewritten(self, vault: Path):
        write(vault / "notes" / "Alpha.md", "")
        linker = write(
            vault / "other.md",
            "[[notes/Alpha]] and [[Alpha]]\n",
        )
        rename_note(vault / "notes" / "Alpha.md", vault / "archive" / "Alpha.md")
        text = linker.read_text()
        assert "[[archive/Alpha]]" in text
        # Bare name still resolves; v1 leaves it alone when name unchanged.
        assert "[[Alpha]]" in text


class TestErrors:
    def test_target_exists_raises(self, vault: Path):
        write(vault / "notes" / "Alpha.md", "")
        write(vault / "notes" / "Beta.md", "existing")
        with pytest.raises(RenameError):
            rename_note(vault / "notes" / "Alpha.md", vault / "notes" / "Beta.md")

    def test_source_missing_raises(self, vault: Path):
        with pytest.raises(RenameError):
            rename_note(vault / "notes" / "missing.md", vault / "notes" / "Beta.md")

    def test_source_outside_vault_raises(self, vault: Path, tmp_path: Path):
        outside = tmp_path.parent
        with pytest.raises(RenameError):
            rename_note(outside / "stray.md", vault / "notes" / "Beta.md")

    def test_paths_in_different_vaults_raises(self, vault: Path, tmp_path: Path):
        other_vault = tmp_path.parent / "other-vault"
        (other_vault / ".obsidian").mkdir(parents=True)
        write(other_vault / "x.md", "")
        try:
            with pytest.raises(RenameError):
                rename_note(vault / "notes" / "Alpha.md", other_vault / "Alpha.md")
        finally:
            import shutil

            shutil.rmtree(other_vault)


class TestDryRun:
    def test_dry_run_does_not_move(self, vault: Path):
        old = write(vault / "notes" / "Alpha.md", "")
        result = rename_note(old, vault / "notes" / "Beta.md", dry_run=True)
        assert old.exists()
        assert not (vault / "notes" / "Beta.md").exists()
        assert result.moved is False

    def test_dry_run_does_not_rewrite_links(self, vault: Path):
        write(vault / "notes" / "Alpha.md", "")
        linker = write(vault / "notes" / "L.md", "[[Alpha]]\n")
        rename_note(
            vault / "notes" / "Alpha.md",
            vault / "notes" / "Beta.md",
            dry_run=True,
        )
        assert linker.read_text() == "[[Alpha]]\n"

    def test_dry_run_reports_planned_updates(self, vault: Path):
        write(vault / "notes" / "Alpha.md", "")
        write(vault / "notes" / "L.md", "[[Alpha]]\n")
        result = rename_note(
            vault / "notes" / "Alpha.md",
            vault / "notes" / "Beta.md",
            dry_run=True,
        )
        assert any(p.name == "L.md" for p in result.updated_files)


class TestCli:
    def _run(self, *args: str):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_renames_via_cli(self, vault: Path):
        old = write(vault / "notes" / "Alpha.md", "# Alpha")
        write(vault / "notes" / "L.md", "[[Alpha]]\n")
        result = self._run(str(old), str(vault / "notes" / "Beta.md"))
        assert result.returncode == 0, result.stderr
        assert (vault / "notes" / "Beta.md").exists()
        assert (vault / "notes" / "L.md").read_text() == "[[Beta]]\n"

    def test_dry_run_flag(self, vault: Path):
        old = write(vault / "notes" / "Alpha.md", "")
        write(vault / "notes" / "L.md", "[[Alpha]]\n")
        result = self._run(str(old), str(vault / "notes" / "Beta.md"), "--dry-run")
        assert result.returncode == 0
        assert old.exists()
        assert (vault / "notes" / "L.md").read_text() == "[[Alpha]]\n"
