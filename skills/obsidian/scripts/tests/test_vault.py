from pathlib import Path
import subprocess
import sys

import pytest
from vault import (
    SKIP_DIRS,
    NotInVaultError,
    iter_bases,
    iter_canvas,
    iter_notes,
    locate_vault,
    relpath_no_ext,
)

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
VAULT = FIXTURES / "test_vault"
SCRIPT = SCRIPTS_DIR / "vault.py"


@pytest.fixture
def fresh_vault(tmp_path: Path) -> Path:
    (tmp_path / ".obsidian").mkdir()
    return tmp_path


@pytest.fixture
def not_a_vault(tmp_path: Path) -> Path:
    """A directory with no `.obsidian/` ancestor.

    Built under tmp_path rather than checked in: a fixture stored inside
    this repo is only "not a vault" when the repo itself is not inside
    one, which is false whenever the skill is installed into a vault.
    """
    d = tmp_path / "not_a_vault"
    d.mkdir()
    (d / "somefile.md").write_text("# Not a vault\n")
    return d


def write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


class TestLocateVault:
    """Behaviors carried over from the old vault_locate module."""

    def test_returns_root_from_vault_root(self):
        assert locate_vault(VAULT) == VAULT.resolve()

    def test_returns_root_from_nested_dir(self):
        assert locate_vault(VAULT / "notes" / "nested") == VAULT.resolve()

    def test_raises_when_no_dot_obsidian_ancestor(self, not_a_vault: Path):
        with pytest.raises(NotInVaultError):
            locate_vault(not_a_vault)

    def test_raises_when_path_does_not_exist(self, tmp_path: Path):
        with pytest.raises(NotInVaultError):
            locate_vault(tmp_path / "does-not-exist")

    def test_resolves_symlinks(self, tmp_path: Path):
        link = tmp_path / "vault-link"
        try:
            link.symlink_to(VAULT)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"symlinks unavailable on this platform: {exc}")
        assert locate_vault(link / "notes") == VAULT.resolve()

    def test_accepts_string_path(self):
        assert locate_vault(str(VAULT / "notes")) == VAULT.resolve()


class TestIterNotes:
    def test_empty_vault_yields_nothing(self, fresh_vault: Path):
        assert list(iter_notes(fresh_vault)) == []

    def test_yields_top_level_md_files(self, fresh_vault: Path):
        write(fresh_vault / "a.md")
        write(fresh_vault / "b.md")
        names = sorted(p.name for p in iter_notes(fresh_vault))
        assert names == ["a.md", "b.md"]

    def test_yields_nested_md_files(self, fresh_vault: Path):
        write(fresh_vault / "notes" / "nested" / "deep.md")
        notes = list(iter_notes(fresh_vault))
        assert len(notes) == 1
        assert notes[0].name == "deep.md"

    def test_skips_obsidian_dir(self, fresh_vault: Path):
        write(fresh_vault / ".obsidian" / "config.md")
        write(fresh_vault / "real.md")
        names = [p.name for p in iter_notes(fresh_vault)]
        assert names == ["real.md"]

    def test_skips_trash_dir(self, fresh_vault: Path):
        (fresh_vault / ".trash").mkdir()
        write(fresh_vault / ".trash" / "deleted.md")
        write(fresh_vault / "real.md")
        names = [p.name for p in iter_notes(fresh_vault)]
        assert names == ["real.md"]

    def test_skips_git_dir(self, fresh_vault: Path):
        write(fresh_vault / ".git" / "HEAD")
        write(fresh_vault / ".git" / "config.md")
        write(fresh_vault / "real.md")
        names = [p.name for p in iter_notes(fresh_vault)]
        assert names == ["real.md"]

    def test_does_not_yield_canvas_or_base(self, fresh_vault: Path):
        write(fresh_vault / "drawing.canvas", "{}")
        write(fresh_vault / "data.base", "")
        write(fresh_vault / "real.md")
        names = [p.name for p in iter_notes(fresh_vault)]
        assert names == ["real.md"]


