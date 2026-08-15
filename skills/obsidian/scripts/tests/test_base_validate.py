from pathlib import Path
import subprocess
import sys

from base_validate import validate_base

SCRIPT = Path(__file__).resolve().parent.parent / "base_validate.py"


def make(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "x.base"
    p.write_text(content)
    return p


class TestValidateBase:
    def test_minimal_views_only(self, tmp_path: Path):
        result = validate_base(make(tmp_path, "views:\n  - type: table\n    name: T\n"))
        assert result.valid, result.errors

    def test_realistic_table_view(self, tmp_path: Path):
        text = (
            "properties:\n"
            "  file.name:\n"
            "    displayName: Item\n"
            "views:\n"
            "  - type: table\n"
            "    name: Table\n"
            "    filters:\n"
            "      and:\n"
            '        - file.ext == ".md"\n'
            "    order:\n"
            "      - file.name\n"
            "    sort:\n"
            "      - property: file.name\n"
            "        direction: ASC\n"
        )
        result = validate_base(make(tmp_path, text))
        assert result.valid, result.errors

    def test_invalid_yaml_fails(self, tmp_path: Path):
        result = validate_base(make(tmp_path, "views:\n  - this is bad: : :"))
        assert not result.valid
        assert any("yaml" in e.lower() for e in result.errors)

    def test_top_level_not_mapping(self, tmp_path: Path):
        result = validate_base(make(tmp_path, "- a\n- b\n"))
        assert not result.valid

    def test_views_must_be_list(self, tmp_path: Path):
        result = validate_base(make(tmp_path, "views: not-a-list\n"))
        assert not result.valid
        assert any("views" in e for e in result.errors)

    def test_view_missing_type(self, tmp_path: Path):
        result = validate_base(make(tmp_path, "views:\n  - name: NoType\n"))
        assert not result.valid
        assert any("type" in e for e in result.errors)

    def test_view_type_must_be_string(self, tmp_path: Path):
        result = validate_base(make(tmp_path, "views:\n  - type: 5\n    name: T\n"))
        assert not result.valid

    def test_sort_direction_must_be_asc_or_desc(self, tmp_path: Path):
        text = (
            "views:\n"
            "  - type: table\n"
            "    name: T\n"
            "    sort:\n"
            "      - property: x\n"
            "        direction: SIDEWAYS\n"
        )
        result = validate_base(make(tmp_path, text))
        assert not result.valid
        assert any("direction" in e for e in result.errors)

    def test_properties_must_be_mapping(self, tmp_path: Path):
        result = validate_base(make(tmp_path, "properties: not-a-mapping\nviews: []\n"))
        assert not result.valid

    def test_property_entry_must_be_mapping(self, tmp_path: Path):
        text = "properties:\n  file.name: oops\nviews: []\n"
        result = validate_base(make(tmp_path, text))
        assert not result.valid


class TestCli:
    def _run(self, *args: str):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_valid_exits_zero(self, tmp_path: Path):
        p = make(tmp_path, "views:\n  - type: table\n    name: T\n")
        result = self._run(str(p))
        assert result.returncode == 0

    def test_invalid_exits_nonzero(self, tmp_path: Path):
        p = make(tmp_path, "views: not-a-list\n")
        result = self._run(str(p))
        assert result.returncode != 0

    def test_json_output_valid(self, tmp_path: Path):
        import json

        p = make(tmp_path, "views:\n  - type: table\n    name: T\n")
        result = self._run(str(p), "--json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["errors"] == []

    def test_json_output_invalid(self, tmp_path: Path):
        import json

        p = make(tmp_path, "views: not-a-list\n")
        result = self._run(str(p), "--json")
        assert result.returncode == 1
        data = json.loads(result.stdout)
        assert data["valid"] is False
        assert len(data["errors"]) >= 1
