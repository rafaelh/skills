---
name: dropbox
description: List, search, download, upload, move, or share files in Dropbox via the dbxcli CLI (`dbxcli`), using its JSON output and command manifests.
---

# Dropbox (dbxcli)

- Docs: https://dropbox.github.io/dbxcli/. JSON schema and error codes: https://github.com/dropbox/dbxcli/blob/master/docs/json-schema/v1/README.md.
- Always pass `--output=json`. stdout is one envelope; stderr is diagnostics only. Check the exit code and `.ok`.
  - `ok: true`: read `results[].status`, `results[].kind`, `results[].result`, and `warnings`. Ignore prose and undocumented fields.
  - `ok: false`: branch on `.error.code`, not `.error.message`. Don't retry writes or auth errors. `rate_limited` includes `.error.details.retry_after_seconds`.
- Before running a command you haven't used yet this session, read its manifest: `dbxcli <cmd> --help --output=json | jq '.results[0].result'`. Check `supports_structured_output`, `flags`, `destructive_level`, and `may_prompt`. If `supports_structured_output` is false, don't run it as an automated action. Tell the user, or pick a supported command.

## Setup (if `dbxcli` is missing or the error code is `auth_required`)

1. `brew install dbxcli`
2. Ask the user to run `! dbxcli login` themselves. It's a browser OAuth flow (`may_prompt: true`, no JSON output). Don't ask for a token in chat, and never echo `DBXCLI_ACCESS_TOKEN`.
3. Verify with `dbxcli account --output=json`.

## Reads

- Scope reads to the narrowest folder. Use `--limit` on `ls` and `search`. Don't recurse from `/`. A limited result is only a sample, so it can't prove something is absent.
- The CLI handles pagination internally. Never pass or invent cursors.
- `search` matches file names. Add `--content` only when the user asks to search inside files.
- For search → get: copy the exact `path` from the search JSON, then `dbxcli get <path> <local-file>` into the scratchpad. Don't download to stdout (`-`). Process the local file and report its path.

## Writes and external actions

These need explicit confirmation from the user before the real run: `put`, `cp`, `mv`, `rm`, `mkdir`, `restore`, and any `share` or `share-link` command that creates or changes something.

- Use `--dry-run` first wherever the manifest lists it (`put`, `rm`, ...). A dry run that succeeds doesn't authorize the real run.
- Always set `--if-exists` explicitly (`fail|skip|autorename|overwrite`) where it's offered. Never rely on the default. `put` reports `destructive_level: none`, but `--if-exists overwrite` still replaces files.
- `rm` uses `--force`, not `--yes`. `--permanent` can't be undone. Only use it if the user asks for it by name.
- Creating a shared link exposes content outside the account. Confirm the visibility and expiry settings with the user first.
- `--as-member` acts as another team member (team-admin impersonation). Only use it when the user explicitly asks.
- On team accounts `/` may not be writable. Run `dbxcli ls / --output=json` and pick a personal or team folder instead.