class TestIterCanvas:
    def test_yields_canvas_files(self, fresh_vault: Path):
        write(fresh_vault / "a.canvas", "{}")
        write(fresh_vault / "deep" / "b.canvas", "{}")
        write(fresh_vault / "not.md")
        names = sorted(p.name for p in iter_canvas(fresh_vault))
        assert names == ["a.canvas", "b.canvas"]

    def test_skips_obsidian_dir(self, fresh_vault: Path):
        write(fresh_vault / ".obsidian" / "x.canvas", "{}")
        write(fresh_vault / "real.canvas", "{}")
        names = [p.name for p in iter_canvas(fresh_vault)]
        assert names == ["real.canvas"]


class TestIterBases:
    def test_yields_base_files(self, fresh_vault: Path):
        write(fresh_vault / "a.base")
        write(fresh_vault / "deep" / "b.base")
        names = sorted(p.name for p in iter_bases(fresh_vault))
        assert names == ["a.base", "b.base"]

    def test_skips_obsidian_dir(self, fresh_vault: Path):
        write(fresh_vault / ".obsidian" / "x.base")
        write(fresh_vault / "real.base")
        names = [p.name for p in iter_bases(fresh_vault)]
        assert names == ["real.base"]


class TestRelpathNoExt:
    def test_simple_top_level(self, fresh_vault: Path):
        note = write(fresh_vault / "Alpha.md")
        assert relpath_no_ext(fresh_vault, note) == "Alpha"

    def test_nested(self, fresh_vault: Path):
        note = write(fresh_vault / "notes" / "deep" / "Alpha.md")
        assert relpath_no_ext(fresh_vault, note) == "notes/deep/Alpha"

    def test_resolves_symlinks_in_both(self, tmp_path: Path):
        real = tmp_path / "real-vault"
        (real / ".obsidian").mkdir(parents=True)
        write(real / "notes" / "Alpha.md")
        link = tmp_path / "link"
        try:
            link.symlink_to(real)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"symlinks unavailable on this platform: {exc}")
        assert relpath_no_ext(link, link / "notes" / "Alpha.md") == "notes/Alpha"

    def test_strips_canvas_extension(self, fresh_vault: Path):
        f = write(fresh_vault / "board.canvas", "{}")
        assert relpath_no_ext(fresh_vault, f) == "board"


class TestSkipDirsConstant:
    def test_includes_obsidian_trash_git(self):
        assert ".obsidian" in SKIP_DIRS
        assert ".trash" in SKIP_DIRS
        assert ".git" in SKIP_DIRS


class TestVaultLocateCli:
    """Existing CLI behavior must continue to work via the same script name."""

    def _run(self, *args: str, cwd: str | Path | None = None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=cwd,
            check=False,
        )

    def test_prints_root_for_explicit_path(self):
        result = self._run(str(VAULT / "notes"))
        assert result.returncode == 0
        assert result.stdout.strip() == str(VAULT.resolve())

    def test_uses_cwd_when_no_arg(self):
        result = self._run(cwd=VAULT / "notes")
        assert result.returncode == 0
        assert result.stdout.strip() == str(VAULT.resolve())

    def test_exits_nonzero_when_not_in_vault(self, not_a_vault: Path):
        result = self._run(str(not_a_vault))
        assert result.returncode != 0

    def test_json_output_success(self):
        import json as _json

        result = self._run(str(VAULT / "notes"), "--json")
        assert result.returncode == 0
        data = _json.loads(result.stdout)
        assert data["vault_root"] == str(VAULT.resolve())
        assert data["input"] == str(VAULT / "notes")

    def test_json_output_failure(self, not_a_vault: Path):
        import json as _json

        result = self._run(str(not_a_vault), "--json")
        assert result.returncode == 1
        data = _json.loads(result.stdout)
        assert "error" in data
