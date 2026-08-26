---
name: az
description: >
  Use the Azure CLI (`az`) to inspect, manage, deploy, or troubleshoot Azure resources, and to
  investigate Azure security questions. Trigger whenever the user asks to create, configure, list,
  audit, or interact with anything in Azure — App Service and other PaaS, storage, networking,
  identity, RBAC — even if they do not say "az" or "Azure CLI". Also trigger for Azure inventory
  questions ("what's running in the subscription", "which apps are public"), Application Insights or
  Log Analytics queries, KQL, Resource Graph, activity log / audit questions, and questions about
  `az` command syntax itself.
compatibility: >
  Requires the Azure CLI on PATH and Python 3.14+ (stdlib only). `scripts/az-preflight.py` reports
  the install command, login instruction, and access posture when something is missing, so run it
  before anything else rather than diagnosing by hand.
metadata:
  version: "1.1"
---

# Azure CLI

Two helper scripts do the orienting and the lookup; `az` itself does the work.

## 1. If you need to orient yourself, run preflight

```bash
python3 "${SKILL_DIR}/scripts/az-preflight.py" --format text
```

Returns: CLI version and installed extensions, signed-in user, tenant, active subscription,
other reachable subscriptions, **access posture**, and the resource groups you can see.

Use `--skip-access --skip-groups` when you only need identity.

## 2. Look up commands and flags if you don't know them

```bash
python3 "${SKILL_DIR}/scripts/az-help.py" --format text webapp config      # what exists here
python3 "${SKILL_DIR}/scripts/az-help.py" --format text webapp create      # how to call it
python3 "${SKILL_DIR}/scripts/az-help.py" --tree webapp --match "log|diag" # find the verb
```

This script is a compacted help for the installed CLI, so it is always up to date. It can be used to
find a command by group, or a flag by name. Prefer it over `az ... -h`; add `--full` only when
compact output is ambiguous. Group listings barely compact — `--tree` is the reason to use it on a
group, not size.

`--tree <group>` is the one thing plain `-h` cannot do: `-h` reveals a single level, so a nested
command like `az webapp config ssl bind` otherwise costs three round trips. Use `--tree` with
`--match` when you know the verb but not the group.

## 3. Output shape and read volume

Project with `--query`, and pass `-o` explicitly on any command whose output you read.

**Stop when the query has answered the question.** A projected `az graph query` or `az ... list`
over an estate *is* the answer — do not then re-read the resources individually with `az ... show`
to confirm it. Re-read one only when the projection is missing a field you actually need.

## 4. Read before you write

Say what will change and to which resource, and get confirmation, before any write. Never add
`--yes` on your own initiative.

