# Spec: `ai-sdlc` plugin

## Goal

So the spec workflow can be used in any repo and improved in one place, a user can install it from
the `rafaelh` marketplace in one step and run define → design → develop → verify end to end, while
this repo uses and checks the same source of truth.

**Constraint:** the four `spec-*` skills (`spec-define`, `spec-design`, `spec-develop`,
`spec-verify`) and two `critic-*` agents (`critic-specification`, `critic-architecture`) are bundled
as they are. Their content changes only where behaviour 2, 3 or 4 cannot otherwise be met.

## Behaviours

1. **One install.** The `rafaelh` marketplace lists a plugin called `ai-sdlc`. Installing it gives
   the user the four `spec-*` skills and the two `critic-*` agents, and nothing else.

2. **Works on its own once installed.** In a repo where `ai-sdlc` is the only plugin installed from
   this marketplace:
   - `spec-define` successfully launches `critic-specification`.
   - `spec-design` successfully launches `critic-architecture`.
   - Every slash command an `ai-sdlc` skill tells the user to type, whether as a next step or a
     redirect, can be typed in that repo. `/simplify`, `/clear` and `/code-review` count as built
     into Claude Code.

   If that repo defines its own agent named `critic-specification` or `critic-architecture`, the
   skills launch the repo's own agent instead.

3. **One tracked source.** Each skill and agent has exactly one tracked copy of its content. Any
   other tracked entry is a link to that copy. In this repo, whether or not `ai-sdlc` is also
   installed at user scope:
   - A new session uses that copy, so an edit takes effect without a copy or install step.
   - The skills launch their critics.
   - Every command the skills tell the user to type works here too.

   If no single wording of a hand-off or critic launch works both here and when installed
   (behaviour 2), this repo enables its own `ai-sdlc` plugin automatically. An edit to the tracked
   copy must still take effect without a manual copy or install step.

4. **Checked like every other skill.** The repo's self-check is the one that already validates every
   published skill. After this change, **the whole self-check passes**, and:
   - It names each of the four `ai-sdlc` skills individually. Neither the Python nor the TypeScript
     validator reports a failure or warning for any of them, and there is no parity mismatch.
   - It includes an overlap check, which compares each `ai-sdlc` skill against every other skill in
     the marketplace, including `plan` and each other. It fails if any pair that includes an
     `ai-sdlc` skill scores at or above the threshold.
   - It validates both critic agent definitions, and a malformed or unnamed one is a failure.
   - It fails if what the marketplace lists `ai-sdlc` as containing and what the bundle actually
     contains don't match. Examples: a skill or agent the bundle no longer has, or one present in
     only one of the two.
   - It fails if an `ai-sdlc` skill launches an agent the bundle doesn't provide.
   - It fails if an `ai-sdlc` skill tells the user to type a slash command that is neither an
     `ai-sdlc` skill nor `/simplify`, `/clear` or `/code-review`.
   - It fails if any `ai-sdlc` skill or agent has changed since the bundle version last changed.
   - Breaking an `ai-sdlc` skill on purpose makes the self-check fail. Breaking includes at least:
     malformed frontmatter, a name that doesn't match its directory, a dangling reference link, or
     any of the cases above.

5. **Existing plugins still install.** Every plugin in the marketplace other than
   `agent-tool-builder` can still be installed as before, and its workflows still run.
   - `agent-tool-builder` is no longer listed or offered for install anywhere.
   - Nothing that remains runs it, links to it, or tells the user or Claude to use it. Passing
     mentions in prose may stay.
   - `review-repo-agents` is published as a plugin in the marketplace.
   - Incidental fixes and improvements to existing skills made along the way are acceptable.

6. **One version.** `ai-sdlc` has a single version for the whole bundle. Any change to one of its
   skills or agents ships with a new bundle version, so existing installs receive the change when
   they update.

