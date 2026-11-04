"""Where things live: the bundle, its in-repo link, the marketplace, the folded validators."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
SMOKE = REPO / ".claude" / "skills" / "run-skills" / "smoke.py"
BUNDLE = REPO / "plugins" / "ai-sdlc"
SKILLS = ("spec-define", "spec-design", "spec-develop", "spec-verify")
AGENTS = ("critic-specification", "critic-architecture")


def _marketplace() -> dict[str, dict[str, str]]:
    data = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    return {p["name"]: p for p in data["plugins"]}


def test_marketplace_lists_the_bundle_and_review_repo_agents() -> None:
    plugins = _marketplace()
    assert plugins["ai-sdlc"]["source"] == "./plugins/ai-sdlc"
    assert plugins["review-repo-agents"]["source"] == "./skills/review-repo-agents"


def test_marketplace_does_not_offer_agent_tool_builder() -> None:
    assert "agent-tool-builder" not in _marketplace()
    assert not (REPO / "skills" / "agent-tool-builder").exists()


def test_real_marketplace_agrees_with_disk() -> None:
    proc = subprocess.run(
        [sys.executable, str(SMOKE), "--only", "manifests", "--json", "--quiet"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout


def test_bundle_holds_the_four_skills_and_two_critics_and_nothing_else() -> None:
    assert {p.name for p in BUNDLE.iterdir()} == {".claude-plugin", "skills", "agents"}
    assert {p.name for p in (BUNDLE / "skills").iterdir()} == set(SKILLS)
    assert {p.name for p in (BUNDLE / "agents").iterdir()} == {f"{a}.md" for a in AGENTS}


def test_bundle_manifest_names_the_bundle_and_carries_a_version() -> None:
    manifest = json.loads((BUNDLE / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "ai-sdlc"
    assert manifest["version"]


def test_repo_loads_the_bundle_through_a_link_not_a_copy() -> None:
    link = REPO / ".claude" / "skills" / "ai-sdlc"
    assert link.is_symlink()
    assert link.resolve() == BUNDLE
    for skill in SKILLS:
        assert not (REPO / ".claude" / "skills" / skill).exists()
    assert not (REPO / ".claude" / "agents").exists()


def test_project_settings_disable_the_installed_bundle_so_the_link_wins() -> None:
    settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert settings["enabledPlugins"]["ai-sdlc@rafaelh"] is False


def test_bundle_skills_use_namespaced_hand_offs_and_critic_launches() -> None:
    for skill in SKILLS:
        text = (BUNDLE / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        assert not re.search(r"`/spec-[a-z]+`", text), skill
    define = (BUNDLE / "skills" / "spec-define" / "SKILL.md").read_text(encoding="utf-8")
    design = (BUNDLE / "skills" / "spec-design" / "SKILL.md").read_text(encoding="utf-8")
    assert "`ai-sdlc:critic-specification`" in define
    assert "`ai-sdlc:critic-architecture`" in design


def test_agent_tool_tooling_lives_in_skill_audit() -> None:
    audit = REPO / "skills" / "skill-audit"
    for rel in (
        "scripts/validate_agent_tool.py",
        "scripts/perf_check.py",
        "scripts/tests/test_validate_agent_tool.py",
        "scripts/tests/test_perf_check.py",
        "references/perf-findings.md",
        "references/interface-contract.md",
    ):
        assert (audit / rel).is_file(), rel
    skill_md = (audit / "SKILL.md").read_text(encoding="utf-8")
    assert "agent-tool-builder" not in skill_md
    assert "${SKILL_DIR}/scripts/validate_agent_tool.py" in skill_md


def test_nothing_that_remains_links_to_agent_tool_builder() -> None:
    offenders = [
        path.relative_to(REPO).as_posix()
        for root in ("skills", ".claude/skills/run-skills", "pyproject.toml", ".claude-plugin")
        for path in ([REPO / root] if (REPO / root).is_file() else (REPO / root).rglob("*"))
        if path.is_file()
        and "node_modules" not in path.parts
        and "__pycache__" not in path.parts
        and re.search(
            r"agent-tool-builder/|skills/agent-tool-builder|\.\./agent-tool-builder",
            path.read_text(encoding="utf-8", errors="ignore"),
        )
    ]
    assert offenders == []
