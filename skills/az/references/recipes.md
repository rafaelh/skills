# Recipes

Sequences where the naive command is wrong, expensive, or three commands short
of an answer. Everything else: look it up with `az-help.py`.

All examples assume the active subscription from preflight. Add
`--subscription <id>` when working across several.

---

## Inventory

**Reach for Resource Graph first.** One query covers every subscription the
principal can see, returns projected columns only, and costs one round trip.
`az resource list` is per-subscription and returns whole ARM objects.

```bash
# Everything, grouped by type — the fastest way to understand a new tenant
az graph query -q "Resources | summarize count() by type | order by count_ desc" -o table

# All App Service apps with their plan, state, and runtime
az graph query -q "Resources
  | where type =~ 'microsoft.web/sites'
  | project name, resourceGroup, subscriptionId, kind,
            state = properties.state,
            plan = tostring(split(properties.serverFarmId,'/')[8])" -o table

# Resources created in the last 7 days (Resource Graph has no createdTime;
# use the activity log for creation events — see Audit below)
az graph query -q "Resources | where tags['env'] == 'prod' | project name, type, resourceGroup" -o table

# Paginate beyond the 1000-row default
az graph query -q "Resources | project id" --first 1000 --skip 1000 -o table
```

Resource Graph is an extension; preflight installs it, or
`az extension add --name resource-graph`.

Per-subscription fallback when Resource Graph is unavailable:

```bash
az resource list --query "[].{name:name,type:type,rg:resourceGroup}" -o table
az resource list --resource-type Microsoft.Web/sites --query "[].name" -o tsv
```

---

## App Service and PaaS

```bash
az webapp list --query "[].{name:name,rg:resourceGroup,state:state,host:defaultHostName}" -o table
az webapp show -g RG -n APP --query "{state:state,https:httpsOnly,tls:siteConfig.minTlsVersion}" -o json
az webapp config show -g RG -n APP --query "{stack:linuxFxVersion,alwaysOn:alwaysOn,ftps:ftpsState}" -o json
az webapp restart -g RG -n APP
az webapp list-instances -g RG -n APP --query "[].name" -o tsv
```

**App settings and connection strings hold live secrets.** Project to names
only unless a value is genuinely needed, and never echo values back:

```bash
az webapp config appsettings list -g RG -n APP --query "[].name" -o tsv
az webapp config connection-string list -g RG -n APP --query "[].{name:name,type:type}" -o table
```

Slots, identity, and networking:

```bash
az webapp deployment slot list -g RG -n APP --query "[].name" -o tsv
az webapp identity show -g RG -n APP --query "{type:type,principalId:principalId}" -o json
az webapp vnet-integration list -g RG -n APP -o table
az webapp config access-restriction show -g RG -n APP -o json
```

Function Apps, Container Apps, and Static Web Apps mirror the same shape —
`az functionapp …`, `az containerapp …`, `az staticwebapp …`.

Deployment, with `--no-wait` for anything slow:

```bash
az webapp deploy -g RG -n APP --src-path ./app.zip --type zip
az webapp deployment source show -g RG -n APP --query "{repo:repoUrl,branch:branch}" -o json
```

---

## Logs and diagnostics

Live and recent platform logs (no Log Analytics needed):

```bash
az webapp log config -g RG -n APP --application-logging filesystem --level information
az webapp log tail -g RG -n APP          # streams; run with a timeout, it does not exit
az webapp log download -g RG -n APP --log-file logs.zip
```

**Application Insights.** `--apps/-a` takes the component name (with `-g`) or
its app ID. Always bound the window with `--offset` or `--start-time`, and
always `summarize` or `take` — an unbounded query returns megabytes.

```bash
# Find the component first
az monitor app-insights component show -g RG --query "[].{name:name,appId:appId}" -o table

# Failures in the last 6 hours, grouped
az monitor app-insights query -g RG -a APPINSIGHTS --offset 6h \
  --analytics-query "requests | where success == false | summarize count() by name, resultCode | order by count_ desc | take 20" -o json

# The exceptions behind them
az monitor app-insights query -g RG -a APPINSIGHTS --offset 6h \
  --analytics-query "exceptions | summarize count() by type, outerMessage | top 10 by count_" -o json
```

**Log Analytics.** `-w` is the workspace *customer ID* (a GUID), not its name:

```bash
az monitor log-analytics workspace list --query "[].{name:name,rg:resourceGroup,id:customerId}" -o table
az monitor log-analytics query -w <customerId> -t P1D \
  --analytics-query "AzureDiagnostics | summarize count() by Category, ResourceId | take 20" -o json
```

Both are extensions (`application-insights`, `log-analytics`); preflight's
`--ensure-ext` installs them ahead of time. See
[kql.md](kql.md) before writing the query.

Check whether a resource is even sending logs:

```bash
az monitor diagnostic-settings list --resource <arm-id> \
  --query "value[].{name:name,workspace:workspaceId,logs:logs[?enabled].category}"
```

---

## Security investigation

### Who can do what

