"""Black-box tests for the self-check (`.claude/skills/run-skills/smoke.py`).

Each test copies a small, clean target repo, breaks one thing, and runs the self-check against
the copy with `--repo`, asserting the exit code and which check failed.
"""

from __future__ import annotations

from collections.abc import Callable
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
SMOKE = REPO / ".claude" / "skills" / "run-skills" / "smoke.py"
TSX = REPO / "skills" / "skill-audit-ts" / "node_modules" / ".bin" / "tsx"

Mutation = Callable[[Path], None]

needs_claude = pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
needs_tsx = pytest.mark.skipif(not TSX.is_file(), reason="run `npm ci` in skills/skill-audit-ts")

BUNDLE = "plugins/ai-sdlc"
SPEC_DEFINE = f"{BUNDLE}/skills/spec-define/SKILL.md"
PLUGIN_JSON = f"{BUNDLE}/.claude-plugin/plugin.json"
MARKETPLACE = ".claude-plugin/marketplace.json"

# Near-identical descriptions would trip the overlap check, so each skill gets its own vocabulary.
DESCRIPTIONS = {
    "plan": "Interview the user about a design until every decision branch is resolved. Use when "
    "stress-testing a proposal.",
    "helper": "Greet visitors politely with a canned salutation. Use when a friendly hello is "
    "wanted.",
    "spec-define": "Write down the goal and desired behaviours of a change. Use before significant "
    "work begins.",
    "spec-design": "Interview the user to settle technical decisions for a written specification "
    "file. Use when choosing mechanisms.",
    "spec-develop": "Turn a settled specification file into tested code. Use once decisions are "
    "recorded.",
    "spec-verify": "Check that shipped code honours every behaviour in the specification file. Use "
    "after development finishes.",
}
HAND_OFFS = {
    "spec-define": "Next, run `/ai-sdlc:spec-design`. Launch the `critic-specification` agent "
    "first.",
    "spec-design": "Next, run `/ai-sdlc:spec-develop`. Launch `ai-sdlc:critic-architecture`.",
    "spec-develop": "Next, run `/ai-sdlc:spec-verify`.",
    "spec-verify": "Finish with `/simplify`, then `/code-review`, running `/clear` between them.",
}
AGENT = """---
name: {name}
description: >
  Reviews a draft and pushes back on weak parts, listing each gap it finds.
tools: Read, Glob, Grep, Bash
model: opus
color: red
---

You are a skeptical reviewer. Read the draft and list what is missing or untestable.

## Report

Return at most ten findings, most serious first.
"""


def _skill(name: str, body: str) -> str:
    return f"---\nname: {name}\ndescription: {DESCRIPTIONS[name]}\n---\n\n# {name}\n\n{body}\n"


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _manifest(name: str, version: str | None = None) -> str:
    data: dict[str, Any] = {
        "name": name,
        "description": f"The {name} fixture plugin",
        "author": {"name": "Test"},
    }
    if version:
        data["version"] = version
    return json.dumps(data, indent=2) + "\n"


def _git(repo: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        env=env,
        check=True,
        capture_output=True,
    )


def _build_repo(root: Path) -> None:
    entries = [
        {
            "name": name,
            "description": f"The {name} fixture plugin",
            "source": f"./{path}",
            "category": "development",
        }
        for name, path in (
            ("plan", "skills/plan"),
            ("helper", "skills/helper"),
            ("ai-sdlc", BUNDLE),
        )
    ]
    _write(
        root,
        MARKETPLACE,
        json.dumps({"name": "fixture", "owner": {"name": "T"}, "plugins": entries}),
    )
    _write(root, "skills/plan/SKILL.md", _skill("plan", "Ask one question at a time."))
    _write(root, "skills/plan/.claude-plugin/plugin.json", _manifest("plan", "0.1.0"))
    # Without a tool of each language, `--only python` / `--only ts` exit 3 (nothing to drive).
    _write(
        root,
        "skills/helper/SKILL.md",
        _skill("helper", "Run `scripts/noop.py` or `scripts/noop.ts` to say hello."),
    )
    _write(root, "skills/helper/.claude-plugin/plugin.json", _manifest("helper", "0.1.0"))
    _write(
        root,
        "skills/helper/scripts/noop.py",
        '"""Say hello."""\n\nimport argparse\n\n'
        'argparse.ArgumentParser(description="Say hello.").parse_args()\n',
    )
    _write(root, "skills/helper/scripts/noop.ts", 'console.log("usage: noop [--help]");\n')

    _write(root, PLUGIN_JSON, _manifest("ai-sdlc", "0.1.0"))
    for name, hand_off in HAND_OFFS.items():
        _write(root, f"{BUNDLE}/skills/{name}/SKILL.md", _skill(name, hand_off))
    for agent in ("critic-specification", "critic-architecture"):
        _write(root, f"{BUNDLE}/agents/{agent}.md", AGENT.format(name=agent))

    _git(root, "init", "-q")
    _commit(root, "fixture")


