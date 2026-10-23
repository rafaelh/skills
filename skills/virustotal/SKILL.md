---
name: virustotal
description: >
  Look up file hashes, URLs, domains, and IP addresses on VirusTotal via the `vt` CLI — detection
  verdicts, reputation, and analysis reports — and submit files or URLs for scanning.
---

Use the `vt` CLI to check files, URLs, domains, and IP addresses for threats:

- `vt file <hash>`, `vt url <url>`, `vt domain <domain>`, `vt ip <ip>`: get the report and
  reputation. Each takes several values, or `-` to read them from stdin.
- `vt scan file <path>` / `vt scan url <url>`: submit for analysis, then `vt analysis <id>` for the
  result.
- `<cmd> relationships <id>`: list related objects. The public API returns only some
  relationship types.
- Add `--format json` when you parse the output.

Look up a file by hash before you upload it. VirusTotal shares uploaded files with its paying
customers, so never upload internal or customer files.

**Public API rate limits:** 4 requests per minute and 500 per day. The public API isn't licensed for
commercial use. Premium-only commands (`search`, `download`, `hunting`, `retrohunt`, `iocstream`,
`monitor`, `threatprofile`) fail with a public key.

If `vt` is missing, tell the user to run `brew install virustotal-cli`. If no key is configured,
tell them to run `vt init` or set `VIRUSTOTAL_API_KEY`. Then stop.
