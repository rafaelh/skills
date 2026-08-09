"""Black-box subprocess tests for validate_agent_def.py."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "validate_agent_def.py"

GOOD_AGENT = """\
---
name: test-runner
description: Run the test suite and report only what failed. Use proactively before a commit.
tools: Bash, Read
model: haiku
maxTurns: 6
---

You run the tests and report what failed.

## Procedure
1. `uv run pytest -q`

## Report
On green: `All N tests pass.` and nothing else.
"""


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _codes(result: subprocess.CompletedProcess[str]) -> set[str]:
    payload: dict[str, Any] = json.loads(result.stdout)
    findings: list[dict[str, Any]] = payload["data"]["findings"]
    return {finding["code"] for finding in findings}


def _write_agent(directory: Path, name: str, text: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_help_works() -> None:
    result = _run("--help")
    assert result.returncode == 0
    assert "examples:" in result.stdout.lower()


def test_missing_path_exits_2_with_structured_stderr(tmp_path: Path) -> None:
    result = _run(str(tmp_path / "nope"))
    assert result.returncode == 2
    assert json.loads(result.stderr)["code"] == "bad-invocation"


def test_empty_directory_exits_3(tmp_path: Path) -> None:
    agents = tmp_path / "agents"
    agents.mkdir()
    result = _run(str(agents))
    assert result.returncode == 3


def test_valid_agent_passes(tmp_path: Path) -> None:
    agents = tmp_path / "agents"
    _write_agent(agents, "test-runner", GOOD_AGENT)
    result = _run(str(agents), "--json")
    assert result.returncode == 0
    assert _codes(result) == set()


def test_invalid_model_fails(tmp_path: Path) -> None:
    agents = tmp_path / "agents"
    _write_agent(agents, "test-runner", GOOD_AGENT.replace("model: haiku", "model: cheap"))
    result = _run(str(agents), "--json")
    assert result.returncode == 1
    assert "agent.model.invalid" in _codes(result)


def test_full_model_id_is_accepted(tmp_path: Path) -> None:
    agents = tmp_path / "agents"
    _write_agent(agents, "test-runner", GOOD_AGENT.replace("model: haiku", "model: claude-opus-5"))
    result = _run(str(agents), "--json")
    assert result.returncode == 0


def test_colon_in_name_fails(tmp_path: Path) -> None:
    agents = tmp_path / "agents"
    _write_agent(agents, "runner", GOOD_AGENT.replace("name: test-runner", "name: plug:runner"))
    result = _run(str(agents), "--json")
    assert result.returncode == 1
    assert "agent.name.colon" in _codes(result)


def test_empty_tools_list_fails(tmp_path: Path) -> None:
    agents = tmp_path / "agents"
    _write_agent(agents, "test-runner", GOOD_AGENT.replace("tools: Bash, Read", "tools: []"))
    result = _run(str(agents), "--json")
    assert result.returncode == 1
    assert "agent.tools.empty" in _codes(result)


def test_missing_return_contract_warns(tmp_path: Path) -> None:
    agents = tmp_path / "agents"
    body_only = GOOD_AGENT.split("## Report", maxsplit=1)[0]
    _write_agent(agents, "test-runner", body_only)
    result = _run(str(agents), "--json")
    assert result.returncode == 0  # warn, not fail
    assert "agent.body.no-return-contract" in _codes(result)


def test_multiline_description_is_parsed_whole(tmp_path: Path) -> None:
    """Agent descriptions routinely wrap across indented lines; truncating one
    at the first line would falsely trip the too-thin check."""
    agents = tmp_path / "agents"
    one_line = next(ln for ln in GOOD_AGENT.splitlines() if ln.startswith("description:"))
    wrapped = GOOD_AGENT.replace(
        one_line,
        "description: Run\n  the test suite and report only what failed, using it proactively.",
    )
    _write_agent(agents, "test-runner", wrapped)
    result = _run(str(agents), "--json")
    assert result.returncode == 0
    assert "agent.description.thin" not in _codes(result)


def test_unreferenced_agent_fails_reference_check(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_agent(repo / ".claude" / "agents", "test-runner", GOOD_AGENT)
    (repo / "CLAUDE.md").write_text("# Project\n\nNothing routes anywhere.\n", encoding="utf-8")
    result = _run(str(repo / ".claude" / "agents"), "--check-references", str(repo), "--json")
    assert result.returncode == 1
    assert "agent.refs.unreferenced" in _codes(result)


def test_agent_named_in_claude_md_passes_reference_check(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_agent(repo / ".claude" / "agents", "test-runner", GOOD_AGENT)
    (repo / "CLAUDE.md").write_text(
        "# Project\n\n## Delegation\n\n| Work | Use |\n|---|---|\n| Tests | `test-runner` |\n",
        encoding="utf-8",
    )
    result = _run(str(repo / ".claude" / "agents"), "--check-references", str(repo), "--json")
    assert result.returncode == 0


def test_self_reference_does_not_count_through_a_symlink(tmp_path: Path) -> None:
    """A repo whose .claude symlinks elsewhere reaches each agent by two paths.
    Comparing unresolved paths lets an agent match its own definition file and
    pass as referenced, which silently defeats the whole check."""
    repo = tmp_path / "repo"
    real = repo / ".agents"
    _write_agent(real / "agents", "test-runner", GOOD_AGENT)
    (repo / ".claude").symlink_to(real)
    (repo / "CLAUDE.md").write_text("# Project\n\nNo routing here.\n", encoding="utf-8")
    result = _run(str(repo / ".claude" / "agents"), "--check-references", str(repo), "--json")
    assert result.returncode == 1
    assert "agent.refs.unreferenced" in _codes(result)