@pytest.fixture(scope="module")
def clean_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("fixture")
    _build_repo(root)
    return root


@pytest.fixture
def repo(clean_repo: Path, tmp_path: Path) -> Path:
    copy = tmp_path / "repo"
    shutil.copytree(clean_repo, copy, symlinks=True)
    return copy


def smoke(
    repo: Path,
    only: str | None,
    env: dict[str, str] | None = None,
    extra: tuple[str, ...] = (),
    timeout: float | None = None,
) -> tuple[int, dict[str, dict[str, Any]], str]:
    group = ("--only", only) if only else ()
    proc = subprocess.run(
        [sys.executable, str(SMOKE), "--repo", str(repo), *group, "--json", "--quiet", *extra],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=timeout,
    )
    payload: dict[str, Any] = json.loads(proc.stdout) if proc.stdout.strip() else {"checks": []}
    checks: list[dict[str, Any]] = payload["checks"]
    return proc.returncode, {c["check"]: c for c in checks}, proc.stderr


def failed(checks: dict[str, dict[str, Any]]) -> set[str]:
    return {name for name, c in checks.items() if not c["ok"]}


def assert_fails(repo: Path, only: str, check: str) -> None:
    code, checks, stderr = smoke(repo, only)
    assert "Traceback" not in stderr
    assert code == 1, (code, checks)
    assert any(name == check or name.startswith(check + "/") for name in failed(checks)), (
        check,
        failed(checks),
    )


def assert_passes(repo: Path, only: str, check: str) -> None:
    _, checks, _ = smoke(repo, only)
    assert checks[check]["ok"], checks[check]["detail"]


def edit(repo: Path, rel: str, old: str, new: str) -> None:
    path = repo / rel
    text = path.read_text(encoding="utf-8")
    assert old in text, (rel, old)
    path.write_text(text.replace(old, new), encoding="utf-8")


