# KQL from the Azure CLI

One language, three query surfaces with different tables, time semantics, and
limits. Getting the surface right matters more than the syntax.

| Surface | Command | Data | Time column |
|---|---|---|---|
| Resource Graph | `az graph query -q "…"` | Current ARM resource configuration, all subscriptions | none — it is a snapshot |
| Log Analytics | `az monitor log-analytics query -w <customerId> --analytics-query "…"` | Diagnostic, activity, and Entra logs sent to a workspace | `TimeGenerated` |
| Application Insights | `az monitor app-insights query -a <app> -g <rg> --analytics-query "…"` | Application telemetry | `timestamp` |

Resource Graph answers *"how is it configured right now"*. The other two answer
*"what happened"*. Reaching for a log query to enumerate resources is the most
common mistake — it only sees resources that emit logs.

## Shell quoting

Single-quote the whole query and use double quotes inside it. This survives
bash without escaping:

```bash
az graph query -q 'Resources | where type =~ "microsoft.web/sites" | project name'
```

Multi-line queries work as-is inside single quotes. If a query needs a literal
single quote, put it in a file and use `--analytics-query "$(cat query.kql)"`.

## Core operators

```kusto
| where   Column == "x"        // filter, always first and as early as possible
| project name, rg = resourceGroup   // choose and rename columns
| extend  isPublic = properties.httpsOnly == false   // computed column
| summarize count() by type    // aggregate
| order by count_ desc         // note the trailing underscore on count()
| take 20                      // cap the result — never omit on an open query
| distinct principalId
| mv-expand rule = properties.securityRules   // one row per array element
| join kind=inner (OtherTable) on $left.Key == $right.Key
```

String matching, in order of cost:

| Operator | Meaning |
|---|---|
| `==` / `!=` | exact, case-sensitive |
| `=~` / `!~` | exact, case-insensitive — the right default for ARM type names |
| `has` | whole-token match, indexed and fast |
| `contains` | substring, slow — avoid on large log tables |
| `startswith` / `endswith` | as named |
| `in (…)` / `in~ (…)` | set membership |

Always `project` before `summarize`, and always bound the result with `take`
or `summarize`. An unbounded log query returns megabytes into the conversation.

---

## Resource Graph

Tables: `Resources` (everything), `ResourceContainers` (subscriptions and
resource groups), `SecurityResources` (Defender assessments and alerts),
`PolicyResources` (policy state), `AuthorizationResources` (role assignments
and definitions), `AdvisorResources`.

`properties` is a dynamic bag. Wrap in `tostring()` / `toint()` / `tobool()`
before comparing or string-matching, and remember ARM type names are matched
case-insensitively with `=~`:

```kusto
Resources
| where type =~ 'microsoft.web/sites'
| extend httpsOnly = tobool(properties.httpsOnly),
         tls      = tostring(properties.siteConfig.minTlsVersion)
| where httpsOnly == false or tls != '1.2'
| project name, resourceGroup, subscriptionId, httpsOnly, tls
```

Resolve subscription IDs to names by joining `ResourceContainers`:

```kusto
Resources
| where type =~ 'microsoft.web/sites'
| join kind=leftouter (
    ResourceContainers
    | where type =~ 'microsoft.resources/subscriptions'
    | project subscriptionId, subName = name
  ) on subscriptionId
| project name, resourceGroup, subName
```

Role assignments across every subscription in one query:

```kusto
AuthorizationResources
| where type =~ 'microsoft.authorization/roleassignments'
| extend principalId = tostring(properties.principalId),
         roleDefId   = tostring(properties.roleDefinitionId),
         scope       = tostring(properties.scope)
| join kind=leftouter (
    AuthorizationResources
    | where type =~ 'microsoft.authorization/roledefinitions'
    | project roleDefId = id, roleName = tostring(properties.roleName)
  ) on roleDefId
| where roleName in ('Owner', 'User Access Administrator')
| project principalId, roleName, scope
```

**Paging:** results cap at 1000 rows. Use `--first 1000 --skip N`, or
`--skip-token` from the previous response. `--subscriptions` and
`--management-groups` widen the scope; `--allow-partial-scopes` is needed when
querying a management group with subscriptions the principal cannot read.

---

## Log Analytics

