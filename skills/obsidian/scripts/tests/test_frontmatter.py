import json
from pathlib import Path
import subprocess
import sys

import pytest
from vault_frontmatter import FrontmatterError, delete_key, merge, read, set_key, write

SCRIPT = Path(__file__).resolve().parent.parent / "vault_frontmatter.py"


def make_note(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content)
    return path


class TestRead:
    def test_no_frontmatter_returns_empty_dict_and_full_body(self, tmp_path: Path):
        note = make_note(tmp_path, "a.md", "# Just a heading\n\nbody here\n")
        fm, body = read(note)
        assert fm == {}
        assert body == "# Just a heading\n\nbody here\n"

    def test_simple_frontmatter(self, tmp_path: Path):
        note = make_note(
            tmp_path,
            "a.md",
            "---\ntitle: Hello\ncount: 3\n---\nbody\n",
        )
        fm, body = read(note)
        assert fm == {"title": "Hello", "count": 3}
        assert body == "body\n"

    def test_empty_frontmatter_block(self, tmp_path: Path):
        note = make_note(tmp_path, "a.md", "---\n---\nbody\n")
        fm, body = read(note)
        assert fm == {}
        assert body == "body\n"

    def test_frontmatter_with_list_values(self, tmp_path: Path):
        note = make_note(
            tmp_path,
            "a.md",
            "---\ntags:\n  - foo\n  - bar\naliases: [x, y]\n---\nbody\n",
        )
        fm, _body = read(note)
        assert fm["tags"] == ["foo", "bar"]
        assert fm["aliases"] == ["x", "y"]

    def test_horizontal_rule_in_body_not_treated_as_frontmatter(self, tmp_path: Path):
        note = make_note(
            tmp_path,
            "a.md",
            "---\ntitle: T\n---\nintro\n\n---\n\nmore\n",
        )
        fm, body = read(note)
        assert fm == {"title": "T"}
        assert body == "intro\n\n---\n\nmore\n"

    def test_no_frontmatter_when_file_starts_with_text_then_dashes(self, tmp_path: Path):
        note = make_note(tmp_path, "a.md", "intro\n---\ntitle: T\n---\n")
        fm, body = read(note)
        assert fm == {}
        assert body == "intro\n---\ntitle: T\n---\n"

    def test_preserves_insertion_order(self, tmp_path: Path):
        note = make_note(
            tmp_path,
            "a.md",
            "---\nz: 1\nm: 2\na: 3\n---\nbody\n",
        )
        fm, _ = read(note)
        assert list(fm.keys()) == ["z", "m", "a"]

    def test_unclosed_frontmatter_raises(self, tmp_path: Path):
        note = make_note(tmp_path, "a.md", "---\ntitle: T\nbody without closing\n")
        with pytest.raises(FrontmatterError):
            read(note)

    def test_malformed_yaml_in_block_raises(self, tmp_path: Path):
        note = make_note(
            tmp_path,
            "a.md",
            "---\nsource\nhttps://example.com/page\n---\nbody\n",
        )
        with pytest.raises(FrontmatterError):
            read(note)


class TestWrite:
    def test_writes_frontmatter_above_body(self, tmp_path: Path):
        note = make_note(tmp_path, "a.md", "body\n")
        write(note, {"title": "Hi"}, "body\n")
        text = note.read_text()
        assert text.startswith("---\ntitle: Hi\n---\n")
        assert text.endswith("body\n")

    def test_empty_frontmatter_strips_block(self, tmp_path: Path):
        note = make_note(tmp_path, "a.md", "---\ntitle: Hi\n---\nbody\n")
        write(note, {}, "body\n")
        assert note.read_text() == "body\n"

    def test_preserves_key_order_on_round_trip(self, tmp_path: Path):
        note = make_note(
            tmp_path,
            "a.md",
            "---\nz: 1\nm: 2\na: 3\n---\nbody\n",
        )
        fm, body = read(note)
        write(note, fm, body)
        assert "---\nz: 1\nm: 2\na: 3\n---" in note.read_text()


