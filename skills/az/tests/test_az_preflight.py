"""Black-box subprocess tests for az-preflight.py.

Every test drives the real script through subprocess with AZ_CLI_BIN pointed
at the fake-az stub, so no Azure tenant, credentials, or network are involved.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

SKILL_DIR = Path(__file__).resolve().parents[1]
TOOL = SKILL_DIR / "scripts" / "az-preflight.py"
FIXTURES = Path(__file__).parent / "fixtures"
FAKE_AZ = FIXTURES / "fake-az"


def run_tool(
    *args: str, scenario: str | None = None, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AZ_FAKE_SCENARIO", None)
    env.pop("AZURE_CORE_OUTPUT", None)
    env.update(env_extra or {})
    if scenario is not None:
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


def test_reader_only_tenant_reports_read_only_posture():
    """Tracer bullet: a Reader-assigned principal orients without write access."""
    r = run_tool("--quiet", "--no-config", scenario="reader-only.json")
    assert r.returncode == 0, f"stderr: {r.stderr}\nstdout: {r.stdout}"
    data = json.loads(r.stdout)["data"]

    assert data["ready"] is True
    assert data["auth"]["logged_in"] is True
    assert data["auth"]["user"] == "auditor@contoso.com"
    assert data["auth"]["tenant_domain"] == "contoso.onmicrosoft.com"
    assert data["subscription"]["id"] == "sub-1"
    assert data["access"]["posture"] == "read-only"
    # Microsoft Graph was denied, so the assignee had to be resolved by name.
    assert data["access"]["graph_readable"] is False
    assert "guidance" in data["access"]
    assert data["resource_groups"] == ["rg-app", "rg-data"]
    assert data["resource_group_count"] == 2


def test_logged_out_exits_1_with_device_code_guidance_in_payload():
    """Not signed in is a user-action blocker, but the payload still lands."""
    r = run_tool("--quiet", "--no-config", scenario="logged-out.json")
    assert r.returncode == 1
    data = json.loads(r.stdout)["data"]

    assert data["ready"] is False
    assert data["auth"]["logged_in"] is False
    blocker = data["blockers"][0]
    assert blocker["code"] == "NOT_LOGGED_IN"
    assert "--use-device-code" in blocker["action"]
    assert data["cli"]["version"] == "2.87.0"


def test_denied_role_listing_falls_back_to_unknown_posture():
    """A tenant that blocks role reads must not be reported as write-capable."""
    r = run_tool("--quiet", "--no-config", scenario="unknown-access.json")
    assert r.returncode == 0, r.stderr
    access = json.loads(r.stdout)["data"]["access"]

    assert access["introspected"] is False
    assert access["posture"] == "unknown"
    assert "AuthorizationFailed" in access["reason"]
    assert "least privilege" in access["guidance"]


def test_missing_az_exits_2_with_install_hint():
    env = os.environ.copy()
    env["AZ_CLI_BIN"] = "/nonexistent/az"
    r = subprocess.run(
        [sys.executable, str(TOOL)], capture_output=True, text=True, env=env, check=False
    )
    assert r.returncode == 2
    assert r.stdout == ""
    error = json.loads(r.stderr)
    assert error["code"] == "AZ_NOT_INSTALLED"
    assert "install-azure-cli" in error["hint"]


def test_conflicting_flags_exit_1_with_structured_error():
    r = run_tool("--dry-run", "--no-config", scenario="reader-only.json")
    assert r.returncode == 1
    assert r.stdout == ""
    error = json.loads(r.stderr)
    assert error["code"] == "INVALID_ARG"


def test_dry_run_reports_config_without_writing_it():
    r = run_tool("--quiet", "--dry-run", scenario="reader-only.json")
    assert r.returncode == 0, r.stderr
    config = json.loads(r.stdout)["data"]["config"]

    assert config["dry_run"] is True
    assert config["applied"] == []
    assert "core.collect_telemetry=no" in config["would_apply"]
    # Extension dynamic-install keys are deliberately left alone: `az` already
    # prompts on a TTY and installs silently without one, so pinning them in the
    # user's global config would only remove the prompt from their own shell.
    assert not any("extension." in entry for entry in config["would_apply"])


def test_text_format_is_human_readable_not_json():
    r = run_tool("--quiet", "--no-config", "--format", "text", scenario="reader-only.json")
    assert r.returncode == 0, r.stderr
    assert "access posture: read-only" in r.stdout
    assert not r.stdout.startswith("{")


def test_json_shaped_output_default_is_reported_but_not_flagged():
    """A `jsonc` default is the user's colour preference and still parses."""
    r = run_tool("--quiet", "--dry-run", scenario="reader-only.json")
    assert r.returncode == 0, r.stderr
    output = json.loads(r.stdout)["data"]["config"]["output_default"]

    assert output["format"] == "jsonc"
    assert output["source"] == "core.output"
    assert output["json_shaped"] is True
    assert "guidance" not in output


def test_non_json_output_default_is_flagged_in_both_formats():
    """A `table` default silently reshapes every command that omits `-o`."""
    env_extra = {"AZURE_CORE_OUTPUT": "table"}
    r = run_tool("--quiet", "--dry-run", scenario="reader-only.json", env_extra=env_extra)
    assert r.returncode == 0, r.stderr
    output = json.loads(r.stdout)["data"]["config"]["output_default"]

    assert output["format"] == "table"
    # The env var wins over core.output, which the fixture sets to jsonc.
    assert output["source"] == "AZURE_CORE_OUTPUT"
    assert output["json_shaped"] is False
    assert "-o json" in output["guidance"]

    text = run_tool(
        "--quiet", "--dry-run", "--format", "text", scenario="reader-only.json", env_extra=env_extra
    )
    assert "default output is table" in text.stdout
