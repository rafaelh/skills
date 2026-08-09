"""Black-box subprocess tests for scan_delegation_targets.py."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "scan_delegation_targets.py"

SKILL = """\
---
name: {name}
description: A skill that does something worth delegating parts of.
---

# {name}

## Workflow

1. **Run the validators.** Bulk output nobody rereads.
2. **Decide what to do.** Judgement, stays put.
"""

AGENT = """\
---
name: test-runner
description: Run the test suite and report only what failed. Use proactively before a commit.
tools: Bash, Read
model: haiku
---

You run the tests.

## Report
One line on green.
"""


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _data(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(result.stdout)
    data: dict[str, Any] = payload["data"]
    return data


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_help_works() -> None:
    result = _run("--help")
    assert result.returncode == 0
    assert "examples:" in result.stdout.lower()


def test_missing_path_exits_1_with_structured_stderr(tmp_path: Path) -> None:
    result = _run(str(tmp_path / "nope"))
    assert result.returncode == 1
    assert json.loads(result.stderr)["code"] == "bad-invocation"


def test_empty_repo_exits_3(tmp_path: Path) -> None:
    result = _run(str(tmp_path), "--json")
    assert result.returncode == 3


def test_finds_skills_agents_and_toolchain(tmp_path: Path) -> None:
    _write(tmp_path / ".claude" / "skills" / "tdd" / "SKILL.md", SKILL.format(name="tdd"))
    _write(tmp_path / ".claude" / "agents" / "test-runner.md", AGENT)
    _write(tmp_path / "CLAUDE.md", "# Project\n\n```bash\nuv run pytest\n```\n")
    _write(tmp_path / "pyproject.toml", "[tool.pytest.ini_options]\n\n[tool.ruff]\n")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")

    result = _run(str(tmp_path), "--json")
    assert result.returncode == 0
    data = _data(result)

    assert [s["name"] for s in data["skills"]] == ["tdd"]
    assert data["agents"][0]["model"] == "haiku"
    assert data["agents"][0]["tools"] == ["Bash", "Read"]
    commands = [t["command"] for t in data["toolchain"]]
    assert "uv run pytest" in commands  # uv.lock present, so the runner is prefixed
    assert data["claude_md"][0]["fenced_commands"] == ["uv run pytest"]


def test_skill_outline_captures_workflow_steps(tmp_path: Path) -> None:
    _write(tmp_path / ".claude" / "skills" / "tdd" / "SKILL.md", SKILL.format(name="tdd"))
    data = _data(_run(str(tmp_path), "--json"))
    kinds = [entry["kind"] for entry in data["skills"][0]["outline"]]
    assert "heading" in kinds
    assert "step" in kinds


def test_symlinked_claude_dir_does_not_double_count_skills(tmp_path: Path) -> None:
    """A repo whose .claude symlinks to .agents reaches every skill twice."""
    _write(tmp_path / ".agents" / "skills" / "tdd" / "SKILL.md", SKILL.format(name="tdd"))
    (tmp_path / ".claude").symlink_to(tmp_path / ".agents")
    data = _data(_run(str(tmp_path), "--json"))
    assert [s["name"] for s in data["skills"]] == ["tdd"]


def test_plugin_sourced_skill_is_marked_not_editable(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    repo = tmp_path / "repo"
    _write(plugins / "market" / "skills" / "tdd" / "SKILL.md", SKILL.format(name="tdd"))
    (repo / ".claude" / "skills").mkdir(parents=True)
    (repo / ".claude" / "skills" / "tdd").symlink_to(plugins / "market" / "skills" / "tdd")
    _write(repo / "CLAUDE.md", "# Project\n")

    data = _data(_run(str(repo), "--plugins-dir", str(plugins), "--json"))
    skill = data["skills"][0]
    assert skill["origin"] == "plugin"
    assert skill["editable"] is False


def test_reports_gitignored_agents_dir(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    _write(tmp_path / ".gitignore", ".claude/\n")
    _write(tmp_path / ".claude" / "agents" / "test-runner.md", AGENT)
    data = _data(_run(str(tmp_path), "--json"))
    assert data["agents_dir"]["gitignored"] is True
