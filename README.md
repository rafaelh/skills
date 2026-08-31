```
                            .                  .     .-. .         . .
                           / \                _|_   (   )|      o  | |
                          /___\  .-.. .-. .--. |     `-. |.-.   .  | | .--.
                         /     \(   |(.-' |  | |    (   )|-.'   |  | | `--.
                        '       ``-`| `--''  `-`-'   `-' '  `--' `-`-`-`--'
                                 ._.'
```

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.14%2B-blue?logo=python&logoColor=white" alt="Python 3.14+"></a>
  <a href="https://nodejs.org/"><img src="https://img.shields.io/badge/node-18%2B-green?logo=node.js&logoColor=white" alt="Node.js 18+"></a>
  <a href="https://docs.anthropic.com/en/docs/claude-code"><img src="https://img.shields.io/badge/Claude_Code-plugin-orange?logo=anthropic" alt="Claude Code"></a>
  <a href="https://owasp.org/www-project-agentic-skills-top-10/"><img src="https://img.shields.io/badge/OWASP-audited-brightgreen?logo=owasp" alt="OWASP"></a>
</p>

This repo contains agent skills that I use on a day to day basis outside of standard repo skills. They all comply with (and to some extent enforce) the [agentskills.io](https://agentskills.io/) specification.

Most of these tools use python scripts, though there are some that use typescript.

## Skills

<details>
  <summary>skill-audit</summary>

### skill-audit

Audits, optimizes, validates, and trigger-evals Claude Agent Skills (SKILL.md files).

- **Validation and analysis** — frontmatter, body structure and script references against the spec; token budget, section balance and progressive disclosure quality; description overlap between sibling skills (bag-of-words cosine similarity); whether the skill should have helper scripts at all
- **Description optimization** — rewrites `description` with imperative phrasing and concrete trigger contexts, then proves the rewrite: a trigger-rate eval invokes `claude -p` against a labeled query set, iterates candidates against train failures, and scores the winner on a held-out split
- **Script quality** *(Python only)* — performance anti-patterns via AST analysis plus optional cProfile, and the agent-tool interface contract: `--format`, `--quiet`, `--dry-run`, exit codes `0/1/2/3`, no `input()`, no free-form stdout errors
- **Security** — audits against the [OWASP Agentic Skills Top 10](https://owasp.org/www-project-agentic-skills-top-10/): over-privileged `allowed-tools`, hardcoded secrets, unsafe deserialization, shell injection, supply chain (fetch-and-run, unpinned deps), hidden-unicode instructions, and prompt injection in prose. No guarantee it'll work, but better than nothing. Prose checks apply to any skill; the Python-specific ones only to `.py` scripts

Scripts live in `skills/skill-audit/scripts/` and accept `--json` for machine-readable output.

| Script | Purpose |
|---|---|
| `validate_skill.py` | Frontmatter + body validation, exit 1 on any failure |
| `analyze_skill.py` | Token count, section balance, progressive disclosure quality |
| `recommend_scripts.py` | Advises on helper scripts — what to add and what patterns to follow |
| `detect_skill_overlap.py` | Cosine similarity between skill descriptions; single-skill or all-pairs mode |
| `eval_triggers.py` | Trigger-rate eval against a labeled query set; train/validation split |
| `optimize_description.py` | Multi-round description optimizer; propose-only by default, `--apply` to write |
| `count_tokens.py` | Token counter; exact via Anthropic SDK, heuristic fallback |
| `perf_check.py` | AST-based performance checker + optional cProfile profiling |
| `audit_security.py` | OWASP Agentic Skills Top 10 audit; FAILs on hardcoded secrets, WARNs on the rest |

</details>

---

<details>
  <summary>skill-audit-ts</summary>

### skill-audit-ts

The TypeScript twin of `skill-audit` — same audit/eval workflow, same script names and modes, for skills whose bundled scripts are TypeScript (run via `npx tsx`) instead of Python. For machines without Python available, most commonly Windows.

Validation, analysis and description optimization match `skill-audit` above. What differs is everything language-specific: perf checks target JS/TS anti-patterns (string `+=` in a loop, `new RegExp(literal)` recompiled per iteration, `.includes()`/`.indexOf()` membership tests, `readFileSync` or `.sort()` in a loop), the security script-construct checks target `eval()`/`new Function()`, `child_process.exec`/`{shell: true}` and `package.json` pinning, and `validate_agent_tool.ts` is folded in rather than borrowed from `agent-tool-builder`, which is Python-only.

Scripts live in `skills/skill-audit-ts/scripts/` and accept `--format json|text` for machine-readable output.

| Script | Purpose |
|---|---|
| `validate_skill.ts` | Frontmatter + body validation, exit 1 on any failure |
| `analyze_skill.ts` | Token count, section balance, progressive disclosure quality |
| `recommend_scripts.ts` | Advises on helper scripts — what to add and what patterns to follow |
| `detect_skill_overlap.ts` | Cosine similarity between skill descriptions; single-skill or all-pairs mode |
| `eval_triggers.ts` | Trigger-rate eval against a labeled query set; train/validation split |
| `optimize_description.ts` | Multi-round description optimizer; propose-only by default, `--apply` to write |
| `count_tokens.ts` | Token counter; exact via `@anthropic-ai/sdk` (optional dep), heuristic fallback |
| `perf_check.ts` | AST-based (TypeScript compiler API) performance checker, static only |
| `audit_security.ts` | OWASP Agentic Skills Top 10 audit; FAILs on hardcoded secrets, WARNs on the rest |
| `validate_agent_tool.ts` | Interface contract validation — flags, exit codes, output shape (folded in from agent-tool-builder) |

</details>

---

<details>
  <summary>agent-tool-builder</summary>

### agent-tool-builder

Builds and reviews **Python** scripts intended to be called by AI agents as tools. Enforces a standard interface contract — structured JSON output, predictable exit codes, `--format`, `--quiet`, `--dry-run` — and catches performance anti-patterns before they cost agent round-trips.

- Runs a decision-forcing design interview — data model, operations, flag set, JSON output shape, failure modes — before a line of code gets written
- Validates the contract: mandatory and conditional flags, exit code conventions, stderr discipline, and output that's parseable JSON by default so agents never parse prose
- Scaffolds new tools from a PEP 723 template with argparse, `--format json/text/csv`, structured error output and stub tests
- Detects O(n²) string concatenation, recompiled regexes and list-membership anti-patterns via AST analysis + optional cProfile profiling

> Python only. Agent tools in TypeScript, Bash or another language need a separate contract enforcer for that language's conventions — `skill-audit-ts` carries one for TypeScript.

Scripts live in `skills/agent-tool-builder/scripts/` and accept `--json` for machine-readable output.

| Script | Purpose |
|---|---|
| `validate_agent_tool.py` | Interface contract validation — flags, exit codes, output shape |
| `perf_check.py` | AST-based performance checker + optional cProfile profiling |
| `init_tool.py` | Scaffold a new agent tool from the bundled PEP 723 template |

</details>

---

<details>
  <summary>create-agents-for-repo</summary>

### create-agents-for-repo

Adds custom subagents to the repo it's run on and, where appropriate, wires them into that repo's skills and `CLAUDE.md` so they actually run. This keeps verbose output out of the main context window and moves work to cheaper models where something external — an exit code, a schema, a diff — decides whether it succeeded. It needs Python `>=3.14` for its own scripts; the target repo can be in any language.

**What it writes**
- `.claude/agents/*.md` with a narrowed tool grant, an explicit model, and a return contract that caps what comes back
- A `## Delegation` routing table in CLAUDE.md — the durable backbone, since it survives skill re-imports
- Call sites inside repo-local SKILL.md workflows, skipped for plugin-installed or symlinked skills where an edit would be reverted or would leak upstream

**How it runs**

The candidate hunt and the review of that hunt are themselves delegated to parallel subagents. The reviewer is adversarial and separate from the hunters: would a subagent actually be *good* at this, and is it cheaper than the simplest thing that would work? A `-q` flag, a pre-commit hook, a Makefile target, or the built-in `Explore` agent all beat a bespoke agent when they suffice, and "SIMPLER: add `-q`" is a legitimate verdict. It proposes the whole batch and stops for approval before writing anything, lists what it rejected so the bar is visible, and asks separately about Opus agents — those buy context isolation but no cost saving.

Don't run `/create-agents-for-repo` in this repo. The skills here are meant to travel between repos; the subagents it writes hardcode the local toolchain and deliberately don't.

</details>

---

<details>
  <summary>obsidian-metabind</summary>

### obsidian-metabind

Reads, authors, audits and refactors [Meta Bind](https://www.moritzjung.dev/obsidian-meta-bind-plugin-docs/) syntax — the input fields, view fields, buttons and embeds that make a note interactive. It is scoped tightly to that surface — 21 input field types, 17 input field arguments, 4 view field types, 14 button actions, a bind target grammar and two plugin APIs — and walks the vault itself, so it needs nothing else installed.

- `scan.py --list` inventories every declaration in the vault; `--check` validates them, `--strict` also flags bind targets naming a property that doesn't exist yet
- `rename.py --property` retargets a renamed frontmatter key across inline fields, fenced blocks, `js-view` headers and button `updateMetadata` YAML; `--path` fixes cross-note bind targets after a note moves, which renaming the file itself never touches
- `refresh_docs.py` regenerates `references/field-spec.json` from the plugin's own `FieldConfigs.ts` and `ButtonConfig.ts`, pinned to the version the vault actually has installed

Two things it deliberately won't do: rewrite identifiers inside `js` or `inlineJS` code — it reports those sites for you to review, because pattern-rewriting arbitrary JS eventually corrupts working code — and parse declarations with regex, since argument values legitimately contain brackets and commas (`option(80, Griffon [flying])`), so a declaration's extent comes from its host code span or fence, mirroring the plugin's own parser.

</details>

---

<details>
  <summary>az</summary>

### az

Drives the Azure CLI — inspecting, deploying and troubleshooting resources, and answering inventory or security questions about a subscription. Two scripts do the orienting and the lookup; `az` itself does the work.

- `az-preflight.py` — one call, always first. Returns CLI version and extensions, signed-in identity, tenant, active and other reachable subscriptions, resource groups, and **access posture** (`write` / `read-only` / `unknown`). Blockers carry the exact instruction for the user, so nothing gets guessed around
- `az-help.py` — the installed CLI's own help, compacted ~8x. `--tree <group>` walks nested commands, which plain `az -h` can't: it reveals one level at a time, so finding `az webapp config ssl bind` otherwise costs three round trips

The rest is operating discipline: project with `--query` (a bare `az webapp list` is tens of thousands of tokens), pass `-o` explicitly since the user's config can override the default, confirm every mutation before running it, honour a `read-only` posture rather than routing around an `AuthorizationFailed`, and never touch global state (`az account set`, `az configure`, unattended `az login`). References cover recipes, KQL for Resource Graph / Log Analytics / Application Insights, and error-code troubleshooting.

| Script | Purpose |
|---|---|
| `az-preflight.py` | Session orientation — identity, subscriptions, access posture, blockers |
| `az-help.py` | Compacted `az` help lookup; `--tree` for nested command groups |

</details>

---

<details>
  <summary>python-performance</summary>

### python-performance

Finds and fixes slow Python. One script does both halves of the job: static analysis of the patterns whose cost grows with the input, and a cProfile run for when nothing static explains it.

- Flags the shapes that actually dominate Python slowness — quadratic string and bytes concatenation, a list drained with `pop(0)`, linear-scan membership tests, `sorted(...)[:n]` to answer a top-n question, `list(rows)[:10]` over a generator, regexes and `open()` and sorts repeated inside loops, `iterrows()` on a DataFrame, and a costly module-scope import that only one function uses
- **Every finding explains itself.** Each carries the cost mechanism, the measured impact where one has been benchmarked, and the specific rewrite — so there's no companion document to load and nothing to interpret from a bare category name. `--explain` prints the same detail for every check, plus the patterns it deliberately stays quiet about and why (cached method lookups, `itertools.groupby`, `itertools.tee`)
- Findings are grouped by category and severity, so a file with twenty occurrences of one problem reads as one explained problem, not twenty lines of noise
- `--profile <script.py> -- <args>` runs cProfile sorted by cumulative time with the script's own frames highlighted, for when the static pass comes back clean — or with nothing above LOW, which is the same answer and the same next step

> Deliberately thin on prose. Profiling and benchmarking are things a capable agent already knows how to do; the skill exists to make sure the cheap check happens first and the fix gets measured, not to re-teach `timeit`.

| Script | Purpose |
|---|---|
| `perf_check.py` | Self-explaining AST performance checker (`--explain` for the full check list) + cProfile profiling |

</details>

---

<details>
  <summary>architecture, plan, tdd, refactor</summary>

## These skills are designed to be used together

The `architecture` and `tdd` skills have been adapted for my needs from Matt Pocock's [Skills for Agents](https://github.com/mattpocock/skills), check his repo out, it's awesome. The refactor skill is adapted from Addy Osmani's [Agent Skills](https://github.com/addyosmani/agent-skills), also good to review.

They assume you are working in a python codebase - you'll need to update them for anything else. They also assume you are using: `pyright` for type safety, `pytest` for testing, and `ruff` for linting/sast/etc. These are all pretty solid choices.

The cycle for use should be:

1. After running `/init` on a repo, use `/architecture` write ADRs, create `CONTEXT-MAP.md`
2. `/plan` create a plan for a feature (with a smart model like Opus)
3. `/tdd` test driven development, for building stuff (with a workhorse model like Sonnet)
4. `/refactor` to simplify and refactor the work that has been done
5. Optionally, `/architecture` to review an existing codebase for ADR violations, or look for deepening opportunities.

</details>

---

## Installing

<details>
  <summary>Install Details</summary>

### Option 1

Use a recent version of the **GitHub CLI** and run `gh skill install rafaelh/skills <skillname>`. This will copy the skill into your target repo, or global directory (you'll be prompted for your choice). At a later date running `gh skill update rafaelh/skills <skillname>` will pull an updated version of this skill.

### Option 2

This repo is a Claude Code plugin marketplace. From inside Claude Code, add the marketplace and install whichever skills you need:

```
/plugin marketplace add rafaelh/skills
/plugin install skill-audit@rafaelh
/plugin install skill-audit-ts@rafaelh
/plugin install agent-tool-builder@rafaelh
/plugin install create-agents-for-repo@rafaelh
/plugin install architecture@rafaelh
/plugin install plan@rafaelh
/plugin install tdd@rafaelh
/plugin install refactor@rafaelh
/plugin install obsidian-metabind@rafaelh
/plugin install az@rafaelh
/plugin install python-performance@rafaelh
/reload-plugins
```

Once installed, skills activate automatically based on context — `skill-audit` or `skill-audit-ts` when you ask Claude to audit a SKILL.md (pick based on whether your bundled scripts are Python or TypeScript); `agent-tool-builder` when you ask Claude to write or improve a Python script an agent will call. `skill-audit` and `skill-audit-ts` cover overlapping ground by design — their descriptions each carry an explicit "NOT for X — see Y" disambiguator so only one activates per request. `obsidian-metabind` carries the same kind of disambiguator, so it activates on `INPUT[` / `VIEW[` / `BUTTON[` / a `meta-bind` fence rather than on general vault work.

After installing `skill-audit-ts`, run `npm ci` once inside `skills/skill-audit-ts/` to resolve `tsx`/`typescript`/`vitest` from the committed lockfile.

## Requirements

**skill-audit / agent-tool-builder / create-agents-for-repo / obsidian-metabind / az / python-performance (Python):**
- Python 3.14+ (all bundled scripts are stdlib-only except where PEP 723 metadata declares third-party deps)
- `ANTHROPIC_API_KEY` in environment (optional — enables exact token counts via the SDK)

**skill-audit-ts (TypeScript):**
- Node.js 18.3+ (20+ recommended), plus a one-time `npm ci` in the skill directory
- `ANTHROPIC_API_KEY` in environment (optional — enables exact token counts via `@anthropic-ai/sdk`)

**az:**
- The Azure CLI on PATH, and a signed-in session (`az login`) — `az-preflight.py` reports the install command and login instruction when either is missing

**Both audit skills:**
- Claude Code CLI (for trigger evals and description optimization)

</details>
