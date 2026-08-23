#!/usr/bin/env python3
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Single-call orientation for an Azure session.

Answers, in one invocation and roughly two seconds, everything an agent needs
before it runs its first real `az` command: is the CLI installed, is anyone
logged in, which subscription and tenant is active, which other subscriptions
are reachable, what the signed-in principal is actually allowed to do, and
which resource groups exist.

It also disables `az` telemetry and the periodic survey banner. Those two keys
are written to the user's global `~/.azure/config` and persist beyond this
session, so `--no-config` and `--dry-run` exist to opt out or preview.

Deliberately NOT set: `extension.use_dynamic_install` and
`extension.dynamic_install_allow_preview`. `az` already picks the right value
per context - it prompts on a TTY and installs silently without one - so
pinning them globally would only remove the prompt the user gets in their own
interactive shell, and would buy an agent nothing.

When something is wrong the guidance travels in the payload — install command,
device-code login instruction, wrong-cloud fix — so the skill itself carries
none of it and the agent does not spend a turn asking.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import os
import sys
from typing import Any

from _common import (
    ARM_TIMEOUT,
    EXIT_OK,
    EXIT_SYSTEM_ERROR,
    EXIT_USER_ERROR,
    AgentToolParser,
    AzUnavailableError,
    Timer,
    add_common_flags,
    as_dict,
    as_list,
    az_available,
    az_json,
    emit_error,
    emit_json,
    install_hint,
    log,
    run_az,
)

# Applied unless --no-config. These are written to the user's global
# ~/.azure/config and outlive the session, so the list is kept to settings a
# user would want off everywhere rather than agent-only conveniences.
MANAGED_CONFIG: dict[str, str] = {
    "core.survey_message": "no",
    "core.collect_telemetry": "no",
}

# Role names are free text, so classify on substrings rather than an
# enumeration. Anything unrecognised falls through to "unknown", which the
# skill treats as least-privilege.
WRITE_ROLE_TOKENS = (
    "owner",
    "contributor",
    "administrator",
    "admin",
    "operator",
    "officer",
    "writer",
    "manager",
    "publisher",
)
READ_ROLE_TOKENS = ("reader", "viewer", "read")

DEFAULT_MAX_GROUPS = 60


def read_config() -> dict[str, str]:
    """Current `az config` as a flat section.key -> value mapping."""
    parsed, _ = az_json(["config", "get"], timeout=ARM_TIMEOUT)
    return {
        f"{section}.{entry['name']}": str(entry["value"])
        for section, entries in as_dict(parsed).items()
        for entry in (as_dict(e) for e in as_list(entries))
        if "name" in entry
    }


def effective_output(config: dict[str, str]) -> dict[str, Any]:
    """The format `az` returns when a command omits `-o`.

    `--output` defaults to json only until the user sets `core.output` or
    AZURE_CORE_OUTPUT; a `table` or `yaml` default silently changes the shape of
    every unqualified command. That default is the user's own preference for
    their interactive shell, so it is reported rather than overwritten - the fix
    belongs on the agent's side, as an explicit `-o` per command.
    """
    env = os.environ.get("AZURE_CORE_OUTPUT")
    configured = config.get("core.output")
    value = env or configured or "json"
    source = "AZURE_CORE_OUTPUT" if env else "core.output" if configured else "az default"
    payload: dict[str, Any] = {
        "format": value,
        "source": source,
        # jsonc is json plus colour, and az drops the colour when stdout is not
        # a terminal, so an agent can parse it exactly like json.
        "json_shaped": value in {"json", "jsonc"},
    }
    if not payload["json_shaped"]:
        payload["guidance"] = (
            f"Commands that omit `-o` return {value}, not JSON. Pass `-o json` or `-o tsv` "
            "explicitly on any command whose output you read, and leave the user's default alone."
        )
    return payload