`-w` takes the workspace **customer ID** (a GUID), not the workspace name:

```bash
WS=$(az monitor log-analytics workspace show -g RG -n WORKSPACE --query customerId -o tsv)
az monitor log-analytics query -w "$WS" -t P1D --analytics-query '…'
```

`-t/--timespan` is an ISO-8601 duration (`PT1H`, `P1D`, `P3DT12H`) and is
applied on top of any `TimeGenerated` filter in the query. Set it — the
workspace default window is generous.

Tables worth knowing:

| Table | Contents |
|---|---|
| `AzureActivity` | Control-plane operations — the durable version of the activity log |
| `AzureDiagnostics` | Catch-all resource diagnostics for services without a dedicated table |
| `AppServiceHTTPLogs` | App Service request logs (status, latency, client IP) |
| `AppServiceConsoleLogs` / `AppServiceAppLogs` | stdout and application logs |
| `AppServiceAuditLogs` | FTP/Kudu publishing access |
| `SigninLogs` / `AuditLogs` | Entra ID sign-ins and directory changes |
| `AZKVAuditLogs` | Key Vault data-plane access |
| `SecurityEvent` / `SecurityAlert` | Defender / Sentinel |

Sign-in failures by principal and reason:

```kusto
SigninLogs
| where TimeGenerated > ago(24h)
| where ResultType != 0
| summarize attempts = count() by UserPrincipalName, ResultType, ResultDescription, IPAddress
| order by attempts desc
| take 25
```

Successful sign-ins from an unusual location:

```kusto
SigninLogs
| where TimeGenerated > ago(7d) and ResultType == 0
| summarize count() by UserPrincipalName, Location = tostring(LocationDetails.countryOrRegion)
| order by count_ asc
```

App Service traffic anomalies:

```kusto
AppServiceHTTPLogs
| where TimeGenerated > ago(6h)
| summarize requests = count(), errors = countif(ScStatus >= 500) by CsHost, bin(TimeGenerated, 15m)
| where errors > 0
| order by TimeGenerated desc
```

Who changed role assignments, beyond the activity log's 90 days:

```kusto
AzureActivity
| where TimeGenerated > ago(90d)
| where OperationNameValue has "roleAssignments" and ActivityStatusValue == "Success"
| project TimeGenerated, Caller, OperationNameValue, _ResourceId
| order by TimeGenerated desc
```

---

## Application Insights

Tables are lower-case: `requests`, `dependencies`, `exceptions`, `traces`,
`customEvents`, `customMetrics`, `pageViews`, `availabilityResults`. The time
column is `timestamp`.

Bound the window with `--offset` (`30m`, `6h`, `1h30m`) or
`--start-time`/`--end-time` rather than only inside the query — the CLI flag is
what limits how much is scanned.

```kusto
// Slowest operations
requests
| summarize p95 = percentile(duration, 95), count() by name
| order by p95 desc
| take 15

// Failures joined to the exception that caused them
requests
| where success == false
| join kind=inner (exceptions | project operation_Id, type, outerMessage) on operation_Id
| summarize count() by name, resultCode, type, outerMessage
| order by count_ desc
| take 20

// Dependency failures — usually the real cause of a 5xx
dependencies
| where success == false
| summarize count() by target, name, resultCode
| order by count_ desc

// Trace hunt for one request
traces
| where operation_Id == "<id>"
| project timestamp, severityLevel, message
| order by timestamp asc
```

Cross-resource queries use `app()` and `workspace()`:

```kusto
app('other-appinsights').requests | take 10
workspace('WORKSPACE-NAME').AzureActivity | take 10
```

## Gotchas

- `count()` produces a column named `count_`, with a trailing underscore.
- `ago(7d)` inside the query does not override a narrower CLI `--offset` /
  `-t` window; the CLI window wins.
- Resource Graph has no time dimension. "When was this created?" is an
  `AzureActivity` / activity-log question, not a Resource Graph one.
- Dynamic fields (`properties.x`) compare as `dynamic`, not `string` — a bare
  `properties.state == 'Running'` can silently match nothing. Wrap in
  `tostring()`.
- `contains` on a large log table is slow enough to time out; use `has`.
- Empty results are a valid answer. Confirm the table has *any* rows in the
  window (`| take 5`) before concluding a resource is clean.
