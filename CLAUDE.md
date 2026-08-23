# CLAUDE.md

## What this repo is

A Claude Code plugin marketplace of Agent Skills that comply with (and enforce) the
[agentskills.io](https://agentskills.io/) spec. Not a distributable library: `package = false`,
scripts run in place by path, nothing publishes to PyPI or npm.

`skills/` is the single source for every skill; each is a published plugin listed in
`.claude-plugin/marketplace.json`. `.claude/skills/` symlinks the subset active while working *in*
this repo. `.gitignore` excludes `.claude/*` but re-includes `.claude/skills/`, so those symlinks
are tracked source and local settings are not. The one non-symlink is `run-skills/`, the repo's
own smoke driver — deliberately not a published plugin.

Script-bearing skills — held to the contracts below:

| Skill | Language | Role |
|---|---|---|
| `skill-audit` | Python | Audit / eval SKILL.md files whose bundled scripts are Python |
| `skill-audit-ts` | TypeScript | Same workflow, for skills whose scripts are TypeScript |
| `agent-tool-builder` | Python | Build & audit Python scripts that agents call as tools |
| `create-agents-for-repo` | Python | Fit `.claude/agents/*.md` subagents to a *target* repo, wire their call sites |
| `obsidian` | Python | An Obsidian vault: notes, frontmatter, wikilinks, canvas, bases |
| `obsidian-metabind` | Python | Meta Bind syntax in a vault: read, author, validate, refactor |
| `az` | Python | Orient an Azure session, look up `az` command syntax |

The rest (`architecture`, `plan`, `refactor`, `tdd`) are prose-only — no `scripts/`, so the
agent-tool contract does not apply. `create-agents-for-repo` operates on a *consuming* repo rather
than on skills: skills travel between repos, the subagents it writes deliberately do not — they
hardcode the local toolchain.

Eval harnesses: `evals/create-agents-for-repo/` (fixture repos, staging,
grader) and `skills/plan/evals/`, which drives a simulated interview — a conversation leaves no
artifact to diff; read its README first. `skills/obsidian-metabind/evals/` is just a labeled query
set for `eval_triggers.py`.

## Commands

Python (repo root, uv-managed venv at `.venv`):

```bash
uv sync                                # dev deps: pytest, ruff, pyright
uv run pytest [path::Class::test]      # omit the path for the whole suite
uv run ruff check . --fix && uv run ruff format .
uv run pyright                         # strict over skills/
uv run pre-commit run --all-files      # ruff + ruff-format + pyright + hygiene
```

TypeScript (`skills/skill-audit-ts/`, one-time `npm ci`):

```bash
npm test              # vitest run; add `-t "name"` for one
npm run typecheck     # tsc --noEmit
npm run lint          # eslint
npm run format        # prettier --write
```

## Architecture

### Skill layout is a contract, not a convention

A skill is `SKILL.md` + optional `scripts/` / `references/` / `assets/` + its own
`.claude-plugin/plugin.json`. `validate_skill.py` enforces that frontmatter `name` equals the
parent directory name (`validate.name.dir-mismatch`) and that every `references/*.md` link and
`` `scripts/*.py` `` mention resolves — so renaming a directory breaks validation until the
frontmatter follows. `description` caps at 1024 chars.

Adding a skill means editing **two** manifests — the root `.claude-plugin/marketplace.json` (keyed
by `source: ./skills/<name>`) and the skill's own `.claude-plugin/plugin.json` — then symlinking it
into `.claude/skills/`. There is no plugin manifest at the repo root; the root is the marketplace.
Skills version independently.

### Scripts are agent tools and are validated as such

Every bundled script is subject to the interface contract in
[interface-contract.md](skills/agent-tool-builder/references/interface-contract.md), machine-checked
by `validate_agent_tool.py`:

- `--format json|text`, `--json` as shorthand, `--quiet` to suppress informational stderr.
- Exit codes: `0` success, `1` user error, `2` system error, `3` not-found/empty. Never make the
  agent parse text to tell "nothing matched" from "it broke".
- Argparse-based; no `input()`, no free-form stdout errors.
- Library modules that are *not* agent tools carry `# agent-tool: false` in the first 10 lines so
  the validator skips them.

The contract prescribes a JSON default; most scripts here default to `text` because their audience
is a human reading validator output. That deviation is deliberate — keep it. This repo's tooling is
the spec for new scripts: run `validate_agent_tool.py` and `perf_check.py` on them.

### Cross-skill dependency

`skill-audit`'s SKILL.md invokes `../agent-tool-builder/scripts/validate_agent_tool.py` and
`perf_check.py` by relative path and links to `agent-tool-builder/references/perf-findings.md`;
moving those breaks the Python audit workflow. `skill-audit-ts` deliberately has **no** such
dependency — it folds in its own equivalents so it runs on machines without Python.

`obsidian` and `obsidian-metabind` are an explicit **non**-dependency: neither invokes the other,
and `obsidian-metabind`'s `parser.py` re-implements vault walking rather than import it, so a vault
with Meta Bind but no `obsidian` install still works. Both ship a flat `refresh_docs.py`, so each
`tests/conftest.py` reclaims its own bare module names from `sys.modules`; `.claude` is in
`norecursedirs` so symlinks aren't collected twice.

### Python/TypeScript parity

`skill-audit` and `skill-audit-ts` are twins: same script names, same modes (Audit / Eval), same
OWASP AST## finding codes, parallel `references/`. Mirror behavioral changes across both.
Legitimate divergence: perf checks (Python AST vs TS compiler API), security script-construct
checks (`pickle`/`shell=True` vs `eval()`/`{shell: true}`), pinning (PEP 723 vs `package.json`).

Python scripts import siblings flatly (`from skill_lib import ...`) because they run as
`python3 path/to/script.py`; each `tests/conftest.py` bootstraps `sys.path`. Test placement differs
per skill — `skill-audit` in `scripts/tests/`, `agent-tool-builder` in a top-level `tests/`,
TypeScript co-located `*.test.ts`. Python tests are black-box: invoke the script under
`subprocess`, assert on JSON stdout + exit code.

### Descriptions are tuned artifacts

Sibling skills overlap by design, so each `description` ends with an explicit disambiguator (`NOT
for skills whose bundled scripts are TypeScript — use skill-audit-ts for that`).
`detect_skill_overlap.py` flags sibling pairs at cosine ≥ 0.5 without one. Preserve the
disambiguator and the concrete trigger phrases when editing — they were measured by
`eval_triggers.py`, not written for prose.

SKILL.md bodies write `${SKILL_DIR}` for the skill's own directory — notation, not a shell
variable; Claude Code resolves it from `${CLAUDE_SKILL_DIR}`.

## Conventions

Ruff runs a wide select list (`S` bandit, `PERF`, `TRY`, `PL`, `ERA`) at line-length 100,
`target-version = py314`. Exceptions go in `[tool.ruff.lint.per-file-ignores]` in `pyproject.toml`
**with a comment explaining why**, not as inline `# noqa`. Pyright is `strict` over `skills/`.

**Abstraction is opt-in.** Its cost is concepts a reader must hold — functions, parameters,
branches, files, config keys — not lines. A helper earns its keep through repeated use; until then,
change the call sites. Grep first: a near-miss you extend beats a new one alongside. Don't compress
by density either — one wide line doing three things costs more than three doing one each.

**Keep diffs scoped.** No drive-by restructuring of code the task didn't touch. Deletion is the
exception: remove grep-verified dead code inside functions you're already editing. Anything larger
is a `refactor` pass.

**Comments and docs carry intent, not history or restatement.** Keep the *why* — a workaround, a
vendor quirk, a non-obvious constraint. Drop what the line already says and never narrate the
change ("renamed from", "new in v2"); git holds that. Strip such detail when you find it.

`README.md`, `SKILL.md` bodies, and this file are the doc surface; `docs/` holds only dated eval
benchmark records. Update whatever your change makes wrong, in the same change. Keep this file
under 8 KB.
