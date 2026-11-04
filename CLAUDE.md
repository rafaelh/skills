# CLAUDE.md

## What this repo is

A Claude Code plugin marketplace of Agent Skills that comply with (and enforce) the
[agentskills.io](https://agentskills.io/) spec. Not a distributable library: `package = false`,
scripts run in place by path, nothing publishes to PyPI or npm.

`skills/` holds one plugin per skill; `plugins/` holds bundles — today `ai-sdlc` (the four `spec-*`
skills and two `critic-*` agents) — and mods like `session` (a hooks module, no SKILL.md). All are
listed in `.claude-plugin/marketplace.json`. The bundle installs only as a whole; `gh skill install`
of a `spec-*` skill is unsupported. `.claude/skills/` symlinks the subset active while working
*in* this repo. `.gitignore` ignores only `.claude/settings.local.json`, so the symlinks and
`.claude/settings.json` are tracked. The real dirs there are `run-skills/` (the smoke driver, not
published) and `skill-creator/` (vendored).

`.claude/skills/ai-sdlc` links to `plugins/ai-sdlc` and loads as `ai-sdlc@skills-dir` with the same
`ai-sdlc:` names as an install; edits apply next session or on `/reload-plugins`.
`.claude/settings.json` disables the installed `ai-sdlc@rafaelh` here so it can't outrank the link;
a `settings.local.json` re-enabling it would.

Script-bearing skills — held to the contracts below:

| Skill | Language | Role |
|---|---|---|
| `skill-audit` | Python | Audit / eval SKILL.md files with Python scripts; owns the agent-tool validators |
| `skill-audit-ts` | TypeScript | Same workflow, for skills whose scripts are TypeScript |
| `create-agents-for-repo` | Python | Fit `.claude/agents/*.md` subagents to a *target* repo, wire their call sites |
| `az` | Python | Orient an Azure session, look up `az` command syntax |
| `python-performance` | Python | Slow Python: static checks, cProfile, benchmark driver |

The rest (`architecture`, `plan`, `refactor`, `review-repo-agents`, `tdd`, `ai-sdlc`) are prose-only
— no `scripts/`, so the agent-tool contract does not apply. `create-agents-for-repo` writes
subagents into a *consuming* repo and deliberately hardcodes its toolchain; skills travel, those
don't.

Eval harnesses live in `evals/<skill>/`, outside the shipped plugin, following
[eval-approach.md](evals/eval-approach.md) — read it before touching one. Four shapes by what a run
leaves behind: artifact (`create-agents-for-repo`, `refactor`, `python-performance`: staged repos,
diffed; `review-repo-agents`: the review itself), conversation (`plan`: a simulated interview,
graded on the transcript), call log (`az`: a fake `az` on PATH logs each call; the rubric grades
the commands chosen), trigger (a labeled query set for `eval_triggers.py`; no suite today).
`refactor`, `az` and `review-repo-agents` drive their own runs via `run_case.py --safe-mode` (the
first two grant Edit/Write/Bash, the last is read-only). Shared plumbing: `evals/shared/`.

## Commands

Python (repo root, uv-managed venv at `.venv`):

```bash
uv sync
uv run pytest [path::Class::test]
uv run ruff check . --fix && uv run ruff format .
uv run pyright                         # strict over skills/ and tests/
uv run pre-commit run --all-files      # ruff + pyright + hygiene
uv run python3 .claude/skills/run-skills/smoke.py [--tests]   # self-check; needs claude
```

TypeScript (`skills/skill-audit-ts/`, one-time `npm ci`):

```bash
npm test              # vitest run; add `-t "name"` for one
npm run typecheck     # likewise lint, format
```

## Architecture

### Skill layout is a contract, not a convention

A skill is `SKILL.md` + optional `scripts/` / `references/` / `assets/` + its own `plugin.json`
under `.claude-plugin/`. `validate_skill.py` enforces that frontmatter `name` equals the
parent directory name and that every `references/*.md` link and
`` `scripts/*.py` `` mention resolves. `description` caps at 1024 chars.

Adding a skill means editing **two** manifests — the root `.claude-plugin/marketplace.json` (keyed
by `source: ./skills/<name>`) and the skill's own `.claude-plugin/plugin.json` — then symlinking it
into `.claude/skills/`. There is no plugin manifest at the repo root; the root is the marketplace.
A skill in the bundle is just `plugins/ai-sdlc/skills/<name>/SKILL.md`: no manifest of its own, no
marketplace entry. Each plugin versions independently, and a change under `plugins/ai-sdlc` must
raise its `plugin.json` version. `smoke.py --only bundle` enforces that, exact bundle contents,
and that its skills name only agents and commands it provides.

### Scripts are agent tools and are validated as such

Every bundled script is subject to the interface contract in
[interface-contract.md](skills/skill-audit/references/interface-contract.md), machine-checked
by `validate_agent_tool.py`:

- `--format json|text`, `--json` as shorthand, `--quiet` to suppress informational stderr.
- Exit codes: `0` success, `1` user error, `2` system error, `3` not-found/empty. Never make the
  agent parse text to tell "nothing matched" from "it broke"; never exit `126`+ (the shell's range).
- Argparse-based; no `input()`, no free-form stdout errors.
- Library modules that are *not* agent tools carry `# agent-tool: false` in the first 10 lines so
  the validator skips them.

The contract prescribes a JSON default; most scripts here default to `text` because their audience
is a human reading validator output — deliberate, keep it. Run skill-audit's
`validate_agent_tool.py` and `perf_check.py` on every new script.

### Cross-skill dependency

`skill-audit` ships the contract, `validate_agent_tool.py` and `perf_check.py`; `skill-audit-ts`
folds in its own equivalents so it runs without Python.

`python-performance` deliberately forks `skill-audit`'s `perf_check.py`, folding `perf-findings.md`
into the script so findings explain themselves, and scoring severity by cost growth, not per-call
agent overhead. Don't mirror changes.

### Python/TypeScript parity

`skill-audit` and `skill-audit-ts` are twins: same script names, modes (Audit / Eval), OWASP AST##
finding codes and parallel `references/`. Mirror behavioral changes across both.
Legitimate divergence: perf checks (Python AST vs TS compiler API), security script-construct
checks (`pickle`/`shell=True` vs `eval()`/`{shell: true}`), pinning (PEP 723 vs `package.json`).

Python scripts import siblings flatly (`from skill_lib import ...`) because they run as
`python3 path/to/script.py`; each `tests/conftest.py` bootstraps `sys.path`. Test placement differs:
`skill-audit` in `scripts/tests/`, repo-level checks in top-level `tests/`, TypeScript co-located
`*.test.ts`. Python tests are black-box: run the script under `subprocess`, assert on JSON stdout +
exit code.

### Descriptions are tuned artifacts

Sibling skills overlap by design, so sibling pairs end each `description` with an explicit
disambiguator (`NOT for skills whose bundled scripts are TypeScript — use skill-audit-ts for that`).
`detect_skill_overlap.py` compares similarity only (≥ 0.5 flags a pair); the disambiguator is a
convention, not checked. Preserve it and the concrete trigger phrases when editing — they were
measured by `eval_triggers.py`, not written for prose.

SKILL.md bodies write `${SKILL_DIR}` for the skill's own directory — notation, not a shell
variable; Claude Code resolves it from `${CLAUDE_SKILL_DIR}`.

## Conventions

Ruff runs a wide select list (`S` bandit, `PERF`, `TRY`, `PL`, `ERA`) at line-length 100,
`target-version = py314`. Exceptions go in `[tool.ruff.lint.per-file-ignores]` in `pyproject.toml`
**with a comment explaining why**, not as inline `# noqa`. Pyright is `strict` over `skills/` and `tests/`.

**Comments and docs carry intent, not history or restatement.** Keep the *why* — a workaround, a
vendor quirk, a non-obvious constraint. Drop what the line already says; never narrate the change
("renamed from", "new in v2") — git holds that. Strip such detail when you find it.

`README.md`, `SKILL.md` bodies, and this file are the doc surface; `docs/` holds dated eval
benchmark records, and `docs/specs/` the specs written by the `ai-sdlc` workflow. Update whatever your change makes wrong, in the same change. Keep this file
under 8 KB.
