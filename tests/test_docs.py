"""The doc surface: CLAUDE.md's size budget and the claims README and CLAUDE.md must make."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLAUDE_MD = REPO / "CLAUDE.md"
README = REPO / "README.md"

CLAUDE_MD_BUDGET = 8192


def test_claude_md_fits_its_size_budget() -> None:
    assert CLAUDE_MD.stat().st_size <= CLAUDE_MD_BUDGET


def test_readme_gives_the_install_command_and_the_whole_bundle_rule() -> None:
    text = README.read_text(encoding="utf-8")
    assert "/plugin install ai-sdlc@rafaelh" in text
    assert "gh skill install" in text
    assert "unsupported" in text.lower()


def test_readme_offers_review_repo_agents() -> None:
    assert "/plugin install review-repo-agents@rafaelh" in README.read_text(encoding="utf-8")


def test_claude_md_describes_the_bundle_and_the_specs_directory() -> None:
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert "ai-sdlc" in text
    assert "plugins/" in text
    assert "docs/specs/" in text


def test_docs_no_longer_mention_agent_tool_builder() -> None:
    for doc in (README, CLAUDE_MD):
        assert "agent-tool-builder" not in doc.read_text(encoding="utf-8"), doc.name


def test_claude_md_no_longer_claims_one_plugin_per_skill() -> None:
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert "each is a published plugin" not in text
    assert "Skills version independently" not in text
