# agent-tool: false
"""Shared helpers for the `az` skill's agent tools.

Importable by every script in this directory. Exit codes and stdout/stderr
discipline follow the agent-tool-builder contract:

Exit codes:
    0  success - data returned or operation completed
    1  user/invocation error - bad flag, validation failed, action needed by the user
    2  system/infrastructure error - `az` missing, unusable, or timed out
    3  not found - the command path is not recognised by the installed CLI

stdout: clean JSON envelope ({"data": ..., "meta": {...}}) or the text
rendering when --format text is passed.
stderr: informational logs (suppressed by --quiet) and structured error JSON.

Test seam: set AZ_CLI_BIN to point at a stub executable instead of the real
`az` binary. Every subprocess call in this suite routes through az_bin().
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Any, cast

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_SYSTEM_ERROR = 2
EXIT_NOT_FOUND = 3

# `az` help is rendered locally with no network round trip; anything slower
# than this means the CLI is wedged rather than busy.
HELP_TIMEOUT = 30
# ARM-backed calls (account, role assignments, groups) cross the network.
ARM_TIMEOUT = 60


class AzUnavailableError(RuntimeError):
    """The `az` binary is missing, not executable, or failed to start."""


class AgentToolParser(argparse.ArgumentParser):
    """ArgumentParser that emits structured errors and exits 1 (not 2).

    argparse's default error handler prints usage to stderr and exits 2,
    which conflicts with the contract: missing/bad args are user errors
    (exit 1); exit 2 is reserved for system/infrastructure failures.
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        code = "INVALID_ARG"
        hint = ""
        marker = "the following arguments are required:"
        if marker in message:
            code = "MISSING_ARG"
            hint = f"Pass {message.split(marker, 1)[1].strip()} on the command line"
        emit_error(message, code, hint=hint)
        sys.exit(EXIT_USER_ERROR)


def emit_error(error: str, code: str, hint: str = "", **extra: Any) -> None:
    """Write a structured error JSON line to stderr.

    Stdout is reserved for tool output; never write errors to stdout.
    """
    payload: dict[str, Any] = {"error": error, "code": code}
    if hint:
        payload["hint"] = hint
    payload.update(extra)
    print(json.dumps(payload), file=sys.stderr)


def emit_json(payload: dict[str, Any]) -> None:
    """Serialise the result envelope and write it to stdout."""
    print(json.dumps(payload))


def log(msg: str, *, quiet: bool = False) -> None:
    """Informational stderr message, suppressed when --quiet is set."""
    if not quiet:
        print(msg, file=sys.stderr)


def add_common_flags(parser: argparse.ArgumentParser) -> None:
    """Add --format and --quiet. Every script in this suite takes both."""
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
        help="Output format (default: json). text is the compact rendering and costs "
        "roughly a third fewer tokens; use it when reading output directly.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress informational stderr output. Errors still emit.",
    )


def az_bin() -> str:
    """Path to the Azure CLI executable, honouring the AZ_CLI_BIN test seam."""
    return os.environ.get("AZ_CLI_BIN") or "az"


def az_available() -> str | None:
    """Resolved path to `az`, or None when it is missing or not executable.

    `shutil.which` handles both forms az_bin() can take: a bare name is looked
    up on PATH, and a name containing a separator is checked in place.
    """
    return shutil.which(az_bin())


def run_az(
    args: list[str],
    *,
    timeout: int = HELP_TIMEOUT,
    only_show_errors: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Invoke `az` with the given arguments and capture both streams.

    Raises AzUnavailableError when the binary cannot be started or does not
    return within `timeout` seconds. Non-zero exits are returned to the caller
    to interpret, since `az` uses exit 1 for both "no such command" and
    "the service said no".
    """
    argv = [az_bin(), *args]
    if only_show_errors:
        argv.append("--only-show-errors")
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "AZURE_CORE_NO_COLOR": "true"},
        )
    except FileNotFoundError as exc:
        raise AzUnavailableError(f"`{az_bin()}` is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise AzUnavailableError(
            f"`{az_bin()} {' '.join(args)}` did not return within {timeout}s"
        ) from exc


def az_json(args: list[str], *, timeout: int = ARM_TIMEOUT) -> tuple[Any, str | None]:
    """Run `az ... -o json` and parse stdout.

    Returns (parsed, None) on success and (None, error_message) on any
    failure, so callers can degrade gracefully instead of aborting. Used for
    the optional parts of preflight where a permission denial is an expected,
    informative outcome rather than a fault.
    """
    result = run_az([*args, "-o", "json"], timeout=timeout, only_show_errors=True)
    if result.returncode != 0:
        return None, last_error_line(result.stderr or result.stdout)
    try:
        return json.loads(result.stdout or "null"), None
    except json.JSONDecodeError:
        return None, "az returned output that is not valid JSON"


def as_dict(value: Any) -> dict[str, Any]:
    """Coerce a parsed `az` payload to a dict; any other shape becomes empty.

    `az_json` returns whatever the CLI emitted, so every consumer would
    otherwise repeat the same isinstance dance to satisfy a strict checker.
    """
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    """Coerce a parsed `az` payload to a list; any other shape becomes empty."""
    return cast("list[Any]", value) if isinstance(value, list) else []


def last_error_line(stream: str) -> str:
    """Reduce an `az` stderr dump to its most specific line.

    `az` prefixes the real failure with deprecation warnings and follows it
    with a wrapped explanation; the ERROR line carries the code the agent
    needs (for example `(AuthorizationFailed)`).
    """
    lines = [ln.strip() for ln in stream.strip().splitlines() if ln.strip()]
    if not lines:
        return "az exited non-zero with no diagnostic output"
    for line in lines:
        if line.startswith("ERROR:"):
            return line.removeprefix("ERROR:").strip()
    return lines[-1]


INSTALL_HINTS = {
    "linux": "Arch: `sudo pacman -S azure-cli` · Debian/Ubuntu: "
    "`curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash` · "
    "RHEL/Fedora: `sudo dnf install azure-cli`",
    "darwin": "`brew install azure-cli`",
    "win32": "`winget install -e --id Microsoft.AzureCLI`",
}


def install_hint() -> str:
    """Platform-appropriate installation instruction for a missing `az`."""
    generic = "See https://learn.microsoft.com/cli/azure/install-azure-cli"
    return f"{INSTALL_HINTS.get(sys.platform, generic)} — {generic}"


class Timer:
    """Wall-clock stopwatch, started on construction, for the meta block."""

    def __init__(self) -> None:
        self.start = time.monotonic()

    @property
    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.start) * 1000)
