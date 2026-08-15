import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from canvas_validate import validate_canvas

SCRIPT = Path(__file__).resolve().parent.parent / "canvas_validate.py"


def make(tmp_path: Path, payload: Any) -> Path:
    p = tmp_path / "board.canvas"
    p.write_text(json.dumps(payload))
    return p


class TestValidateCanvas:
    def test_minimal_empty_is_valid(self, tmp_path: Path):
        result = validate_canvas(make(tmp_path, {"nodes": [], "edges": []}))
        assert result.valid is True
        assert result.errors == []

    def test_text_node_valid(self, tmp_path: Path):
        node = {
            "id": "n1",
            "type": "text",
            "x": 0,
            "y": 0,
            "width": 200,
            "height": 100,
            "text": "hello",
        }
        result = validate_canvas(make(tmp_path, {"nodes": [node], "edges": []}))
        assert result.valid

    def test_file_node_valid(self, tmp_path: Path):
        node = {
            "id": "n1",
            "type": "file",
            "x": 0,
            "y": 0,
            "width": 200,
            "height": 100,
            "file": "notes/Alpha.md",
        }
        result = validate_canvas(make(tmp_path, {"nodes": [node], "edges": []}))
        assert result.valid

    def test_link_node_valid(self, tmp_path: Path):
        node = {
            "id": "n1",
            "type": "link",
            "x": 0,
            "y": 0,
            "width": 200,
            "height": 100,
            "url": "https://example.com",
        }
        result = validate_canvas(make(tmp_path, {"nodes": [node], "edges": []}))
        assert result.valid

    def test_group_node_valid(self, tmp_path: Path):
        node = {
            "id": "n1",
            "type": "group",
            "x": 0,
            "y": 0,
            "width": 200,
            "height": 100,
        }
        result = validate_canvas(make(tmp_path, {"nodes": [node], "edges": []}))
        assert result.valid

    def test_edge_with_existing_nodes_valid(self, tmp_path: Path):
        nodes = [
            {"id": "a", "type": "text", "x": 0, "y": 0, "width": 1, "height": 1, "text": ""},
            {"id": "b", "type": "text", "x": 0, "y": 0, "width": 1, "height": 1, "text": ""},
        ]
        edges = [{"id": "e1", "fromNode": "a", "toNode": "b"}]
        result = validate_canvas(make(tmp_path, {"nodes": nodes, "edges": edges}))
        assert result.valid

    def test_invalid_json_fails(self, tmp_path: Path):
        p = tmp_path / "board.canvas"
        p.write_text("not json {")
        result = validate_canvas(p)
        assert not result.valid
        assert any("json" in e.lower() for e in result.errors)

    def test_top_level_not_object_fails(self, tmp_path: Path):
        p = make(tmp_path, [])
        result = validate_canvas(p)
        assert not result.valid

    def test_node_missing_required_field_fails(self, tmp_path: Path):
        node = {"id": "n1", "type": "text", "x": 0, "y": 0}
        result = validate_canvas(make(tmp_path, {"nodes": [node], "edges": []}))
        assert not result.valid
        assert any("width" in e or "height" in e for e in result.errors)

    def test_unknown_node_type_fails(self, tmp_path: Path):
        node = {
            "id": "n1",
            "type": "rocket",
            "x": 0,
            "y": 0,
            "width": 1,
            "height": 1,
        }
        result = validate_canvas(make(tmp_path, {"nodes": [node], "edges": []}))
        assert not result.valid

    def test_text_node_missing_text_fails(self, tmp_path: Path):
        node = {"id": "n1", "type": "text", "x": 0, "y": 0, "width": 1, "height": 1}
        result = validate_canvas(make(tmp_path, {"nodes": [node], "edges": []}))
        assert not result.valid

    def test_edge_referencing_unknown_node_fails(self, tmp_path: Path):
        nodes = [{"id": "a", "type": "text", "x": 0, "y": 0, "width": 1, "height": 1, "text": ""}]
        edges = [{"id": "e1", "fromNode": "a", "toNode": "ghost"}]
        result = validate_canvas(make(tmp_path, {"nodes": nodes, "edges": edges}))
        assert not result.valid
        assert any("ghost" in e for e in result.errors)

    def test_duplicate_node_ids_fail(self, tmp_path: Path):
        nodes = [
            {"id": "a", "type": "text", "x": 0, "y": 0, "width": 1, "height": 1, "text": ""},
            {"id": "a", "type": "text", "x": 0, "y": 0, "width": 1, "height": 1, "text": ""},
        ]
        result = validate_canvas(make(tmp_path, {"nodes": nodes, "edges": []}))
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
        p = tmp_path / "board.canvas"
        p.write_text(json.dumps({"nodes": [], "edges": []}))
        result = self._run(str(p))
        assert result.returncode == 0

    def test_invalid_exits_nonzero(self, tmp_path: Path):
        p = tmp_path / "board.canvas"
        p.write_text("not json")
        result = self._run(str(p))
        assert result.returncode != 0

    def test_json_output_valid(self, tmp_path: Path):
        p = tmp_path / "board.canvas"
        p.write_text(json.dumps({"nodes": [], "edges": []}))
        result = self._run(str(p), "--json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["errors"] == []
        assert data["file"] == str(p)

    def test_json_output_invalid(self, tmp_path: Path):
        p = tmp_path / "board.canvas"
        p.write_text("not json")
        result = self._run(str(p), "--json")
        assert result.returncode == 1
        data = json.loads(result.stdout)
        assert data["valid"] is False
        assert len(data["errors"]) >= 1
