import json
from pathlib import Path
import subprocess
import sys

from conftest import TEST_VAULT
import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scan.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def codes(result: subprocess.CompletedProcess[str]) -> set[str]:
    return {finding["code"] for finding in json.loads(result.stdout)["data"]}


@pytest.fixture
def empty_vault(tmp_path: Path) -> Path:
    (tmp_path / ".obsidian").mkdir()
    return tmp_path


class TestList:
    def test_lists_every_declaration(self):
        result = run("--vault", str(TEST_VAULT), "--list", "--json", "--quiet")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["meta"]["count"] == len(payload["data"])
        assert payload["meta"]["count"] > 20

    def test_row_shape_is_stable(self):
        result = run("--vault", str(TEST_VAULT), "--list", "--json", "--quiet")
        for row in json.loads(result.stdout)["data"]:
            assert set(row) == {
                "file",
                "line",
                "column",
                "kind",
                "host",
                "field_type",
                "template_name",
                "bind_target",
                "read_targets",
                "arguments",
                "button_ids",
                "button_id",
                "embed_target",
                "has_errors",
                "raw",
            }

    def test_finds_the_cross_note_bind_target(self):
        result = run("--vault", str(TEST_VAULT), "--list", "--json", "--quiet")
        targets = {row["bind_target"] for row in json.loads(result.stdout)["data"]}
        assert "Other Note#title" in targets
        assert 'nested["object"]' in targets
        assert "memory^scratch" in targets

    def test_positional_paths_narrow_the_scope(self):
        result = run(
            "--vault",
            str(TEST_VAULT),
            "--list",
            "--json",
            "--quiet",
            str(TEST_VAULT / "Buttons.md"),
        )
        files = {row["file"] for row in json.loads(result.stdout)["data"]}
        assert files == {str(TEST_VAULT / "Buttons.md")}

    def test_empty_scope_exits_3(self, empty_vault: Path):
        result = run("--vault", str(empty_vault), "--list", "--quiet")
        assert result.returncode == 3

    def test_text_output_is_greppable(self):
        result = run("--vault", str(TEST_VAULT), "--list", "--quiet")
        assert result.returncode == 0
        assert "input:toggle" in result.stdout


class TestCheck:
    def test_valid_notes_are_clean(self):
        result = run(
            "--vault",
            str(TEST_VAULT),
            "--check",
            "--quiet",
            str(TEST_VAULT / "Fields.md"),
            str(TEST_VAULT / "Buttons.md"),
            str(TEST_VAULT / "Other Note.md"),
        )
        assert result.returncode == 0, result.stdout

    @pytest.mark.parametrize(
        "code",
        [
            "metabind.parse-error",
            "metabind.unknown-field-type",
            "metabind.unknown-argument",
            "metabind.argument-not-allowed",
            "metabind.argument-arity",
            "metabind.argument-value",
            "metabind.duplicate-argument",
            "metabind.inline-not-allowed",
            "metabind.unresolved-button-id",
            "metabind.button-config",
            "metabind.unknown-button-action",
            "metabind.button-action-field",
        ],
    )
    def test_every_finding_class_fires(self, code: str):
        result = run(
            "--vault",
            str(TEST_VAULT),
            "--check",
            "--json",
            "--quiet",
            str(TEST_VAULT / "Broken.md"),
        )
        assert result.returncode == 1
        assert code in codes(result)

    def test_findings_carry_a_location(self):
        result = run(
            "--vault",
            str(TEST_VAULT),
            "--check",
            "--json",
            "--quiet",
            str(TEST_VAULT / "Broken.md"),
        )
        for finding in json.loads(result.stdout)["data"]:
            assert finding["line"] >= 1
            assert finding["column"] >= 1
            assert finding["severity"] in ("error", "warning")

    def test_strict_is_off_by_default(self):
        result = run(
            "--vault",
            str(TEST_VAULT),
            "--check",
            "--json",
            "--quiet",
            str(TEST_VAULT / "Broken.md"),
        )
        assert "metabind.missing-property" not in codes(result)

    def test_strict_reports_absent_properties(self):
        result = run(
            "--vault",
            str(TEST_VAULT),
            "--check",
            "--strict",
            "--json",
            "--quiet",
            str(TEST_VAULT / "Broken.md"),
        )
        assert "metabind.missing-property" in codes(result)
        assert "metabind.unresolved-note" in codes(result)

    def test_strict_accepts_memory_scoped_targets(self):
        result = run(
            "--vault",
            str(TEST_VAULT),
            "--check",
            "--strict",
            "--json",
            "--quiet",
            str(TEST_VAULT / "Fields.md"),
        )
        messages = [f["message"] for f in json.loads(result.stdout)["data"]]
        assert not any("scratch" in message or "shared" in message for message in messages)

    def test_button_ids_resolve_across_the_vault(self, tmp_path: Path):
        (tmp_path / ".obsidian").mkdir()
        (tmp_path / "Config.md").write_text(
            "```meta-bind-button\nlabel: Go\nstyle: primary\nid: go\n"
            "action:\n  type: command\n  command: editor:save-file\n```\n",
            encoding="utf-8",
        )
        (tmp_path / "Use.md").write_text("`BUTTON[go]`\n", encoding="utf-8")
        result = run(
            "--vault", str(tmp_path), "--check", "--json", "--quiet", str(tmp_path / "Use.md")
        )
        assert result.returncode == 0, result.stdout

    def test_empty_scope_exits_3(self, empty_vault: Path):
        result = run("--vault", str(empty_vault), "--check", "--quiet")
        assert result.returncode == 3


class TestCli:
    def test_missing_spec_exits_2(self, tmp_path: Path):
        result = run(
            "--vault",
            str(TEST_VAULT),
            "--check",
            "--quiet",
            "--spec-path",
            str(tmp_path / "nope.json"),
        )
        assert result.returncode == 2
        assert json.loads(result.stderr)["code"] == "SPEC_UNAVAILABLE"

    def test_unknown_path_exits_1(self, tmp_path: Path):
        result = run("--vault", str(TEST_VAULT), "--list", "--quiet", str(tmp_path / "nope.md"))
        assert result.returncode == 1
        assert json.loads(result.stderr)["code"] == "PATH_NOT_FOUND"

    def test_outside_a_vault_exits_1(self, tmp_path: Path):
        result = run("--vault", str(tmp_path), "--list", "--quiet")
        assert result.returncode == 1
        assert json.loads(result.stderr)["code"] == "NOT_IN_VAULT"

    def test_a_mode_is_required(self):
        assert run("--vault", str(TEST_VAULT)).returncode == 2

    def test_format_json_matches_the_json_alias(self):
        with_flag = run("--vault", str(TEST_VAULT), "--list", "--json", "--quiet")
        with_format = run("--vault", str(TEST_VAULT), "--list", "--format", "json", "--quiet")
        assert with_flag.stdout == with_format.stdout

    def test_quiet_suppresses_the_summary(self):
        noisy = run("--vault", str(TEST_VAULT), "--list", "--json")
        quiet = run("--vault", str(TEST_VAULT), "--list", "--json", "--quiet")
        assert noisy.stderr != ""
        assert quiet.stderr == ""

    def test_help_shows_examples(self):
        result = run("--help")
        assert result.returncode == 0
        assert "examples:" in result.stdout