def apply_config(*, dry_run: bool, quiet: bool) -> dict[str, Any]:
    """Set the managed keys that are missing or wrong, and report what changed."""
    current = read_config()
    pending = {k: v for k, v in MANAGED_CONFIG.items() if current.get(k) != v}
    settings = [f"{k}={v}" for k, v in pending.items()]
    payload: dict[str, Any] = {
        "applied": [],
        "already_set": sorted(set(MANAGED_CONFIG) - set(pending)),
        "dry_run": dry_run,
        "output_default": effective_output(current),
    }
    if not pending:
        return payload
    if dry_run:
        payload["would_apply"] = settings
        return payload

    log(f"setting {len(pending)} az config key(s)", quiet=quiet)
    result = run_az(["config", "set", *settings], timeout=ARM_TIMEOUT, only_show_errors=True)
    if result.returncode == 0:
        payload["applied"] = settings
    else:
        payload["failed"] = f"{[*pending]} could not be set"
    return payload


def cli_info() -> dict[str, Any]:
    """Installed CLI version and extension inventory (local, no network)."""
    parsed, error = az_json(["version"], timeout=ARM_TIMEOUT)
    if not isinstance(parsed, dict):
        return {"installed": True, "path": az_available(), "version": None, "error": error}
    version = as_dict(parsed)
    return {
        "installed": True,
        "path": az_available(),
        "version": version.get("azure-cli"),
        "extensions": version.get("extensions") or {},
    }


def signed_in_object_id() -> str | None:
    """Object ID of the signed-in user, or None when Microsoft Graph is denied."""
    parsed, _ = az_json(["ad", "signed-in-user", "show", "--query", "id"])
    return parsed if isinstance(parsed, str) else None


def classify(roles: list[str]) -> str:
    """Reduce assigned role names to write / read-only / unknown."""
    if not roles:
        return "unknown"
    lowered = [r.lower() for r in roles]
    if any(any(token in role for token in WRITE_ROLE_TOKENS) for role in lowered):
        return "write"
    if all(any(token in role for token in READ_ROLE_TOKENS) for role in lowered):
        return "read-only"
    return "unknown"


def access_info(account: dict[str, Any]) -> dict[str, Any]:
    """What the signed-in principal can do in the active subscription.

    The assignee is resolved through Microsoft Graph first, because an object
    ID also picks up group-inherited assignments; a tenant that denies
    directory reads falls back to matching by name. A failure here is
    informative, not fatal: `unknown` tells the skill to assume least privilege.
    """
    user: dict[str, Any] = account.get("user") or {}
    query = ["role", "assignment", "list", "--all", "--include-inherited"]
    object_id = signed_in_object_id() if user.get("type") == "user" else None
    if object_id:
        query += ["--assignee-object-id", object_id, "--include-groups"]
    elif user.get("name"):
        query += ["--assignee", str(user["name"])]

    parsed, error = az_json([*query, "--query", "[].{role:roleDefinitionName,scope:scope}"])
    if not isinstance(parsed, list):
        return {
            "introspected": False,
            "posture": "unknown",
            "assignments": [],
            "reason": error or "role assignments could not be listed",
            "guidance": "Assume least privilege: propose write commands to the user "
            "rather than running them.",
        }
    assignments = [as_dict(a) for a in as_list(parsed) if isinstance(a, dict)]
    posture = classify([str(a.get("role", "")) for a in assignments])
    payload: dict[str, Any] = {
        "introspected": True,
        "posture": posture,
        "assignments": assignments,
        "graph_readable": object_id is not None,
    }
    if posture != "write":
        payload["guidance"] = (
            "No write-capable role was found in this subscription. Expect "
            "(AuthorizationFailed) on create/update/delete; confirm with the user "
            "before attempting one."
        )
    return payload


def subscriptions_info() -> tuple[list[dict[str, Any]], str | None]:
    parsed, error = az_json(
        ["account", "list", "--query", "[].{id:id,name:name,isDefault:isDefault,state:state}"]
    )
    return as_list(parsed), error


def groups_info(limit: int) -> tuple[list[str], int, str | None]:
    parsed, error = az_json(["group", "list", "--query", "[].name"])
    if not isinstance(parsed, list):
        return [], 0, error
    names = sorted(str(n) for n in as_list(parsed))
    return names[:limit], len(names), None


def ensure_extensions(names: list[str], quiet: bool) -> list[dict[str, Any]]:
    """Install the named extensions up front so later commands do not stall."""
    results: list[dict[str, Any]] = []
    for name in names:
        log(f"ensuring extension {name} ...", quiet=quiet)
        result = run_az(
            ["extension", "add", "--name", name, "--upgrade"], timeout=300, only_show_errors=True
        )
        results.append({"name": name, "ok": result.returncode == 0})
    return results