7. **Documented.** README and CLAUDE.md:
   - describe `ai-sdlc` as the one plugin bundling several skills and agents, and give its install
     command
   - state that it is installed only as a whole; installing individual `spec-*` skills (for example
     with `gh skill install`) is unsupported
   - allow `docs/specs/` to hold specs written by this workflow
   - no longer contain statements this change makes false, or that are already false in the areas
     it touches. These include:
     - one plugin per skill
     - per-skill versioning
     - how a skill is added
     - the claim that every skill's description carries a disambiguator
     - what is tracked or linked under the repo's local Claude configuration
     - `agent-tool-builder`

   CLAUDE.md is at most 8,192 bytes.

# Design

## Verified facts this design rests on

- Plugin components are always namespaced. Installed, the skills are `/ai-sdlc:spec-design` and so on, and
  the agents are `ai-sdlc:critic-specification` and so on (code.claude.com plugins reference).
- A directory holding `.claude-plugin/plugin.json` under a project's `.claude/skills/` loads in place as
  `<name>@skills-dir`. Edits apply at the next session start or `/reload-plugins`. This repo's
  `.claude/skills/plan` symlink already loads as `plan@skills-dir`.
- An installed marketplace plugin outranks a skills-dir plugin with the same name. Project
  `.claude/settings.json` `enabledPlugins` overrides user settings, and `settings.local.json`
  overrides project settings.
- In `plugin.json`, a `version` pins installs until it changes. The `agents` key replaces the default
  `agents/` scan, and the `skills` key adds to the default `skills/` scan.

## Decisions

| # | Decision | Answer | Why |
|---|---|---|---|
| 1 | Where the bundle lives | `plugins/ai-sdlc/` with `.claude-plugin/plugin.json` (`name: ai-sdlc`, `version: 0.1.0`, description, author), `skills/spec-{define,design,develop,verify}/SKILL.md`, `agents/critic-{specification,architecture}.md`. No component keys in `plugin.json`, so default scans apply | User wanted it separate from `skills/`. Default scans mean the directory is the only inventory |
| 2 | What "listed as containing" means (B1 "nothing else", B4 mismatch) | The bundle's directory is its listing. The self-check enforces exact contents: top-level entries ⊆ {`.claude-plugin`, `skills`, `agents`}; every `skills/*/` holds a `SKILL.md`; every `agents/*` is an `.md`; any component key (`skills`/`agents`/`commands`/`hooks`/`mcpServers`/…) appearing in `plugin.json` or the marketplace entry is a failure | No second inventory to drift. A stray `commands/` or `hooks/` fails instead of shipping silently |
| 3 | Marketplace | Add `ai-sdlc` (`source: ./plugins/ai-sdlc`). Add `review-repo-agents` with a new `.claude-plugin/plugin.json` (`0.1.0`). Remove `agent-tool-builder` | B1, B5 |
| 4 | In-repo use (B3) | Symlink `.claude/skills/ai-sdlc` → `../../plugins/ai-sdlc`. Delete `.claude/skills/spec-*` and `.claude/agents/`. New tracked `.claude/settings.json`: `{"enabledPlugins": {"ai-sdlc@rafaelh": false}}` | Loads as `ai-sdlc@skills-dir` with the same namespaced names as an install, so one wording works in both places. The project `false` stops a user-scope install outranking the in-repo copy. A `settings.local.json` `true` would bring that install back, which CLAUDE.md notes |
| 5 | Forced skill edits (the only content changes) | Hand-offs `/spec-X` → `/ai-sdlc:spec-X` (spec-define ×2, spec-design ×1, spec-develop ×2). Critic launch in spec-define step 3 and spec-design step 6 becomes: "launch the `critic-specification` agent defined in this repo or your user config if there is one, otherwise `ai-sdlc:critic-specification`" (same for architecture). spec-verify, descriptions and agent files are unchanged | B2 namespacing. A same-named project critic wins (a user-level one also does, which is acceptable). Overlap passes today (max 0.433; spec-design vs plan 0.41) |
| 6 | Self-check | Extend `.claude/skills/run-skills/smoke.py`; see below | It is the run that already validates every published skill |
| 7 | agent-tool-builder | Fold into skill-audit. Restore from `HEAD` `validate_agent_tool.py` and `perf_check.py` → `skills/skill-audit/scripts/`, their tests → `skills/skill-audit/scripts/tests/` (only `SCRIPT` paths change), `perf-findings.md` and `interface-contract.md` → `skills/skill-audit/references/` (no TS mirror: the contract is Python-specific). Drop `init_tool.py`, the template, the other references and the empty `skills/agent-tool-builder/` | User choice. Gives real parity with skill-audit-ts, which already ships `validate_agent_tool.ts`/`perf_check.ts`/`perf-findings.md`. Also fixes `${SKILL_DIR}/../agent-tool-builder` paths, which never resolved for a marketplace install |
| 8 | Versioning | `ai-sdlc` starts at `0.1.0`. The self-check requires a strictly higher version (dotted-int compare) when bundle content changes. Bump the `skill-audit` and `create-agents-for-repo` versions for this change | B6. Matches the existing `0.1.0` convention |
| 9 | B2 verification | Static checks plus a manual run in `/spec-verify` (below) | User choice |

