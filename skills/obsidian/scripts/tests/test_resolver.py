from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from resolver import Resolver

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / ".obsidian").mkdir()
    return tmp_path


def write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestResolve:
    def test_resolves_by_basename(self, vault: Path):
        note = write(vault / "Alpha.md")
        r = Resolver(vault)
        assert r.resolve("Alpha") == {note.resolve()}

    def test_resolves_by_relpath(self, vault: Path):
        note = write(vault / "notes" / "Alpha.md")
        r = Resolver(vault)
        assert r.resolve("notes/Alpha") == {note.resolve()}

    def test_resolves_by_string_alias(self, vault: Path):
        note = write(vault / "Alpha.md", "---\naliases: foo\n---\n")
        r = Resolver(vault)
        assert r.resolve("foo") == {note.resolve()}

    def test_resolves_by_list_alias(self, vault: Path):
        note = write(
            vault / "Alpha.md",
            "---\naliases:\n  - foo\n  - bar baz\n---\n",
        )
        r = Resolver(vault)
        assert r.resolve("foo") == {note.resolve()}
        assert r.resolve("bar baz") == {note.resolve()}

    def test_resolution_is_case_insensitive(self, vault: Path):
        note = write(vault / "Alpha.md")
        r = Resolver(vault)
        assert r.resolve("alpha") == {note.resolve()}
        assert r.resolve("ALPHA") == {note.resolve()}
        assert r.resolve("aLpHa") == {note.resolve()}

    def test_unknown_target_returns_empty(self, vault: Path):
        write(vault / "Alpha.md")
        r = Resolver(vault)
        assert r.resolve("nonexistent") == set()

    def test_multiple_notes_same_basename(self, vault: Path):
        n1 = write(vault / "notes" / "Alpha.md")
        n2 = write(vault / "archive" / "Alpha.md")
        r = Resolver(vault)
        assert r.resolve("Alpha") == {n1.resolve(), n2.resolve()}

    def test_relpath_disambiguates_collision(self, vault: Path):
        n1 = write(vault / "notes" / "Alpha.md")
        write(vault / "archive" / "Alpha.md")
        r = Resolver(vault)
        assert r.resolve("notes/Alpha") == {n1.resolve()}

    def test_skips_dot_obsidian_and_trash(self, vault: Path):
        write(vault / ".obsidian" / "Alpha.md")
        (vault / ".trash").mkdir()
        write(vault / ".trash" / "Alpha.md")
        real = write(vault / "Alpha.md")
        r = Resolver(vault)
        assert r.resolve("Alpha") == {real.resolve()}


class TestNamesFor:
    def test_returns_basename_and_relpath(self, vault: Path):
        note = write(vault / "notes" / "Alpha.md")
        r = Resolver(vault)
        names = r.names_for(note)
        assert "alpha" in names
        assert "notes/alpha" in names

    def test_includes_aliases_lowercased(self, vault: Path):
        note = write(
            vault / "Alpha.md",
            "---\naliases: [Foo, BAR]\n---\n",
        )
        r = Resolver(vault)
        names = r.names_for(note)
        assert "foo" in names
        assert "bar" in names

    def test_returns_empty_set_for_unknown_note(self, vault: Path, tmp_path: Path):
        write(vault / "Alpha.md")
        r = Resolver(vault)
        assert r.names_for(tmp_path / "outside.md") == set()


class TestMatches:
    def test_basename_match(self, vault: Path):
        note = write(vault / "Alpha.md")
        r = Resolver(vault)
        assert r.matches("Alpha", note)

    def test_relpath_match(self, vault: Path):
        note = write(vault / "notes" / "Alpha.md")
        r = Resolver(vault)
        assert r.matches("notes/Alpha", note)

    def test_alias_match(self, vault: Path):
        note = write(vault / "Alpha.md", "---\naliases: [foo]\n---\n")
        r = Resolver(vault)
        assert r.matches("foo", note)

    def test_case_insensitive_match(self, vault: Path):
        note = write(vault / "Alpha.md")
        r = Resolver(vault)
        assert r.matches("alpha", note)
        assert r.matches("ALPHA", note)

    def test_unrelated_target_does_not_match(self, vault: Path):
        note = write(vault / "Alpha.md")
        write(vault / "Beta.md")
        r = Resolver(vault)
        assert not r.matches("Beta", note)

    def test_partial_name_does_not_match(self, vault: Path):
        note = write(vault / "Alpha.md")
        r = Resolver(vault)
        assert not r.matches("Alph", note)
        assert not r.matches("AlphaX", note)


class TestRobustness:
    def test_malformed_frontmatter_does_not_break_other_names(self, vault: Path):
        note = write(
            vault / "Alpha.md",
            "---\nthis is not\nvalid yaml: : :\n---\n",
        )
        r = Resolver(vault)
        # Aliases unrecoverable, but basename/relpath still resolve.
        assert r.resolve("Alpha") == {note.resolve()}

    def test_alias_that_is_not_a_string_is_ignored(self, vault: Path):
        note = write(
            vault / "Alpha.md",
            "---\naliases:\n  - 5\n  - foo\n---\n",
        )
        r = Resolver(vault)
        assert r.resolve("foo") == {note.resolve()}

    def test_index_built_lazily(self, vault: Path):
        write(vault / "Alpha.md")
        r = Resolver(vault)
        # Add a file after Resolver is constructed.
        write(vault / "Beta.md")
        # Build is triggered by first query; should see Beta.
        assert r.resolve("Beta") != set()

    def test_index_cached_across_queries(self, vault: Path):
        note = write(vault / "Alpha.md")
        r = Resolver(vault)
        r.resolve("Alpha")
        # Add after first query — cache should NOT pick this up.
        write(vault / "Late.md")
        assert r.resolve("Late") == set()
        assert r.resolve("Alpha") == {note.resolve()}
