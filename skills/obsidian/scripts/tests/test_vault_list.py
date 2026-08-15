import json
from pathlib import Path
import subprocess
import sys

import pytest
from vault_list import list_notes, list_plugins

SCRIPT = Path(__file__).resolve().parent.parent / "vault_list.py"


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


class TestListNotes:
    def test_lists_all_markdown(self, vault: Path):
        write(vault / "notes" / "a.md", "")
        write(vault / "notes" / "b.md", "")
        write(vault / "archive" / "c.md", "")
        names = sorted(p.name for p in list_notes(vault))
        assert names == ["a.md", "b.md", "c.md"]

    def test_skips_obsidian_dir(self, vault: Path):
        write(vault / ".obsidian" / "junk.md", "")
        write(vault / "real.md", "")
        assert [p.name for p in list_notes(vault)] == ["real.md"]

    def test_skips_trash_dir(self, vault: Path):
        (vault / ".trash").mkdir()
        write(vault / ".trash" / "deleted.md", "")
        write(vault / "real.md", "")
        assert [p.name for p in list_notes(vault)] == ["real.md"]

    def test_filter_by_folder(self, vault: Path):
        write(vault / "notes" / "a.md", "")
        write(vault / "archive" / "b.md", "")
        result = [p.name for p in list_notes(vault, folder="notes")]
        assert result == ["a.md"]

    def test_filter_by_frontmatter_tag(self, vault: Path):
        write(vault / "a.md", "---\ntags: [work, urgent]\n---\nbody\n")
        write(vault / "b.md", "---\ntags: [home]\n---\nbody\n")
        write(vault / "c.md", "no fm\n")
        result = sorted(p.name for p in list_notes(vault, tag="work"))
        assert result == ["a.md"]

    def test_filter_by_inline_tag(self, vault: Path):
        write(vault / "a.md", "body has #work tag\n")
        write(vault / "b.md", "body has nothing\n")
        result = [p.name for p in list_notes(vault, tag="work")]
        assert result == ["a.md"]

    def test_inline_and_frontmatter_tag_both_match(self, vault: Path):
        write(vault / "a.md", "---\ntags: [work]\n---\nbody\n")
        write(vault / "b.md", "body #work\n")
        result = sorted(p.name for p in list_notes(vault, tag="work"))
        assert result == ["a.md", "b.md"]

    def test_filter_by_has_property(self, vault: Path):
        write(vault / "a.md", "---\nstatus: draft\n---\n")
        write(vault / "b.md", "---\ntitle: T\n---\n")
        result = sorted(p.name for p in list_notes(vault, has_property="status"))
        assert result == ["a.md"]

    def test_filter_by_property_value(self, vault: Path):
        write(vault / "a.md", "---\nstatus: draft\n---\n")
        write(vault / "b.md", "---\nstatus: published\n---\n")
        result = sorted(
            p.name for p in list_notes(vault, has_property="status", property_value="draft")
        )
        assert result == ["a.md"]

    def test_combined_filters(self, vault: Path):
        write(vault / "notes" / "a.md", "---\ntags: [work]\nstatus: draft\n---\n")
        write(vault / "notes" / "b.md", "---\ntags: [work]\n---\n")
        write(vault / "archive" / "c.md", "---\ntags: [work]\nstatus: draft\n---\n")
        result = sorted(
            p.name for p in list_notes(vault, folder="notes", tag="work", has_property="status")
        )
        assert result == ["a.md"]


class TestListPlugins:
    def test_no_plugins_returns_empty(self, vault: Path):
        info = list_plugins(vault)
        assert info["enabled_community"] == []
        assert info["installed_community"] == []

    def test_reports_installed_plugin_dirs(self, vault: Path):
        plugin_dir = vault / ".obsidian" / "plugins" / "dataview"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "manifest.json").write_text(
            json.dumps({"id": "dataview", "name": "Dataview", "version": "0.5.0"})
        )
        info = list_plugins(vault)
        assert "dataview" in info["installed_community"]

    def test_reports_enabled_from_community_plugins_json(self, vault: Path):
        (vault / ".obsidian" / "community-plugins.json").write_text(
            json.dumps(["dataview", "templater-obsidian"])
        )
        info = list_plugins(vault)
        assert info["enabled_community"] == ["dataview", "templater-obsidian"]

    def test_handles_missing_or_malformed_files_gracefully(self, vault: Path):
        (vault / ".obsidian" / "community-plugins.json").write_text("not json")
        info = list_plugins(vault)
        assert info["enabled_community"] == []


class TestCli:
    def _run(self, *args: str):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_lists_paths_one_per_line(self, vault: Path):
        write(vault / "a.md", "")
        write(vault / "b.md", "")
        result = self._run("--vault", str(vault))
        assert result.returncode == 0
        names = sorted(Path(line).name for line in result.stdout.strip().splitlines())
        assert names == ["a.md", "b.md"]

    def test_json_output(self, vault: Path):
        write(vault / "a.md", "")
        result = self._run("--vault", str(vault), "--json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert any(item.endswith("a.md") for item in data)

    def test_plugins_flag_outputs_json(self, vault: Path):
        result = self._run("--vault", str(vault), "--plugins")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "enabled_community" in data
        assert "installed_community" in data