class TestSetKey:
    def test_adds_key_when_missing(self, tmp_path: Path):
        note = make_note(tmp_path, "a.md", "---\ntitle: T\n---\nbody\n")
        set_key(note, "tags", ["foo"])
        fm, _ = read(note)
        assert fm == {"title": "T", "tags": ["foo"]}

    def test_updates_existing_key_in_place(self, tmp_path: Path):
        note = make_note(
            tmp_path,
            "a.md",
            "---\ntitle: T\nstatus: draft\ncount: 1\n---\nbody\n",
        )
        set_key(note, "status", "published")
        fm, _ = read(note)
        assert list(fm.keys()) == ["title", "status", "count"]
        assert fm["status"] == "published"

    def test_creates_frontmatter_block_when_none_exists(self, tmp_path: Path):
        note = make_note(tmp_path, "a.md", "body\n")
        set_key(note, "title", "Hi")
        fm, body = read(note)
        assert fm == {"title": "Hi"}
        assert body == "body\n"


class TestDeleteKey:
    def test_removes_key_and_preserves_others(self, tmp_path: Path):
        note = make_note(
            tmp_path,
            "a.md",
            "---\ntitle: T\nstatus: draft\n---\nbody\n",
        )
        delete_key(note, "status")
        fm, _ = read(note)
        assert fm == {"title": "T"}

    def test_missing_key_is_noop(self, tmp_path: Path):
        note = make_note(tmp_path, "a.md", "---\ntitle: T\n---\nbody\n")
        delete_key(note, "nope")
        fm, _ = read(note)
        assert fm == {"title": "T"}

    def test_removing_last_key_strips_block(self, tmp_path: Path):
        note = make_note(tmp_path, "a.md", "---\ntitle: T\n---\nbody\n")
        delete_key(note, "title")
        assert note.read_text() == "body\n"


class TestMerge:
    def test_adds_and_overwrites(self, tmp_path: Path):
        note = make_note(
            tmp_path,
            "a.md",
            "---\ntitle: T\nstatus: draft\n---\nbody\n",
        )
        merge(note, {"status": "published", "tags": ["x"]})
        fm, _ = read(note)
        assert fm == {"title": "T", "status": "published", "tags": ["x"]}


class TestCli:
    def _run(self, *args: str):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_show_outputs_json(self, tmp_path: Path):
        note = make_note(tmp_path, "a.md", "---\ntitle: T\ncount: 3\n---\nbody\n")
        result = self._run("show", str(note))
        assert result.returncode == 0
        assert json.loads(result.stdout) == {"title": "T", "count": 3}

    def test_get_outputs_value_as_json(self, tmp_path: Path):
        note = make_note(tmp_path, "a.md", "---\ntags: [a, b]\n---\nbody\n")
        result = self._run("get", str(note), "tags")
        assert result.returncode == 0
        assert json.loads(result.stdout) == ["a", "b"]

    def test_get_missing_key_exits_nonzero(self, tmp_path: Path):
        note = make_note(tmp_path, "a.md", "---\ntitle: T\n---\nbody\n")
        result = self._run("get", str(note), "nope")
        assert result.returncode != 0

    def test_set_persists(self, tmp_path: Path):
        note = make_note(tmp_path, "a.md", "body\n")
        result = self._run("set", str(note), "title", "Hello")
        assert result.returncode == 0
        fm, _ = read(note)
        assert fm == {"title": "Hello"}

    def test_set_with_json_flag_parses_typed_value(self, tmp_path: Path):
        note = make_note(tmp_path, "a.md", "body\n")
        result = self._run("set", str(note), "tags", '["a","b"]', "--json")
        assert result.returncode == 0
        fm, _ = read(note)
        assert fm == {"tags": ["a", "b"]}

    def test_delete_persists(self, tmp_path: Path):
        note = make_note(tmp_path, "a.md", "---\na: 1\nb: 2\n---\nbody\n")
        result = self._run("delete", str(note), "a")
        assert result.returncode == 0
        fm, _ = read(note)
        assert fm == {"b": 2}
