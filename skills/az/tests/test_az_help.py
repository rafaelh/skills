"""Black-box subprocess tests for az-help.py.

The help fixtures are verbatim output captured from a real `az` install, so
the parser is exercised against the CLI's actual wrapping and column layout
without the tests depending on which az version happens to be installed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

SKILL_DIR = Path(__file__).resolve().parents[1]
TOOL = SKILL_DIR / "scripts" / "az-help.py"
FIXTURES = Path(__file__).parent / "fixtures"
FAKE_AZ = FIXTURES / "fake-az"


def run_tool(*args: str, scenario: str = "help.json") -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AZ_CLI_BIN"] = str(FAKE_AZ)
    env["AZ_FAKE_SCENARIO"] = str(FIXTURES / scenario)
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=SKILL_DIR,
        check=False,
    )


def test_leaf_help_separates_required_from_optional_arguments():
    """Tracer bullet: the compact rendering keeps what an agent needs to build a call."""
    r = run_tool("--quiet", "sql", "db", "create")
    assert r.returncode == 0, f"stderr: {r.stderr}\nstdout: {r.stdout}"
    payload = json.loads(r.stdout)
    data = payload["data"]

    assert data["kind"] == "command"
    assert data["command"] == "az sql db create"
    assert data["summary"].startswith("Create a database.")

    required = {" ".join(a["flags"]) for a in data["required"]}
    assert required == {"--name -n", "--resource-group -g", "--server -s"}
    assert all("description" in a for a in data["required"])

    optional = {a["flags"][0] for a in data["optional"]}
    assert "--edition" in optional
    assert "--no-wait" in optional
    # Global arguments are dropped in compact mode - that is the token saving.
    assert "--query" not in optional
    assert "--subscription" not in optional
    assert payload["meta"]["required_count"] == 3


def test_enumerated_values_are_preserved_but_descriptions_are_not():
    r = run_tool("--quiet", "sql", "db", "create")
    optional = {a["flags"][0]: a for a in json.loads(r.stdout)["data"]["optional"]}

    assert optional["--compute-model"]["allowed"] == ["Provisioned", "Serverless"]
    assert "description" not in optional["--compute-model"]
    assert "description" not in optional["--no-wait"]


def test_full_mode_restores_descriptions_and_global_arguments():
    r = run_tool("--quiet", "--full", "sql", "db", "create")
    assert r.returncode == 0, r.stderr
    optional = {a["flags"][0]: a for a in json.loads(r.stdout)["data"]["optional"]}

    assert "--query" in optional
    assert optional["--compute-model"]["description"]


def test_hard_wrapped_examples_are_rejoined_without_corrupting_flags():
    """`az` wraps mid-flag; naive whitespace joining would emit `--compute- model`."""
    r = run_tool("--quiet", "sql", "db", "create")
    examples = json.loads(r.stdout)["data"]["examples"]

    assert any("--compute-model Serverless" in ex for ex in examples)
    assert any("--backup-storage-redundancy Local" in ex for ex in examples)
    assert not any("- " in ex.replace("-- ", "") and "compute- model" in ex for ex in examples)


def test_group_help_lists_subgroups_with_preview_status():
    r = run_tool("--quiet", "sql")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)["data"]

    assert data["kind"] == "group"
    subgroups = {s["name"]: s for s in data["subgroups"]}
    assert subgroups["db"]["summary"] == "Manage databases."
    assert subgroups["db"]["status"] is None
    # A status tag is padded away from the name; it must not bleed into the summary.
    assert subgroups["stg"]["status"] == "Preview"
    assert subgroups["server"]["summary"] == "Manage SQL servers."
    assert {c["name"] for c in data["commands"]} == {"list-usages", "show-usage"}


def test_tree_descends_through_every_level():
    r = run_tool("--quiet", "--tree", "demo")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)

    commands = [row["command"] for row in payload["data"]]
    assert commands == ["az demo net dns resolve", "az demo net ping", "az demo status"]
    assert payload["meta"]["count"] == 3


def test_tree_respects_max_depth():
    r = run_tool("--quiet", "--tree", "demo", "--max-depth", "1")
    commands = [row["command"] for row in json.loads(r.stdout)["data"]]

    assert "az demo net ping" in commands
    assert "az demo net dns resolve" not in commands


def test_tree_match_filters_and_reports_totals():
    r = run_tool("--quiet", "--tree", "demo", "--match", "dns|ping")
    payload = json.loads(r.stdout)

    assert payload["meta"]["matched"] == 2
    assert payload["meta"]["total"] == 3
    assert payload["meta"]["truncated"] is False


def test_tree_limit_marks_result_truncated():
    r = run_tool("--quiet", "--tree", "demo", "--limit", "1")
    payload = json.loads(r.stdout)

    assert payload["meta"]["count"] == 1
    assert payload["meta"]["truncated"] is True


def test_tree_match_with_no_hits_exits_3():
    r = run_tool("--quiet", "--tree", "demo", "--match", "nothing-matches-this")
    assert r.returncode == 3
    assert r.stdout == ""
    assert json.loads(r.stderr)["code"] == "NOT_FOUND"


def test_unrecognised_command_exits_3_with_parent_group_hint():
    r = run_tool("--quiet", "sql", "db", "frobnicate")
    assert r.returncode == 3
    assert r.stdout == ""
    error = json.loads(r.stderr)
    assert error["code"] == "NOT_FOUND"
    assert "misspelled" in error["error"]
    assert "az-help.py sql db" in error["hint"]


def test_leading_az_in_path_exits_1():
    r = run_tool("--quiet", "az", "sql")
    assert r.returncode == 1
    assert json.loads(r.stderr)["code"] == "INVALID_ARG"


def test_match_without_tree_exits_1():
    r = run_tool("--quiet", "--match", "foo", "sql")
    assert r.returncode == 1
    assert json.loads(r.stderr)["code"] == "INVALID_ARG"


def test_tree_without_group_exits_1():
    r = run_tool("--quiet", "--tree")
    assert r.returncode == 1
    assert json.loads(r.stderr)["code"] == "MISSING_ARG"


def test_invalid_match_regex_exits_1():
    r = run_tool("--quiet", "--tree", "demo", "--match", "[unclosed")
    assert r.returncode == 1
    assert json.loads(r.stderr)["code"] == "INVALID_ARG"


def test_missing_az_exits_2():
    env = os.environ.copy()
    env["AZ_CLI_BIN"] = "/nonexistent/az"
    r = subprocess.run(
        [sys.executable, str(TOOL), "sql"], capture_output=True, text=True, env=env, check=False
    )
    assert r.returncode == 2
    assert r.stdout == ""
    assert json.loads(r.stderr)["code"] == "AZ_UNAVAILABLE"


def test_tree_with_missing_az_exits_2_not_3():
    """A missing CLI is a system fault, not an empty group — the codes must not blur."""
    env = os.environ.copy()
    env["AZ_CLI_BIN"] = "/nonexistent/az"
    r = subprocess.run(
        [sys.executable, str(TOOL), "--quiet", "--tree", "sql"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert r.returncode == 2
    assert r.stdout == ""
    assert json.loads(r.stderr)["code"] == "AZ_UNAVAILABLE"


def test_text_format_is_smaller_than_raw_help():
    """The entire point of the tool: compact output beats piping `az -h` around."""
    r = run_tool("--quiet", "--format", "text", "sql", "db", "create")
    assert r.returncode == 0, r.stderr

    raw = json.loads((FIXTURES / "help.json").read_text())[0]["stdout"]
    assert len(r.stdout) < len(raw) / 5
    assert r.stdout.startswith("az sql db create —")
    assert "REQUIRED" in r.stdout