```bash
# Every assignment in the subscription, resolved to names
az role assignment list --all --include-inherited --include-groups \
  --query "[].{principal:principalName,type:principalType,role:roleDefinitionName,scope:scope}" -o table

# Just the dangerous ones
az role assignment list --all --query "[?roleDefinitionName=='Owner' || roleDefinitionName=='User Access Administrator'].{principal:principalName,scope:scope}" -o table

# Custom roles — often where over-permissioning hides
az role definition list --custom-role-only true \
  --query "[].{name:roleName,actions:permissions[0].actions}" -o json

# What one principal has
az role assignment list --all --assignee <upn-or-objectId> --include-inherited -o table
```

`principalName` is empty when Microsoft Graph reads are denied; fall back to
`principalId` and say so rather than guessing.

### Service principals and app registrations

```bash
az ad sp list --all --query "[?keyCredentials[0] || passwordCredentials[0]].{name:displayName,appId:appId}" -o table
az ad app list --all --query "[].{name:displayName,appId:appId,signInAudience:signInAudience}" -o table

# Credentials expiring or expired
az ad app credential list --id <appId> --query "[].{name:displayName,end:endDateTime}" -o table
```

### Exposure

```bash
# Web apps reachable over plain HTTP or weak TLS
az graph query -q "Resources
  | where type =~ 'microsoft.web/sites'
  | where properties.httpsOnly == false
  | project name, resourceGroup, subscriptionId" -o table

# Storage accounts allowing public blob access or open network rules
az graph query -q "Resources
  | where type =~ 'microsoft.storage/storageAccounts'
  | project name, resourceGroup,
            publicBlob = properties.allowBlobPublicAccess,
            defaultAction = properties.networkAcls.defaultAction
  | where publicBlob == true or defaultAction =~ 'Allow'" -o table

# Public IPs and what they are attached to
az network public-ip list --query "[].{name:name,ip:ipAddress,attachedTo:ipConfiguration.id}" -o table

# NSG rules permitting inbound from anywhere
az graph query -q "Resources
  | where type =~ 'microsoft.network/networkSecurityGroups'
  | mv-expand rule = properties.securityRules
  | where rule.properties.access =~ 'Allow'
      and rule.properties.direction =~ 'Inbound'
      and rule.properties.sourceAddressPrefix in ('*','0.0.0.0/0','Internet')
  | project nsg = name, resourceGroup, ruleName = rule.name,
            port = rule.properties.destinationPortRange" -o table
```

Defender for Cloud, when licensed:

```bash
az security assessment list --query "[?status.code=='Unhealthy'].{name:displayName,resource:resourceDetails.Id}" -o table
az security alert list --query "[].{name:alertDisplayName,severity:reportedSeverity,state:state}" -o table
```

### Audit — what changed and who did it

```bash
# Writes in a resource group over the last 24h
az monitor activity-log list -g RG --offset 24h \
  --query "[?operationName.value != 'Microsoft.Resources/deployments/read'].{time:eventTimestamp,op:operationName.localizedValue,by:caller,status:status.value}" -o table

# Everything one principal did
az monitor activity-log list --caller user@contoso.com --offset 7d --max-events 200 \
  --query "[].{time:eventTimestamp,op:operationName.value,resource:resourceId}" -o table

# Role assignment changes specifically — the highest-signal audit query
az monitor activity-log list --offset 30d --max-events 500 \
  --query "[?contains(operationName.value,'roleAssignments')].{time:eventTimestamp,op:operationName.value,by:caller,scope:resourceId}" -o table
```

The activity log holds 90 days. Older than that needs a Log Analytics workspace
with the `AzureActivity` table — see [kql.md](kql.md).

### Key Vault

```bash
az keyvault list --query "[].{name:name,rg:resourceGroup,rbac:properties.enableRbacAuthorization,purgeProtection:properties.enablePurgeProtection}" -o table
az keyvault secret list --vault-name VAULT --query "[].{name:name,enabled:attributes.enabled,expires:attributes.expires}" -o table

# Who accessed a vault — requires diagnostic settings pointing at a workspace
az monitor diagnostic-settings list --resource <vault-arm-id> --query "value[].name"
```

Never run `az keyvault secret show` unless the user has asked for the value,
and never print it.

---

## Deployment

```bash
# Always what-if before create
az deployment group what-if -g RG --template-file main.bicep --parameters @params.json
az deployment group create -g RG --template-file main.bicep --parameters @params.json --no-wait

# Diagnose a failure
az deployment group list -g RG --query "[?properties.provisioningState=='Failed'].name" -o tsv
az deployment operation group list -g RG -n DEPLOYMENT \
  --query "[?properties.provisioningState=='Failed'].{resource:properties.targetResource.resourceName,error:properties.statusMessage.error.message}"
```

---

## Generic escape hatches

```bash
# Property not modelled by the CLI
az resource show --ids <arm-id> --api-version 2023-01-01 --query "properties"

# No CLI surface at all — any ARM or Graph API
az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.Web/sites?api-version=2023-12-01" \
  --query "value[].name"
az rest --method get --url "https://graph.microsoft.com/v1.0/me"

# Update a property no flag exposes
az webapp update -g RG -n APP --set siteConfig.minTlsVersion=1.2
```