## Self-check changes (`smoke.py`)

- **`--repo PATH`**, defaulting to the script's own checkout. This separates *what is checked* (the
  target repo) from *where the tools live* (the validators in the script's checkout), so tests can
  point it at a small fixture.
- **Published skills** = every `skills/*/` holding a `SKILL.md`, plus every `plugins/*/skills/*/`.
  Check labels read `ai-sdlc/spec-define`. Self-audit (Python and TS, fail=0 warn=0) and parity iterate
  this list, so each bundle skill is named individually.
- **`manifests` group** stops using the skill list (bundle skills have no `plugin.json`). For each
  marketplace entry, the `source` exists and holds a `plugin.json` whose `name` equals the entry name.
  Every `skills/*/` with a `SKILL.md` and every `plugins/*/` must be listed, so nothing is stray in
  either direction.
- **New `bundle` group** (`--only bundle`), run for each `plugins/<p>/`:
  - **contents**: the exact-contents rule from decision 2.
  - **plugin-validate**: `claude plugin validate --strict plugins/<p>`. Fall back to non-strict only if
    metadata-only warnings make strict unusable, and record that.
  - **agents**: `validate_agent_def.py plugins/<p>/agents --json`, parsing `meta.fail`/`meta.warn`
    (not `summary`), with fail=0 and warn=0.
  - **refs**: scan each SKILL.md's backticked spans.
    - A span that *is* a slash command (`^/[a-z][a-z0-9-]*(:[a-z0-9-]+)?$`, so paths like `/home/…`
      never match) must be `/<p>:<bundle skill>` or one of `/simplify`, `/clear`, `/code-review`.
    - A span shaped `^[a-z0-9-]+:[a-z0-9-]+$` must be `<p>:<bundle agent>`. This also catches other
      plugins' agents.
    - A bare span within a few words of "agent" must be a bundle agent name.
    - Text outside backticks is out of scope; all hand-offs are backticked.
  - **overlap**: build a temp dir of symlinks to every published skill, run
    `detect_skill_overlap.py --json`, and fail if any pair at or above the threshold includes a bundle
    skill. Skill names must be unique across both trees, since pairs are keyed by name; the check
    asserts this.
  - **version**: B = `git log -1 --format=%H -G'"version"' -- plugins/<p>/.claude-plugin/plugin.json`.
    - Pass if `plugin.json` isn't committed yet.
    - Pass if the working-tree version is strictly higher than `HEAD`'s.
    - Otherwise fail if `git diff B -- plugins/<p>` (excluding `plugin.json`) is non-empty, or if
      untracked files exist under `plugins/<p>`.
    - If B can't be resolved (e.g. a shallow clone), fail with a clear detail, not a traceback.
- **Toolchain gating per group**: `uv` always; node/tsx only for `ts` and `parity`; `claude` only for
  `bundle`.

## Files touched

- **New:**
  - `plugins/ai-sdlc/**` (moved from `.claude/skills/spec-*` and `.claude/agents/*`)
  - `.claude/skills/ai-sdlc` (symlink)
  - `.claude/settings.json`
  - `skills/review-repo-agents/.claude-plugin/plugin.json`
  - `skills/skill-audit/scripts/{validate_agent_tool,perf_check}.py` plus their tests
  - `skills/skill-audit/references/{perf-findings,interface-contract}.md`
  - `tests/test_smoke.py`
  - `tests/test_docs.py`
- **Edited:**
  - `.claude-plugin/marketplace.json`
  - `.claude/skills/run-skills/{smoke.py,SKILL.md}` (paths, counts, `--repo`, `--only bundle`)
  - `skills/skill-audit/SKILL.md` (steps 4b/4c → `${SKILL_DIR}/scripts/…`, link →
    `references/perf-findings.md`)
  - `skills/skill-audit/scripts/recommend_scripts.py` (messages)
  - `skills/create-agents-for-repo/SKILL.md` (drop the "use agent-tool-builder" clause; overlap
    check confirms)
  - plugin versions for skill-audit and create-agents-for-repo
  - `skills/skill-audit-ts/references/perf-findings.md:25` and `skills/az/scripts/_common.py:5`
    (stale mentions)
  - `pyproject.toml`: move the agent-tool-builder per-file-ignores; add `tests/*.py` (S101, S603,
    S607) with reason comments; add `tests` to pyright `include`
  - `README.md`
  - `CLAUDE.md`
- **Deleted:** the `agent-tool-builder` tree (already deleted in the working tree), and
  `.claude/skills/spec-*` and `.claude/agents/`.

## Docs

- **README:**
  - Add an `ai-sdlc` section: the define→design→develop→verify workflow, the critics, and
    `/plugin install ai-sdlc@rafaelh`.
  - State that it is installed only as a whole, and that `gh skill install` of `spec-*` is unsupported.
  - Add a `review-repo-agents` install line.
  - Remove the agent-tool-builder section and its install line.
- **CLAUDE.md** (must end ≤ 8,192 bytes; it is 8,190 now).
  - **Cut:**
    - the agent-tool-builder table row
    - the `../agent-tool-builder/...` dependency paragraph
    - the agent-tool-builder clause in the test-placement sentence
    - a tightened commands block
  - **Fix:**
    - `.gitignore` only ignores `settings.local.json`
    - tracked real dirs under `.claude/skills/` are `run-skills/` and `skill-creator/`
  - **Add, tersely:**
    - `plugins/` holds multi-component bundles
    - each plugin versions independently, and an `ai-sdlc` bump is enforced
    - how to add a skill, including to the bundle
    - in-repo `ai-sdlc` loads via the symlink, with the `.claude/settings.json` override and the
      `settings.local.json` caveat
    - overlap compares similarity only; disambiguators are a convention for sibling pairs
    - the interface contract and perf tools live in skill-audit
    - python-performance forks skill-audit's `perf_check.py`
    - `docs/specs/` holds specs from this workflow

## Tests

`tests/test_smoke.py` is black-box. A module-scoped fixture builds a small target repo in `tmp_path`
(marketplace.json, a copy of `plugins/ai-sdlc`, `skills/plan`, `git init` + commit). Each test copies
it, breaks one thing, and runs `smoke.py --repo <copy> --only <group> --json`. Each test asserts the
exit code and which check failed. Tests needing `claude` or `tsx` are skipped when those are absent.

| Case | Group | Expect |
|---|---|---|
| bundle skill frontmatter `name` ≠ dir | `python` (not `parity`: equal fails pass parity) | fail |
| malformed bundle skill frontmatter | `python` | fail |
| dangling `references/` link in a bundle skill | `python` | fail (warn counts) |
| `ai-sdlc:critic-nope`; bare `` `critic-nope` agent ``; `other-plugin:agent` | `bundle` | fail |
| `` `/ai-sdlc:spec-nope` ``, `` `/foo` `` | `bundle` | fail; `` `/simplify` `` and `` `/home/x` `` pass |
| marketplace entry name ≠ `plugin.json` name; unlisted `plugins/x/`; missing `source` | `manifests` | fail |
| stray `plugins/ai-sdlc/commands/x.md`; empty `skills/foo/`; `agents` key in `plugin.json` | `bundle` | fail |
| agent with malformed frontmatter; agent with no `name` | `bundle` | fail |
| bundle skill whose description is copied from `plan` | `bundle` | fail (overlap) |
| committed skill edit, no bump; new untracked agent, no bump | `bundle` | fail |
| uncommitted bump; committed bump; version lowered | `bundle` | pass, pass, fail |
| clean fixture | each group | pass |

`tests/test_docs.py`: CLAUDE.md is ≤ 8,192 bytes. The folded agent-tool-builder tests run from their
new home. The whole real-repo smoke run is not a pytest test: it needs `npm ci` and `claude`, and it
fails by design mid-edit. `/spec-verify` runs it (`uv run python3 .claude/skills/run-skills/smoke.py
--tests` exits 0).

## Implementation order and manual verification

1. **Experiment first** (decision 4 depends on it):
   - Create the symlink and start a session here.
   - Confirm `/ai-sdlc:spec-define` and the `ai-sdlc:critic-specification` subagent type both appear,
     i.e. `agents/` loads from a skills-dir plugin.
   - If agents don't load this way, stop and revisit decision 4 with the user. The candidate fallback
     is `.claude/settings.json` `extraKnownMarketplaces` with a local directory source, which loads in
     place.
2. Move the files, make the forced edits, and update the manifests and settings.
3. Do the smoke changes and tests (TDD), then the agent-tool-builder fold.
4. Update the docs.
5. **Manual check in `/spec-verify`:**
   - **(a) Installed copy disabled here:** in an isolated `CLAUDE_CONFIG_DIR`, run
     `claude plugin marketplace add /home/rafael/git/skills` and `claude plugin install
     ai-sdlc@rafaelh` (user scope). Open this repo, edit a bundle skill, `/reload-plugins`, and
     confirm the edit is live (the skills-dir copy wins).
   - **(b) Works on its own:** in a scratch repo with only `ai-sdlc` installed, run
     `/ai-sdlc:spec-define` and `/ai-sdlc:spec-design`, and confirm each critic launches and each
     hand-off command exists.
   - **(c) Repo critic override:** repeat (b) with a repo-local `.claude/agents/critic-specification.md`
     and confirm that one is used.

## Out of scope

- Skill content changes beyond decision 5.
- Description tuning and trigger evals.
- Evals for `ai-sdlc`.
- Handling a critic that fails to launch.
- Supporting `gh skill install` of single `spec-*` skills.
- Scanning unbackticked prose for commands.
- Detecting a version lowered further back than the last two commits that changed `version`.
- A test for a real shallow clone. "Cannot resolve the last version change" is tested with a repo
  that has no `.git`; in a shallow clone the boundary commit is treated as the last change.
- The bare-name rule in the refs check only reads lowercase-hyphen spans within three words of
  "agent"; fenced code blocks are scanned like prose and are not special-cased.
- `uv run pre-commit run --all-files` fails its `ruff (legacy alias)` hook on
  `skills/az/tests/fixtures/fake-az` (PTH123). That file predates this change and is untouched;
  plain `uv run ruff check .` passes.

# Implementation (Develop)

**Experiment (design step 1).** With `.claude/skills/ai-sdlc` linked, a fresh headless session
(`claude -p`) listed `ai-sdlc:critic-specification`, `ai-sdlc:critic-architecture` and all four
`ai-sdlc:spec-*` skills, so `agents/` loads from a skills-dir plugin and decision 4 stands. That was
the model's own listing; the installed-copy checks (a)–(c) below are still manual.

**How it was built.**
- **Bundle:** `.claude/skills/spec-*` and `.claude/agents/*` moved to `plugins/ai-sdlc/` (`0.1.0`).
  `.claude/skills/ai-sdlc` links to it, and a new `.claude/settings.json` disables
  `ai-sdlc@rafaelh`. Only the decision 5 edits were made: five hand-offs namespaced, and the two
  critic launches reworded.
- **Self-check:** `smoke.py` gained `--repo`, the published-skills list, the new `manifests` logic,
  the `bundle` group (`contents`, `plugin-validate`, `agents`, `refs`, `overlap`, `version`) and
  per-group toolchain gating. `claude plugin validate --strict` passes as is, so there was no
  non-strict fallback.
- **agent-tool-builder:** `validate_agent_tool.py`, `perf_check.py`, their tests and the two
  references now live in `skill-audit`. The tree, its marketplace entry, and every remaining link
  to it are gone. `review-repo-agents` has a `plugin.json` and a marketplace entry. Versions:
  `skill-audit` 4.1.0, `create-agents-for-repo` 0.1.1.
- **Docs:** README, CLAUDE.md (8,141 bytes), and `run-skills/SKILL.md` updated.

**Tests** (`tests/test_smoke.py` unless noted; each copies a clean fixture, breaks one thing, and
asserts the exit code and the named check):

| Behaviour | Pinned by |
|---|---|
| 1 One install | clean fixture per group; contents cases (stray `commands/`, empty `skills/foo/`, `agents` key, marketplace component key); `test_layout.py` |
| 2 Works on its own | refs cases (5 failing, 5 passing); static only, the manual run is in `/spec-verify` |
| 3 One tracked source | manifests cases (name mismatch, unlisted plugin or skill, missing source); `test_layout.py` (link, settings, no second copy) |
| 4 Self-check | each bundle skill named in `python` and `parity`; python-group cases (name mismatch, malformed frontmatter, dangling link); agent cases; overlap and name-clash cases |
| 5 Existing plugins | `test_layout.py` (marketplace, no remaining links); the folded `skill-audit` tests; full pytest |
| 6 One version | edit with no bump (committed, uncommitted, untracked agent), uncommitted bump, committed bump, edit after a bump, version lowered (uncommitted and committed), bundle not yet committed, no `.git` |
| 7 Documented | `test_docs.py` (size, install command, whole-bundle rule, no `agent-tool-builder`, no stale claims) |

Toolchain gating has two tests (`manifests` runs without `claude` or `node`; `bundle` without
`claude` exits 2). Final state: 362 pytest, 185 vitest, ruff and pyright clean, and
`smoke.py --tests` 99/99.

**Deviations from the plan.**
- The fixture builds a synthetic bundle and `plan` rather than copying the real ones, so tests don't
  move with skill wording. It also has a `helper` skill with a tiny Python and TypeScript tool:
  without one, `--only python` and `--only ts` exit 3.
- Added `tests/test_layout.py`, which checks the real repo's layout, link, settings and removals.
- `smoke.py` also finds tools under `plugins/*/skills/*/scripts/`, and TypeScript tools under any
  `skills/*/scripts/`, not only `skill-audit-ts`.
- The `bundle` group also requires `git`; a missing `--repo` exits 3, as does `--only bundle` with
  no bundles.
- The version check also rejects a lowered version, which the design's rule alone would pass, and a
  lowering committed after a bump.
- Stale mentions in `skill-audit-ts/references/perf-findings.md`, `az/scripts/_common.py`,
  `recommend_scripts.py` and a dangling template link in `interface-contract.md` were fixed.

# Verification

**Verdict:** every behaviour and the goal are met in the working tree. Behaviour 3's "one *tracked*
copy" is only met once the change is committed (see below).

**Evidence.**
- **Self-check:** `smoke.py --tests` 99/99 (exit 0), 362 pytest and 185 vitest pass. Each
  `ai-sdlc/spec-*` skill is named individually under `python`, `ts` and `parity` at fail=0 warn=0.
  `bundle/ai-sdlc/{contents,plugin-validate,agents,refs,overlap,version}` all pass.
- **Real bundle broken on purpose** (in a copy of the repo, not just the synthetic fixture):
  - a renamed `spec-verify` frontmatter fails `--only python`
  - a `` `/foo` `` plus a `` `critic-nope` agent `` fails `--only bundle`
  - after a commit, an agent edit with no bump fails `version`, and passes once the version is
    bumped
- **B1, B5 (real install):** in an isolated `CLAUDE_CONFIG_DIR`, `marketplace add` of this repo and
  `plugin install` of all 11 entries succeed. The installed `ai-sdlc` holds exactly 4 skills and 2
  agents, and every `${SKILL_DIR}/scripts/…` and `references/…` path in the installed `skill-audit`
  resolves. No install contains a `${SKILL_DIR}/../` path.
- **B2 (b), (c):** each ran as a headless session in a scratch repo, with launches read from the
  `subagent_type` in each `Agent` call.
  - `--plugin-dir` loads the bundle as `ai-sdlc@inline` rather than as an `@rafaelh` install. The
    namespaced names are the same.
  - No other `rafaelh` plugin was installed. The user's unrelated plugins also loaded, and the
    critic launches don't depend on them.
  - The init event lists both `ai-sdlc:critic-*` agents, the four `ai-sdlc:spec-*` commands, and
    `/simplify`, `/clear` and `/code-review`.
  - `/ai-sdlc:spec-define` launched `ai-sdlc:critic-specification`.
  - `/ai-sdlc:spec-design` launched `ai-sdlc:critic-architecture`.
  - With a repo-local `.claude/agents/critic-specification.md`, `spec-define` launched the bare
    `critic-specification`. Its marker reply is in that `Agent` call's own result.
- **B3 (a):** with `ai-sdlc@rafaelh` installed at user scope in the isolated config,
  `claude plugin list` reports it `enabled: false` inside this repo and `enabled: true` in a scratch
  repo. The in-repo copy therefore loads from the symlink. This session also lists
  `ai-sdlc:spec-*`, with no `rafaelh` install in the real user config.
  - Not done: the live edit, then `/reload-plugins` step under that install, which needs an
    interactive authenticated session in the isolated config.

**Gaps and caveats.**
- **Not yet tracked:** `plugins/`, `.claude/skills/ai-sdlc`, `.claude/settings.json`, `tests/`, the
  folded `skill-audit` files and `review-repo-agents/.claude-plugin/` are untracked.
  - B3's single tracked copy holds only after a commit.
  - Until then, the real repo's `version` check passes vacuously, because `plugin.json` isn't in
    `HEAD`.
- **Constraint checked by inspection only:** the original `.claude/skills/spec-*` and
  `.claude/agents/*` were never committed, so there is no baseline to diff. The bundle shows exactly
  the decision 5 edits (five namespaced hand-offs and two critic-launch rewordings), and nothing
  else looks altered.
- **B7:** CLAUDE.md describes the bundle and the whole-only rule but does not repeat the install
  command. That is in README, as the design's Docs section assigned it.

**Changed during verification:** nothing, because no bugs were found. After the headless runs,
the bundle still matched the install snapshot exactly. The real user config gained no `rafaelh`
marketplace or plugin. The scratch config and repos were deleted.
