import json
from pathlib import Path
import shutil
import subprocess
import sys

from conftest import TEST_VAULT
import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "rename.py"


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """A writable copy of the fixture vault."""
    target = tmp_path / "vault"
    shutil.copytree(TEST_VAULT, target)
    return target


def run(vault: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--vault", str(vault), "--quiet", *args],
        capture_output=True,
        text=True,
        check=False,
    )


class TestRenameProperty:
    def test_rewrites_inline_and_fenced_bind_targets(self, vault: Path):
        result = run(vault, "--property", "count", "hitPoints")
        assert result.returncode == 0
        fields = (vault / "Fields.md").read_text(encoding="utf-8")
        assert "`INPUT[number:hitPoints]`" in fields
        assert "`VIEW[{hitPoints}]`" in fields
        # `{count} as count` keeps its alias — only the bind target moves.
        assert "{hitPoints} as count" in fields

    def test_rewrites_the_view_field_write_target(self, vault: Path):
        run(vault, "--property", "doubled", "trebled")
        assert "[math:trebled]" in (vault / "Fields.md").read_text(encoding="utf-8")

    def test_rewrites_button_update_metadata_targets(self, vault: Path):
        run(vault, "--property", "count", "hitPoints")
        buttons = (vault / "Buttons.md").read_text(encoding="utf-8")
        assert "bindTarget: hitPoints" in buttons
        assert "bindTarget: count" not in buttons

    def test_leaves_button_ids_alone(self, vault: Path):
        run(vault, "--property", "count", "hitPoints")
        buttons = (vault / "Buttons.md").read_text(encoding="utf-8")
        assert "id: count-increment" in buttons
        assert "`BUTTON[count-increment, count-reset]`" in buttons

    def test_never_rewrites_identifiers_inside_js(self, vault: Path):
        result = run(vault, "--property", "count", "hitPoints", "--format", "json")
        buttons = (vault / "Buttons.md").read_text(encoding="utf-8")
        assert "engine.getMetadata('count')" in buttons
        manual = json.loads(result.stdout)["data"]["manual"]
        assert any("JS mentions 'count'" in site["reason"] for site in manual)

    def test_rewrites_a_quoted_object_access(self, vault: Path):
        run(vault, "--property", "nested.object", "nested.payload")
        assert 'nested["payload"]' in (vault / "Fields.md").read_text(encoding="utf-8")

    def test_rewrites_only_the_matched_prefix(self, vault: Path):
        run(vault, "--property", "nested", "outer")
        assert 'outer["object"]' in (vault / "Fields.md").read_text(encoding="utf-8")

    def test_a_list_index_in_the_prefix_needs_manual_attention(self, vault: Path):
        result = run(vault, "--property", "list.0", "list.zero", "--format", "json")
        manual = json.loads(result.stdout)["data"]["manual"]
        assert any("list index" in site["reason"] for site in manual)
        assert "INPUT[text:list[0]]" in (vault / "Fields.md").read_text(encoding="utf-8")

    def test_leaves_memory_scoped_targets_with_other_names_alone(self, vault: Path):
        before = (vault / "Fields.md").read_text(encoding="utf-8")
        run(vault, "--property", "scratch", "notepad")
        after = (vault / "Fields.md").read_text(encoding="utf-8")
        assert "memory^notepad" in after
        assert before != after

    def test_unmatched_property_exits_3(self, vault: Path):
        result = run(vault, "--property", "noSuchProperty", "other")
        assert result.returncode == 3

    def test_segment_count_must_match(self, vault: Path):
        result = run(vault, "--property", "a.b", "c")
        assert result.returncode == 1
        assert json.loads(result.stderr)["code"] == "SEGMENT_MISMATCH"

    def test_invalid_new_name_is_rejected(self, vault: Path):
        result = run(vault, "--property", "count", "not a name")
        assert result.returncode == 1
        assert json.loads(result.stderr)["code"] == "INVALID_PROPERTY"


class TestRenamePath:
    def test_rewrites_the_file_half_of_a_bind_target(self, vault: Path):
        result = run(vault, "--path", "Other Note", "Reference Note")
        assert result.returncode == 0
        assert "INPUT[text:Reference Note#title]" in (vault / "Fields.md").read_text(
            encoding="utf-8"
        )

    def test_accepts_an_old_path_that_no_longer_exists(self, vault: Path):
        (vault / "Other Note.md").rename(vault / "Reference Note.md")
        result = run(vault, "--path", "Other Note", "Reference Note")
        assert result.returncode == 0
        assert "Reference Note#title" in (vault / "Fields.md").read_text(encoding="utf-8")

    def test_never_moves_the_file(self, vault: Path):
        run(vault, "--path", "Other Note", "Reference Note")
        assert (vault / "Other Note.md").exists()
        assert not (vault / "Reference Note.md").exists()

    def test_accepts_a_md_suffix(self, vault: Path):
        run(vault, "--path", "Other Note.md", "Reference Note.md")
        assert "Reference Note#title" in (vault / "Fields.md").read_text(encoding="utf-8")

    def test_leaves_wikilinks_alone(self, vault: Path):
        run(vault, "--path", "Other Note", "Reference Note")
        assert "[[Other Note]]" in (vault / "Fields.md").read_text(encoding="utf-8")

    def test_unmatched_path_exits_3(self, vault: Path):
        assert run(vault, "--path", "Absent Note", "Another").returncode == 3


class TestDryRun:
    def test_writes_nothing(self, vault: Path):
        before = (vault / "Fields.md").read_text(encoding="utf-8")
        result = run(vault, "--property", "count", "hitPoints", "--dry-run")
        assert result.returncode == 0
        assert (vault / "Fields.md").read_text(encoding="utf-8") == before

    def test_prints_a_unified_diff(self, vault: Path):
        result = run(vault, "--property", "count", "hitPoints", "--dry-run")
        assert "-An inline input field: `INPUT[number:count]`" in result.stdout
        assert "+An inline input field: `INPUT[number:hitPoints]`" in result.stdout

    def test_json_reports_before_and_after(self, vault: Path):
        result = run(vault, "--property", "count", "hitPoints", "--dry-run", "--json")
        payload = json.loads(result.stdout)
        assert payload["meta"]["dry_run"] is True
        rewritten = payload["data"]["rewritten"]
        assert any(
            site["before"] == "INPUT[number:count]" and site["after"] == "INPUT[number:hitPoints]"
            for site in rewritten
        )


class TestCli:
    def test_a_mode_is_required(self, vault: Path):
        assert run(vault).returncode == 2

    def test_modes_are_mutually_exclusive(self, vault: Path):
        assert run(vault, "--property", "a", "b", "--path", "c", "d").returncode == 2

    def test_outside_a_vault_exits_1(self, tmp_path: Path):
        result = run(tmp_path, "--property", "a", "b")
        assert result.returncode == 1
        assert json.loads(result.stderr)["code"] == "NOT_IN_VAULT"

    def test_help_shows_examples(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0
        assert "examples:" in result.stdout

    def test_rename_leaves_the_vault_check_clean(self, vault: Path):
        run(vault, "--property", "count", "hitPoints")
        scan = subprocess.run(
            [
                sys.executable,
                str(SCRIPT.parent / "scan.py"),
                "--vault",
                str(vault),
                "--check",
                "--quiet",
                str(vault / "Fields.md"),
                str(vault / "Buttons.md"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert scan.returncode == 0, scan.stdout