def survey_tenant(account: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Run the independent ARM reads together and return the keys they fill.

    Sibling subscriptions, access posture, and resource groups do not depend on
    each other, so the slowest of the three sets the wall-clock cost rather
    than their sum.
    """
    found: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        subs_future = pool.submit(subscriptions_info)
        access_future = None if args.skip_access else pool.submit(access_info, account)
        groups_future = None if args.skip_groups else pool.submit(groups_info, args.max_groups)
        found["other_subscriptions"], subs_error = subs_future.result()
        if access_future is not None:
            found["access"] = access_future.result()
        if groups_future is not None:
            names, total, groups_error = groups_future.result()
            found["resource_groups"] = names
            found["resource_group_count"] = total
            if groups_error:
                found["resource_groups_error"] = groups_error
    if subs_error:
        found["other_subscriptions_error"] = subs_error
    return found


def render_text(data: dict[str, Any]) -> str:
    lines: list[str] = []
    cli, auth, sub, access = data["cli"], data["auth"], data["subscription"], data["access"]
    lines.append(f"az {cli.get('version') or '?'} at {cli.get('path')}")
    exts = as_dict(cli.get("extensions"))
    lines.append(f"extensions: {', '.join(sorted(exts)) if exts else '(none)'}")
    output = as_dict(as_dict(data["config"]).get("output_default"))
    if output and not output.get("json_shaped"):
        lines.append(
            f"default output is {output['format']} ({output['source']})"
            " - pass -o explicitly on reads"
        )
    if auth["logged_in"]:
        lines.append(f"signed in as {auth['user']} ({auth['user_type']}) in {auth['cloud']}")
        lines.append(f"tenant: {auth['tenant_domain'] or auth['tenant_id']}")
        lines.append(f"subscription: {sub['name']} ({sub['id']})")
        others = data["other_subscriptions"]
        if len(others) > 1:
            lines.append(f"{len(others)} subscriptions reachable — pass --subscription explicitly")
        lines.append(f"access posture: {access['posture']}")
        lines.extend(f"  {a.get('role')} @ {a.get('scope')}" for a in access["assignments"][:10])
        groups = data["resource_groups"]
        listed = ", ".join(groups) if groups else "none visible"
        lines.append(f"resource groups ({data['resource_group_count']}): {listed}")
    lines.extend(f"BLOCKER {b['code']}: {b['message']} -> {b['action']}" for b in data["blockers"])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = AgentToolParser(
        prog="az-preflight.py",
        description="One-call orientation for an Azure session.",
        epilog="""Examples:
  az-preflight.py                          full orientation, applies managed az config
  az-preflight.py --format text --quiet    compact summary, no progress logging
  az-preflight.py --dry-run                report config changes without writing them
  az-preflight.py --no-config              never touch ~/.azure/config (it is global
                                           and persists after this session)
  az-preflight.py --skip-access --skip-groups   fastest possible check (~0.5s)
  az-preflight.py --ensure-ext resource-graph,application-insights,log-analytics

Exit codes: 0 ready · 1 user action needed (not logged in / no subscription) —
the payload is still written to stdout · 2 `az` missing or unusable.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--no-config", action="store_true", help="Do not read or write ~/.azure/config."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report which config keys would be set, without setting them. "
        "Still performs the read-only Azure lookups.",
    )
    parser.add_argument(
        "--skip-access",
        action="store_true",
        help="Skip role-assignment lookup (saves ~1.5s, loses access posture).",
    )
    parser.add_argument(
        "--skip-groups", action="store_true", help="Skip the resource-group listing (saves ~1s)."
    )
    parser.add_argument(
        "--ensure-ext",
        help="Comma-separated extensions to install before returning. Requires network access.",
    )
    parser.add_argument(
        "--max-groups",
        type=int,
        default=DEFAULT_MAX_GROUPS,
        help=f"Cap resource-group names returned (default: {DEFAULT_MAX_GROUPS}).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=ARM_TIMEOUT,
        help=f"Per-call timeout in seconds (default: {ARM_TIMEOUT}).",
    )
    add_common_flags(parser)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.max_groups < 1:
        emit_error("--max-groups must be 1 or greater", "INVALID_ARG", input=str(args.max_groups))
        return EXIT_USER_ERROR
    if args.dry_run and args.no_config:
        emit_error(
            "--dry-run and --no-config are mutually exclusive",
            "INVALID_ARG",
            hint="--no-config already avoids every write; drop --dry-run.",
        )
        return EXIT_USER_ERROR
    extensions = [e.strip() for e in (args.ensure_ext or "").split(",") if e.strip()]

    if az_available() is None:
        emit_error(
            "The Azure CLI is not installed or not on PATH", "AZ_NOT_INSTALLED", hint=install_hint()
        )
        return EXIT_SYSTEM_ERROR

    timer = Timer()
    blockers: list[dict[str, str]] = []

    try:
        config = (
            {"skipped": True}
            if args.no_config
            else apply_config(dry_run=args.dry_run, quiet=args.quiet)
        )
        cli = cli_info()
        parsed_account, account_error = az_json(["account", "show"], timeout=args.timeout)
    except AzUnavailableError as exc:
        emit_error(str(exc), "AZ_UNUSABLE", hint=install_hint())
        return EXIT_SYSTEM_ERROR

    account = as_dict(parsed_account)
    logged_in = bool(account.get("id"))
    data: dict[str, Any] = {
        "ready": False,
        "cli": cli,
        "config": config,
        "auth": {"logged_in": logged_in},
        "subscription": {},
        "other_subscriptions": [],
        "access": {"introspected": False, "posture": "unknown", "assignments": []},
        "resource_groups": [],
        "resource_group_count": 0,
        "blockers": blockers,
    }

    if not logged_in:
        blockers.append(
            {
                "code": "NOT_LOGGED_IN",
                "message": account_error or "No Azure account is signed in",
                "action": "Run `az login --use-device-code`, then give the user the URL and code "
                "it prints and wait for them to complete sign-in. Do not attempt to "
                "complete the login yourself.",
            }
        )
        if extensions:
            data["extensions_ensured"] = ensure_extensions(extensions, args.quiet)
        data["meta_note"] = "Azure lookups skipped because no account is signed in."
        finish(data, timer, args)
        return EXIT_USER_ERROR

    user: dict[str, Any] = account.get("user") or {}
    data["auth"] = {
        "logged_in": True,
        "user": user.get("name"),
        "user_type": user.get("type"),
        "tenant_id": account.get("tenantId"),
        "tenant_domain": account.get("tenantDefaultDomain"),
        "cloud": account.get("environmentName"),
    }
    data["subscription"] = {
        "id": account.get("id"),
        "name": account.get("name"),
        "state": account.get("state"),
    }

    data.update(survey_tenant(account, args))
    if account.get("state") and account["state"] != "Enabled":
        blockers.append(
            {
                "code": "SUBSCRIPTION_DISABLED",
                "message": f"Subscription state is {account['state']}",
                "action": "Ask the user to re-enable the subscription, or pick another from "
                "other_subscriptions and pass `--subscription <id>` on each command.",
            }
        )
    if extensions:
        data["extensions_ensured"] = ensure_extensions(extensions, args.quiet)

    data["ready"] = not blockers
    finish(data, timer, args)
    return EXIT_OK if data["ready"] else EXIT_USER_ERROR


def finish(data: dict[str, Any], timer: Timer, args: argparse.Namespace) -> None:
    """Emit the payload in the requested format."""
    if args.format == "text":
        print(render_text(data))
    else:
        emit_json(
            {
                "data": data,
                "meta": {"elapsed_ms": timer.elapsed_ms, "blocker_count": len(data["blockers"])},
            }
        )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AzUnavailableError as exc:
        emit_error(str(exc), "AZ_UNUSABLE", hint=install_hint())
        sys.exit(EXIT_SYSTEM_ERROR)
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(EXIT_SYSTEM_ERROR)
    except Exception as exc:
        emit_error(
            f"Unhandled failure: {exc}",
            "INTERNAL_ERROR",
            hint="Re-run with --skip-access --skip-groups --no-config to isolate it.",
        )
        sys.exit(EXIT_SYSTEM_ERROR)
