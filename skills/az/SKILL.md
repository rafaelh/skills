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

Two helper scripts do the orienting and the lookup; `az` itself does the work. Both sit beside this
file in `scripts/`; `${SKILL_DIR}` below is this skill's own directory, which the agent resolves at
run time.

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

This is the installed CLI's own help, compacted ~8x by dropping the global argument block and
reducing optional flags to names plus enumerated values. Prefer it over `az ... -h`. Add `--full` only when compact output is ambiguous.

`--tree <group>` is the one thing plain `-h` cannot do: `-h` reveals a single level, so a nested
command like `az webapp config ssl bind` otherwise costs three round trips. Use `--tree` with
`--match` when you know the verb but not the group.

Exit `3` means the command path does not exist in **this** install — usually a different group,
occasionally an extension. Do not retry the same path.

## 3. Keep output small

`az` returns entire ARM objects by default; a bare `az webapp list` is tens of thousands of tokens.
Always project:

```bash
az webapp list --query "[].{name:name,rg:resourceGroup,state:state}" -o json
az webapp show -g RG -n APP --query "id" -o tsv        # single value into a variable
az group create -g RG -l uksouth --output none          # when only the exit code matters
az ... --only-show-errors                               # drop deprecation banners from stderr
```

Pass `-o` explicitly on any command whose output you read. JSON is only the *fallback* default:
`core.output` in the user's `~/.azure/config` or `AZURE_CORE_OUTPUT` overrides it globally, so under
a `table` or `yaml` default a command you meant to parse returns text and still exits `0`. That
setting is the user's own preference for their interactive shell — never change it. Preflight
reports it as `config.output_default`, flagged when it is not JSON-shaped (`json` and `jsonc` both
parse; `az` drops the colour when stdout is not a terminal).

Never paste a raw `az ... list` dump into the conversation. Project first, then show the user a
table.

## 4. Read before you write

Default to reads. Before any `create`, `delete`, `update`, `set`, `add`, `remove`, `start`, `stop`,
`restart`, `purge`, `regenerate`, `rotate`, or `--yes`: say what will change and to which resource,
and get confirmation. Never add `--yes` on your own initiative.

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
- **Long operations:** `--no-wait`, then `az <group> wait --created --ids <id>`. Do not block on a
  20-minute deployment.
- **Parallel `az` calls:** give each worker its own `AZURE_CONFIG_DIR`; concurrent MSAL token-cache
  writes corrupt `~/.azure`.
- **Bulk operations:** `... --query "[].id" -o tsv | az vm start --ids @-` uses the CLI's built-in
  parallelism.
- **Never run:** `az login` unattended (print the device code and wait for the user),
  `az interactive`, `az configure`, `az feedback`, `az survey`, `az upgrade` — all interactive or
  globally state-mutating.

## 7. References — read on demand, not up front

| File | Read it when |
|---|---|
| [references/recipes.md](references/recipes.md) | App Service / PaaS operations, resource inventory, security investigation, App Insights and Log Analytics access |
| [references/kql.md](references/kql.md) | Writing any KQL — Resource Graph, Log Analytics, or Application Insights |
| [references/troubleshooting.md](references/troubleshooting.md) | An `az` command failed and the error code is not self-explanatory |