def append(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


# --- the clean fixture passes every group -------------------------------------------------


@pytest.mark.parametrize(
    "group",
    [
        "python",
        pytest.param("ts", marks=needs_tsx),
        pytest.param("parity", marks=needs_tsx),
        "manifests",
        pytest.param("bundle", marks=needs_claude),
    ],
)
def test_clean_fixture_passes(repo: Path, group: str) -> None:
    code, checks, _ = smoke(repo, group)
    assert checks, "group produced no checks"
    assert failed(checks) == set()
    assert code == 0
    # Each bundle skill is named individually, not folded into one bundle-level check.
    prefix = {"python": "python/self-audit/ai-sdlc/", "parity": "parity/ai-sdlc/"}.get(group)
    if prefix:
        assert {f"{prefix}{skill}" for skill in HAND_OFFS} <= set(checks)


# --- bundle skills are held to the same validators as every skill -------------------------


def _name_mismatch(r: Path) -> None:
    edit(r, SPEC_DEFINE, "name: spec-define", "name: spec-defin")


def _malformed_frontmatter(r: Path) -> None:
    _write(r, SPEC_DEFINE, "---\nname: spec-define\ndescription: [unclosed\n")


def _dangling_reference(r: Path) -> None:
    append(r, SPEC_DEFINE, "\nSee [more](references/missing.md).\n")


@pytest.mark.parametrize(
    "mutate",
    [_name_mismatch, _malformed_frontmatter, _dangling_reference],
    ids=["name-mismatch", "malformed-frontmatter", "dangling-reference"],
)
def test_broken_bundle_skill_fails_the_python_validator(repo: Path, mutate: Mutation) -> None:
    mutate(repo)
    assert_fails(repo, "python", "python/self-audit/ai-sdlc/spec-define")


# --- bundle/refs: agents and slash commands the skills name -------------------------------


@needs_claude
@pytest.mark.parametrize(
    "text",
    [
        "Launch `ai-sdlc:critic-nope`.",
        "Launch the `critic-nope` agent.",
        "Launch `other-plugin:agent`.",
        "Next, run `/ai-sdlc:spec-nope`.",
        "Next, run `/foo`.",
    ],
)
def test_unresolvable_reference_fails(repo: Path, text: str) -> None:
    append(repo, SPEC_DEFINE, f"\n{text}\n")
    assert_fails(repo, "bundle", "bundle/ai-sdlc/refs")


@needs_claude
def test_resolvable_references_pass(repo: Path) -> None:
    append(
        repo,
        SPEC_DEFINE,
        "\nRun `/simplify`, `/clear` and `/code-review`.\n"
        "Look in `/home/x` for the file.\n"
        "Launch the `critic-architecture` agent.\n"
        "Launch `ai-sdlc:critic-specification`.\n"
        "Next, run `/ai-sdlc:spec-verify`.\n",
    )
    assert_passes(repo, "bundle", "bundle/ai-sdlc/refs")


# --- bundle/contents: the directory is the listing ----------------------------------------


def _stray_commands(r: Path) -> None:
    _write(r, f"{BUNDLE}/commands/x.md", "# x\n")


def _empty_skill_dir(r: Path) -> None:
    (r / BUNDLE / "skills" / "foo").mkdir()


def _agents_key_in_plugin_json(r: Path) -> None:
    edit(r, PLUGIN_JSON, '"version"', '"agents": "./agents",\n  "version"')


def _component_key_in_marketplace(r: Path) -> None:
    edit(
        r,
        MARKETPLACE,
        '"source": "./plugins/ai-sdlc"',
        '"source": "./plugins/ai-sdlc", "skills": []',
    )


@needs_claude
@pytest.mark.parametrize(
    "mutate",
    [_stray_commands, _empty_skill_dir, _agents_key_in_plugin_json, _component_key_in_marketplace],
    ids=["stray-commands", "empty-skill-dir", "agents-key", "marketplace-component-key"],
)
def test_bundle_with_anything_but_skills_and_agents_fails(repo: Path, mutate: Mutation) -> None:
    mutate(repo)
    assert_fails(repo, "bundle", "bundle/ai-sdlc/contents")


# --- bundle/agents ------------------------------------------------------------------------


@needs_claude
@pytest.mark.parametrize(
    "content",
    [
        "---\nname: critic-specification\ndescription: [unclosed\n",
        AGENT.format(name="x").replace("name: x\n", ""),
    ],
    ids=["malformed-frontmatter", "no-name"],
)
def test_bad_critic_definition_fails(repo: Path, content: str) -> None:
    _write(repo, f"{BUNDLE}/agents/critic-specification.md", content)
    assert_fails(repo, "bundle", "bundle/ai-sdlc/agents")


# --- bundle/overlap -----------------------------------------------------------------------


@needs_claude
def test_bundle_skill_overlapping_a_sibling_fails(repo: Path) -> None:
    edit(repo, SPEC_DEFINE, DESCRIPTIONS["spec-define"], DESCRIPTIONS["plan"])
    assert_fails(repo, "bundle", "bundle/ai-sdlc/overlap")


@needs_claude
def test_bundle_skill_name_clashing_with_a_published_skill_fails(repo: Path) -> None:
    clash = repo / BUNDLE / "skills" / "plan"
    shutil.copytree(repo / "skills" / "plan", clash)
    assert_fails(repo, "bundle", "bundle/ai-sdlc/overlap")


# --- manifests ----------------------------------------------------------------------------


def _rename_entry(r: Path) -> None:
    edit(r, MARKETPLACE, '"name": "ai-sdlc"', '"name": "ai-sdlc-x"')


def _unlisted_plugin(r: Path) -> None:
    _write(r, "plugins/x/.claude-plugin/plugin.json", _manifest("x", "0.1.0"))


def _missing_source(r: Path) -> None:
    edit(r, MARKETPLACE, '"./plugins/ai-sdlc"', '"./plugins/gone"')


def _unlisted_skill(r: Path) -> None:
    _write(r, "skills/other/SKILL.md", _skill("helper", "x"))


def _skill_renamed_in_both_manifests(r: Path) -> None:
    edit(r, "skills/plan/.claude-plugin/plugin.json", '"name": "plan"', '"name": "bar"')
    edit(r, MARKETPLACE, '"name": "plan"', '"name": "bar"')


@pytest.mark.parametrize(
    "mutate",
    [
        _rename_entry,
        _unlisted_plugin,
        _missing_source,
        _unlisted_skill,
        _skill_renamed_in_both_manifests,
    ],
    ids=["name-mismatch", "unlisted-plugin", "missing-source", "unlisted-skill", "dir-mismatch"],
)
def test_marketplace_disagreeing_with_disk_fails(repo: Path, mutate: Mutation) -> None:
    mutate(repo)
    assert_fails(repo, "manifests", "manifests")


# --- bundle/version: content changes ship with a higher version ---------------------------


def _bump(repo: Path, version: str) -> None:
    manifest = repo / PLUGIN_JSON
    data = json.loads(manifest.read_text(encoding="utf-8"))
    edit(repo, PLUGIN_JSON, f'"version": "{data["version"]}"', f'"version": "{version}"')


def _commit(repo: Path, message: str = "change") -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _new_agent(repo: Path) -> None:
    _write(repo, f"{BUNDLE}/agents/critic-new.md", AGENT.format(name="critic-new"))


@needs_claude
def test_committed_skill_edit_without_bump_fails(repo: Path) -> None:
    append(repo, SPEC_DEFINE, "\nAn extra sentence.\n")
    _commit(repo)
    assert_fails(repo, "bundle", "bundle/ai-sdlc/version")


@needs_claude
def test_uncommitted_skill_edit_without_bump_fails(repo: Path) -> None:
    append(repo, SPEC_DEFINE, "\nAn extra sentence.\n")
    assert_fails(repo, "bundle", "bundle/ai-sdlc/version")


@needs_claude
def test_untracked_agent_without_bump_fails(repo: Path) -> None:
    _new_agent(repo)
    assert_fails(repo, "bundle", "bundle/ai-sdlc/version")


@needs_claude
def test_uncommitted_bump_passes(repo: Path) -> None:
    append(repo, SPEC_DEFINE, "\nAn extra sentence.\n")
    _new_agent(repo)
    _bump(repo, "0.2.0")
    assert_passes(repo, "bundle", "bundle/ai-sdlc/version")


@needs_claude
def test_committed_bump_passes(repo: Path) -> None:
    append(repo, SPEC_DEFINE, "\nAn extra sentence.\n")
    _bump(repo, "0.2.0")
    _commit(repo)
    assert_passes(repo, "bundle", "bundle/ai-sdlc/version")


@needs_claude
def test_edit_after_a_committed_bump_fails(repo: Path) -> None:
    _bump(repo, "0.2.0")
    _commit(repo)
    append(repo, SPEC_DEFINE, "\nAn extra sentence.\n")
    assert_fails(repo, "bundle", "bundle/ai-sdlc/version")


@needs_claude
def test_lowered_version_fails(repo: Path) -> None:
    _bump(repo, "0.0.9")
    assert_fails(repo, "bundle", "bundle/ai-sdlc/version")


@needs_claude
def test_committed_lowered_version_fails(repo: Path) -> None:
    _bump(repo, "0.2.0")
    _commit(repo)
    _bump(repo, "0.1.5")
    _commit(repo)
    assert_fails(repo, "bundle", "bundle/ai-sdlc/version")


@needs_claude
def test_bundle_not_yet_committed_passes_the_version_check(repo: Path) -> None:
    _git(repo, "rm", "-rq", "--cached", BUNDLE)
    _git(repo, "commit", "-q", "-m", "untrack bundle")
    append(repo, SPEC_DEFINE, "\nAn extra sentence.\n")
    assert_passes(repo, "bundle", "bundle/ai-sdlc/version")


@needs_claude
def test_unresolvable_history_fails_with_a_detail_not_a_traceback(repo: Path) -> None:
    shutil.rmtree(repo / ".git")
    assert_fails(repo, "bundle", "bundle/ai-sdlc/version")


@needs_claude
def test_shallow_clone_cut_before_the_version_change_fails(repo: Path, tmp_path: Path) -> None:
    append(repo, SPEC_DEFINE, "\nAn extra sentence.\n")
    _commit(repo)
    clone = tmp_path / "shallow"
    # A plain local path ignores --depth; only a file:// URL makes the clone shallow.
    _git(tmp_path, "clone", "-q", "--depth", "1", repo.as_uri(), str(clone))
    assert_fails(clone, "bundle", "bundle/ai-sdlc/version")
    _, checks, _ = smoke(clone, "bundle")
    assert "shallow" in checks["bundle/ai-sdlc/version"]["detail"]


@needs_claude
def test_shallow_clone_holding_the_version_change_still_checks(repo: Path, tmp_path: Path) -> None:
    append(repo, "skills/plan/SKILL.md", "\nUnrelated.\n")
    _commit(repo, "becomes the shallow boundary")
    _bump(repo, "0.2.0")
    _commit(repo, "bump")
    append(repo, SPEC_DEFINE, "\nAn extra sentence.\n")
    _commit(repo)
    clone = tmp_path / "shallow"
    _git(tmp_path, "clone", "-q", "--depth", "3", repo.as_uri(), str(clone))
    assert (clone / ".git" / "shallow").is_file()
    _, checks, _ = smoke(clone, "bundle")
    detail = checks["bundle/ai-sdlc/version"]["detail"]
    assert "changed since the version last changed" in detail, detail


# --- malformed JSON fails a check, never the whole sweep ----------------------------------


@pytest.mark.parametrize("group", ["manifests", pytest.param("bundle", marks=needs_claude)])
def test_plugin_json_that_is_not_an_object_fails(repo: Path, group: str) -> None:
    _write(repo, PLUGIN_JSON, "[]\n")
    assert_fails(repo, group, group)


@needs_claude
def test_plugin_json_deleted_but_still_committed_fails(repo: Path) -> None:
    (repo / PLUGIN_JSON).unlink()
    assert_fails(repo, "bundle", "bundle/ai-sdlc/version")


def test_marketplace_that_is_not_an_object_fails(repo: Path) -> None:
    _write(repo, MARKETPLACE, "[]\n")
    assert_fails(repo, "manifests", "manifests/marketplace")


# --- toolchain gating ---------------------------------------------------------------------


def _path_with_only(tmp_path: Path, *tools: str) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in tools:
        found = shutil.which(tool)
        assert found, tool
        (bin_dir / tool).symlink_to(found)
    return {**os.environ, "PATH": str(bin_dir)}


def test_manifests_group_does_not_need_claude_or_node(repo: Path, tmp_path: Path) -> None:
    code, checks, _ = smoke(repo, "manifests", env=_path_with_only(tmp_path, "uv"))
    assert code == 0, checks
    assert not any(name.startswith("toolchain/") and name != "toolchain/uv" for name in checks)


def test_bundle_group_without_claude_is_a_toolchain_error(repo: Path, tmp_path: Path) -> None:
    code, checks, _ = smoke(repo, "bundle", env=_path_with_only(tmp_path, "uv", "git"))
    assert code == 2
    assert "toolchain/claude" in failed(checks)


def _drop_bundle(repo: Path) -> None:
    shutil.rmtree(repo / "plugins")
    data = json.loads((repo / MARKETPLACE).read_text(encoding="utf-8"))
    data["plugins"] = [p for p in data["plugins"] if p["name"] != "ai-sdlc"]
    _write(repo, MARKETPLACE, json.dumps(data))


@needs_tsx
def test_full_sweep_without_bundles_does_not_need_claude(repo: Path, tmp_path: Path) -> None:
    _drop_bundle(repo)
    code, checks, stderr = smoke(repo, None, env=_path_with_only(tmp_path, "uv", "node"))
    assert "Traceback" not in stderr
    assert code != 2, failed(checks)
    assert "toolchain/claude" not in checks
    assert "toolchain/git" not in checks


def test_tests_flag_without_node_is_a_toolchain_error(repo: Path, tmp_path: Path) -> None:
    # If the gate regressed, --tests would re-run this whole suite; the timeout caps that.
    code, checks, stderr = smoke(
        repo, "manifests", env=_path_with_only(tmp_path, "uv"), extra=("--tests",), timeout=60
    )
    assert "Traceback" not in stderr
    assert code == 2, checks
    assert "toolchain/node" in failed(checks)
