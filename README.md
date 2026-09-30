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

Audits Claude Agent Skills to the https://agentskills.io spec and OWASP guidelines. Consider using
this skill when adjusting your other agent skills, in between rounds of evals with Anthropic's
`skill-creator`.

### skill-audit-ts

A typescript version of the same skill.

</details>

---

<details>
  <summary>agent-tool-builder</summary>

### agent-tool-builder

Don't use this for now - it need refinement. Builds and reviews **Python** scripts intended to be
called by AI agents as tools. Enforces a standard interface contract — structured JSON output,
predictable exit codes, `--format`, `--quiet`, `--dry-run` — and catches performance anti-patterns
before they cost agent round-trips.

- Runs a decision-forcing design interview — data model, operations, flag set, JSON output shape,
failure modes — before a line of code gets written
- Validates the contract: mandatory and conditional flags, exit code conventions, stderr discipline,
and output that's parseable JSON by default so agents never parse prose
- Scaffolds new tools from a PEP 723 template with argparse, `--format json/text/csv`, structured
error output and stub tests
- Detects O(n²) string concatenation, recompiled regexes and list-membership anti-patterns via AST
analysis + optional cProfile profiling

> Python only. Agent tools in TypeScript, Bash or another language need a separate contract enforcer
> for that language's conventions — `skill-audit-ts` carries one for TypeScript.

</details>

---

<details>
  <summary>create-agents-for-repo</summary>

### create-agents-for-repo

Adds custom subagents to the repo it's run on and, where appropriate, wires them into that repo's
skills and `CLAUDE.md` so they actually run. This keeps verbose output out of the main context
window and moves work to cheaper models where something external — an exit code, a schema, a diff
— decides whether it succeeded. It needs Python `>=3.14` for its own scripts; the target repo can be
in any language.

**What it writes**
- `.claude/agents/*.md` with a narrowed tool grant, an explicit model, and a return contract that
caps what comes back
- A `## Delegation` routing table in CLAUDE.md — the durable backbone, since it survives skill
re-imports
- Call sites inside repo-local SKILL.md workflows, skipped for plugin-installed or symlinked skills
where an edit would be reverted or would leak upstream

**How it runs**

The candidate hunt and the review of that hunt are themselves delegated to parallel subagents. The
reviewer is adversarial and separate from the hunters: would a subagent actually be *good* at this,
and is it cheaper than the simplest thing that would work? A `-q` flag, a pre-commit hook, a
Makefile target, or the built-in `Explore` agent all beat a bespoke agent when they suffice, and
"SIMPLER: add `-q`" is a legitimate verdict. It proposes the whole batch and stops for approval
before writing anything, lists what it rejected so the bar is visible, and asks separately about
Opus agents — those buy context isolation but no cost saving.

Don't run `/create-agents-for-repo` in this repo. The skills here are meant to travel between repos;
the subagents it writes hardcode the local toolchain and deliberately don't.

</details>

---

<details>
  <summary>az</summary>

### az

Drives the Azure CLI — inspecting, deploying and troubleshooting resources, and answering inventory or security questions about a subscription. Two scripts do the orienting and the lookup; `az` itself does the work.

- `az-preflight.py` — one call, always first. Returns CLI version and extensions, signed-in identity, tenant, active and other reachable subscriptions, resource groups, and **access posture** (`write` / `read-only` / `unknown`). Blockers carry the exact instruction for the user, so nothing gets guessed around
- `az-help.py` — the installed CLI's own help, compacted ~8x. `--tree <group>` walks nested commands, which plain `az -h` can't: it reveals one level at a time, so finding `az webapp config ssl bind` otherwise costs three round trips

The rest is operating discipline: project with `--query` (a bare `az webapp list` is tens of thousands of tokens), pass `-o` explicitly since the user's config can override the default, confirm every mutation before running it, honour a `read-only` posture rather than routing around an `AuthorizationFailed`, and never touch global state (`az account set`, `az configure`, unattended `az login`). References cover recipes, KQL for Resource Graph / Log Analytics / Application Insights, and error-code troubleshooting.

</details>

---

<details>
  <summary>python-performance</summary>

### python-performance

Finds and fixes complex functions that slow down Python code. It augments the checks that `ruff`
does for performance rather than duplicating. It falls back to profiling an application if its
scripts don't get a match for one of the known slow patterns.

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
/plugin install az@rafaelh
/plugin install python-performance@rafaelh
/reload-plugins
```

</details>
