# Troubleshooting `az`

`az` writes errors to stderr as `ERROR: (Code) message`. The parenthesised code
is the actionable part. Add `--only-show-errors` to strip the deprecation
banners that otherwise surround it, and `--debug` only as a last resort — it
emits thousands of lines.

## Authorisation and identity

| Error | Cause | Action |
|---|---|---|
| `(AuthorizationFailed)` | The principal lacks an RBAC action at that scope | Report the scope and the missing action. **Stop** — do not retry, widen scope, or find another route to the same write |
| `(LinkedAuthorizationFailed)` | The write is allowed, but it references a resource (identity, subnet, vault) the principal cannot read | Name the linked resource; it needs a separate assignment |
| `(Authorization_RequestDenied)` | Microsoft Graph read denied — a directory permission, not RBAC | Fall back to object IDs; `principalName` will stay empty |
| `AADSTS50076` / `AADSTS50079` | MFA or conditional access required | The user must re-run `az login` interactively; you cannot satisfy this |
| `AADSTS700082` / refresh token expired | Cached token aged out | `az login --use-device-code`, then hand the user the URL and code |
| `Please run 'az login'` | No cached credential at all | Same as above |

## Wrong place, not wrong permission

| Error | Cause | Action |
|---|---|---|
| `(ResourceGroupNotFound)` | Wrong resource group **or the right one in a different subscription** | Check `az account show` before assuming the group is gone |
| `(SubscriptionNotFound)` | Subscription is not in the signed-in tenant | `az account list -o table`; the user may need `az login --tenant <id>` |
| `(ResourceNotFound)` | Name typo, or the resource is in another subscription | `az graph query -q "Resources \| where name =~ 'NAME' \| project id"` searches everywhere at once |
| `(ParentResourceNotFound)` | The parent (server, plan, vault) does not exist yet | Create or locate the parent first |

## Provider, quota, and capacity

| Error | Cause | Action |
|---|---|---|
| `(MissingSubscriptionRegistration)` | Resource provider not registered | `az provider register -n Microsoft.X --wait` (needs Contributor) |
| `(QuotaExceeded)` / `(OperationNotAllowed)` | Subscription or region quota reached | `az vm list-usage -l <loc> -o table`; a quota increase is a support ticket |
| `SkuNotAvailable` | SKU unavailable in that region or zone | `az vm list-skus -l <loc> --size <size> --all -o table` to find where it is |
| `(RequestDisallowedByPolicy)` | Azure Policy blocked it — **not** an RBAC failure | The message names the policy assignment; report it, do not retry |

## CLI-level failures

| Error | Cause | Action |
|---|---|---|
| `is misspelled or not recognized by the system` | Wrong path, or the command lives in an uninstalled extension | `az-help.py --tree <group> --match <verb>` |
| `unrecognized arguments: --foo` | Flag does not exist on this version | `az-help.py <command>` — never carry a flag over from documentation |
| `Failed to parse string as JSON` | Shell quoting mangled an inline JSON value | Put the JSON in a file and pass `@file.json` |
| `Unable to prompt for extension install confirmation as no tty available` | `extension.use_dynamic_install` has been pinned to `yes_prompt` in config | `az extension add --name X` explicitly. Do not "fix" this by setting `yes_without_prompt` globally — that removes the prompt from the user's own terminal |
| `Preview version of extension is disabled by default` | Informational only — `az` still installs preview extensions that have no stable release | Ignore it, or add `--only-show-errors`. Setting `dynamic_install_allow_preview=true` globally makes *all* preview installs silent, including in the user's interactive shell |
| Token cache errors under parallel calls | Concurrent MSAL writes to `~/.azure` | Give each worker its own `AZURE_CONFIG_DIR` |
| Deployment succeeded but the resource is absent | `--no-wait` was used and the operation is still running | `az <group> wait --created --ids <id>` |

## Diagnosing a failed ARM deployment

The top-level failure message is almost always a wrapper. The cause is in the
operation list:

```bash
az deployment group list -g RG --query "[?properties.provisioningState=='Failed'].name" -o tsv
az deployment operation group list -g RG -n DEPLOYMENT \
  --query "[?properties.provisioningState=='Failed'].{resource:properties.targetResource.resourceName,code:properties.statusMessage.error.code,message:properties.statusMessage.error.message}" -o json
```

## When a read genuinely returns nothing

Empty is a valid answer, and different from an error. Before reporting "there
are none", confirm you are looking in the right place:

1. `az account show --query "{sub:name,id:id}"` — right subscription?
2. `az group list --query "[].name" -o tsv` — can the principal see any groups?
3. `az graph query -q "Resources | summarize count() by type"` — does the
   principal see anything at all across subscriptions?

If step 3 is also empty, the account has no reader access anywhere, which is a
permissions finding to report — not an absence of resources.
