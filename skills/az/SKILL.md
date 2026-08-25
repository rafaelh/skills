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
  version: "1.0"
---

# Azure CLI

Two helper scripts do the orienting and the lookup; `az` itself does the work.

## 1. Orient first — one call, always

```bash
python3 "${SKILL_DIR}/scripts/az-preflight.py" --format text
```

Returns in ~2s: CLI version and installed extensions, signed-in user, tenant, active subscription,
other reachable subscriptions, **access posture**, and the resource groups you can see.

Read `data.ready` and `data.blockers`. Exit `1` means the user must act — the blocker carries the
exact instruction. Never work around a blocker by guessing.

`--skip-access --skip-groups` gives a ~0.5s version when you only need identity.

## 2. Look up commands — never guess flags

```bash
python3 "${SKILL_DIR}/scripts/az-help.py" --format text webapp config      # what exists here
python3 "${SKILL_DIR}/scripts/az-help.py" --format text webapp create      # how to call it
python3 "${SKILL_DIR}/scripts/az-help.py" --tree webapp --match "log|diag" # find the verb
```

This is the installed CLI's own help, compacted ~5x on a leaf command by dropping the global
argument block and reducing optional flags to names plus enumerated values. Prefer it over
`az ... -h`; add `--full` only when compact output is ambiguous. Group listings barely compact —
`--tree` is the reason to use it on a group, not size.

`--tree <group>` is the one thing plain `-h` cannot do: `-h` reveals a single level, so a nested
command like `az webapp config ssl bind` otherwise costs three round trips. Use `--tree` with
`--match` when you know the verb but not the group.

Exit `3` means the command path does not exist in **this** install — usually a different group,
occasionally an extension. Do not retry the same path.

## 3. Output shape and read volume

Project with `--query`, and pass `-o` explicitly on any command whose output you read.

**Stop when the query has answered the question.** A projected `az graph query` or `az ... list`
over an estate *is* the answer — do not then re-read the resources individually with `az ... show`
to confirm it. Re-read one only when the projection is missing a field you actually need.

JSON is only the *fallback* default: `core.output` in the user's `~/.azure/config` or
`AZURE_CORE_OUTPUT` overrides it globally, so under a `table` or `yaml` default a command you meant
to parse returns text and still exits `0`. That setting is the user's own preference for their
interactive shell — never change it. Preflight reports it as `config.output_default`, flagged when
it is not JSON-shaped (`json` and `jsonc` both parse; `az` drops the colour when stdout is not a
terminal).

## 4. Read before you write

Say what will change and to which resource, and get confirmation, before any write. Never add
`--yes` on your own initiative.

Honour the preflight's `access.posture`:

| Posture | Meaning | What to do |
|---|---|---|
| `write` | An Owner/Contributor-class role was found | Proceed after confirming writes |
| `read-only` | Only Reader-class roles | Reads only. Print the write command for the user to run; do not attempt it |
| `unknown` | Role listing was denied, or the roles are unrecognised | Assume least privilege — treat as `read-only` |

`(AuthorizationFailed)` means the principal lacks RBAC at that scope. Report the scope and the role
needed, then stop. Do not retry, widen scope, or attempt a different route to the same write.

For ARM and Bicep, `az deployment group what-if -g RG --template-file main.bicep` is a genuine dry
run — use it before every `deployment group create`.

Secrets: `az keyvault secret show`, `az webapp config appsettings list`, and
`az storage account keys list` return live credentials. The risk starts when the value enters your
context, not when it reaches the conversation — once read it can be echoed by accident, quoted back
in a summary, or written to a scratch file. So project these on the way out, not after:

```bash
az webapp config appsettings list -g RG -n APP --query "[].name" -o tsv
az storage account keys list -g RG -n ACCT --query "[].{name:keyName,created:creationTime}"
az keyvault secret show --vault-name V -n S --query "attributes.updated" -o tsv
```

Diagnosing a credential is almost never a reason to read one. A key that no longer works was
rotated, and rotation leaves a timestamp: `az storage account show --query keyCreationTime`, the
secret's `attributes.updated`, or a `regenerateKey`/`SecretSet` entry in `az monitor activity-log
list`. Compare that against when the caller last worked — that is the whole diagnosis, and it never
touches the value. Prefer `--auth-mode login` over fetching account keys at all.

## 5. When there is no typed command

In order of preference:

1. The typed command — `az webapp show`.
2. `az resource show --ids <arm-id> --api-version 2023-01-01` for unmodelled types.
3. `az rest --method get --url "https://management.azure.com/subscriptions/…?api-version=…"`
   — attaches the bearer token automatically for any URL matching an endpoint in
   `az cloud show --query endpoints`, so it reaches every ARM and Microsoft Graph API, including
   ones with no CLI surface at all.
4. `az graph query -q "<KQL>"` (Resource Graph) for inventory across every
   subscription at once — far cheaper than looping `az resource list`.

## 6. Session mechanics

- **Multiple subscriptions:** pass `--subscription <id>` per command. Do not run `az account set` —
  it mutates the user's global default for every other shell.
- **Long operations:** `--no-wait`, then `az <group> wait --created --ids <id>`.
- **Parallel `az` calls:** give each worker its own `AZURE_CONFIG_DIR`; concurrent MSAL token-cache
  writes corrupt `~/.azure`.
- **Bulk operations:** `... --query "[].id" -o tsv | az vm start --ids @-` uses the CLI's built-in
  parallelism.
