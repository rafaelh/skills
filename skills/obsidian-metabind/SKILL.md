---
name: obsidian-metabind
description: Use this skill when reading, authoring, auditing, or refactoring Meta Bind syntax in an Obsidian vault — input fields, view fields, buttons, embeds, and the Meta Bind / JS Engine APIs. Trigger on `INPUT[`, `VIEW[`, `BUTTON[`, ```meta-bind, ```meta-bind-button, ```meta-bind-js-view, ```js-engine, "Meta Bind", "metabind", or the obsidian-meta-bind-plugin folder. Also trigger when Meta Bind isn't named — "make this note interactive", "add an input field to this note", "bind this checkbox to frontmatter", "a button that increments a property", "why isn't my slider rendering", "my select doesn't render inline", "I renamed a property and the fields broke". Scripts to inventory every declaration, validate them against the plugin's own generated field/argument/action tables, and retarget bind targets after a rename. NOT for general vault work — wikilinks, frontmatter, canvas, bases, renaming notes — use the obsidian skill for that. NOT for Meta Bind's settings UI or for plugin development against its TypeScript API.
---

# Meta Bind

Operate on [Meta Bind](https://www.moritzjung.dev/obsidian-meta-bind-plugin-docs/) syntax inside an
Obsidian vault: the input fields, view fields, buttons and embeds that turn a note into something
interactive. This skill is about working *with* those declarations — reading, writing, checking and
refactoring them — not about teaching the human to use the plugin's settings UI.

Meta Bind's surface is large: 21 input field types, 17 input field arguments, 4 view field types, 14
button actions, a bind target grammar, and two plugin APIs. Do not work from memory. The tables are
generated from the plugin's own source into `references/field-spec.json`.

## When you reach for this skill

The user wants you to:

- Add an input field, view field or button to a note
- Work out why a field renders wrong, or doesn't render at all
- Inventory what a vault binds to, or find every note bound to a property
- Validate declarations after hand-editing, or before a commit
- Fix bind targets after renaming a frontmatter property or a note
- Write JS against the Meta Bind or JS Engine API

For wikilinks, frontmatter editing, canvas, bases, or renaming the note itself, that is the
`obsidian` skill. The two are independent — neither calls the other — but they compose: run
`rename_note.py` from `obsidian` to move a note, then `rename.py --path` from here to fix the bind
targets that point at it, which `rename_note.py` does not touch.

## Workflow

### 1. Look before writing

Never hand-write a declaration into a vault you haven't inventoried. Existing declarations tell you
the conventions the vault already uses:

```bash
python3 scripts/scan.py --list
python3 scripts/scan.py --list --json | jq '.data[] | select(.bind_target == "count")'
```

`--list` reports every declaration with file, line, column, kind, field type and bind target. Exit
`3` means the scope holds no declarations.

### 2. Read the reference for what you're about to write

Reference files are *not* preloaded. Read the one that matches the task before producing syntax:

- **`references/syntax.md`** — the declaration grammar: inline span vs fenced block, when each is
  valid, bind target forms, argument values and escaping. Read before writing any `INPUT[…]`,
  `VIEW[…]` or `BUTTON[…]`.
- **`references/buttons.md`** — button config YAML, the 14 action types and their fields, `id` and
  `BUTTON[id]` group references. Read before writing a ```` ```meta-bind-button ```` block.
- **`references/embeds-and-templates.md`** — `meta-bind-embed`, embed depth, and where input field
  and button templates actually live. Read when a note pulls declarations in from elsewhere.
- **`references/js-engine.md`** — the host surface a ```` ```js-engine ```` or
  ```` ```meta-bind-js-view ```` block runs in. Read before writing either.
- **`references/api.md`** — Meta Bind's own API, for building fields from JS. Read when a
  declaration won't do the job.
- **`references/field-spec.json`** — generated. Which field types exist, which arguments are legal
  on which types, their arities and allowed values, the button action shapes. Grep it rather than
  guessing; `scan.py --check` validates against this same file.

If `references/.cache/` exists it holds the upstream docs fetched by `scripts/refresh_docs.py`.
Do not assume it's present.

### 3. Check what you wrote

```bash
python3 scripts/scan.py --check
python3 scripts/scan.py --check Notes/Health.md
```

Exit `0` clean, `1` findings, `2` no `field-spec.json`, `3` nothing in scope. Findings carry a
`metabind.*` code, a location and a message. Run this after every edit — the failure mode Meta Bind
gives the user is a red error box in the note, and this catches it first.

Add `--strict` to also report bind targets naming a frontmatter property that does not exist. It is
off by default because Meta Bind creates the property on first write, so a fresh note legitimately
has none. Turn it on after a rename, when an absent property means a broken field.

### 4. Refactor with the tool, not with sed

```bash
python3 scripts/rename.py --property count hitPoints --dry-run
python3 scripts/rename.py --property count hitPoints
python3 scripts/rename.py --path 'Other Note' 'Reference Note'
```

`--property` rewrites bind targets in `INPUT`, `VIEW`, `meta-bind-js-view` headers, and button
`updateMetadata` blocks. `--path` rewrites the file half of cross-note bind targets. Always
`--dry-run` first.

It rewrites references only — it never moves or renames a file, and `--path` accepts an `OLD` that
no longer exists on disk, so it composes with the `obsidian` skill's `rename_note.py` in either
order.

### 5. Refresh the tables when the plugin version moves

```bash
python3 scripts/refresh_docs.py --only spec
python3 scripts/refresh_docs.py --only cache --filter button
```

Regenerates `references/field-spec.json` from the plugin's own `FieldConfigs.ts` and
`ButtonConfig.ts`, and mirrors the docs into `references/.cache/`. It reads the installed version
from the vault's `.obsidian/plugins/obsidian-meta-bind-plugin/manifest.json` so the spec matches the
plugin the user actually runs; `--ref` overrides. Needs network access.

## Gotchas

- **Declarations are not regex-friendly.** Argument values legitimately contain brackets, commas
  and quotes — `option(80, Griffon [flying])` is valid. A declaration's extent comes from its host
  (a code span or a fence), never from bracket counting. Use `scan.py`, never a regex.
- **Not every field type renders inline.** `select`, `multiSelect`, `editor`, `progressBar`,
  `list`, `listSuggester` and `imageListSuggester` are block-only. Inline they silently do nothing.
  This is the single most common "my field doesn't work" report.
- **The memory scope goes before the caret**: `memory^prop`, `globalMemory^prop`. These never touch
  frontmatter, so `--strict` correctly ignores them.
- **`VIEW[…]` needs no second bracket group.** `VIEW[{a} + {b}]` is complete. Add `[math:target]`
  when you want evaluation and a write target.
- **Button ids resolve vault-wide.** A `BUTTON[id]` reference and its config may live in different
  notes. Give a referenced-only config `hidden: true` or it renders twice.
- **`action` and `actions` are mutually exclusive** in a button config.
- **Templates live in plugin config, not in notes** — `.obsidian/plugins/…/data.json`. Nothing here
  can see them, so `--check` never reports an unknown template name.
- **Meta Bind creates a bound property on first write.** An absent frontmatter key is not, by
  itself, a bug.
- **Meta Bind does not run on Obsidian Publish.** Declarations publish as literal code.

## Anti-patterns

- Hand-editing a bind target across a vault with sed or a bulk find-and-replace. Button
  `updateMetadata` targets live in YAML, `js-view` targets in a block header, and JS references
  must not be touched at all — `rename.py` knows the difference.
- Rewriting property names inside `js` or `inlineJS` code. `rename.py` reports these as needing
  manual attention on purpose; do the same and tell the user which files to review.
- Authoring a `js-engine` block when a declarative field would do. Declarations are greppable,
  checkable and renameable; JS is none of those.
- Guessing an argument name or which field type accepts it. Grep `references/field-spec.json`.
- Editing `.obsidian/plugins/obsidian-meta-bind-plugin/data.json`. That is the user's plugin
  config; read it if you must, write it only when asked.
- Generating Dataview, Templater or Tasks syntax from this skill. Those are other plugins.

## Specification

- Every script is Python 3 and depends on PyYAML, declared in a PEP 723 block (`pip install pyyaml`
  if missing).
- `scripts/scan.py`, `scripts/rename.py` and `scripts/refresh_docs.py` are agent tools: `--format
  json|text` with `--json` as shorthand, `--quiet`, and exit codes `0` success, `1` user error or
  findings, `2` system error, `3` not found / empty. `scripts/parser.py` is a shared library, not a
  tool, and is marked `# agent-tool: false`.
- Every script accepts `--vault PATH` and otherwise walks up from cwd to find `.obsidian/`.
- `references/field-spec.json` is generated and committed. It regenerates byte-identically from a
  clean `refresh_docs.py --only spec` run at the pinned version; there is no timestamp in it, only
  the resolved commit.
- The fixture vault at `scripts/tests/fixtures/test_vault/` is the only vault any test may touch.
  `Broken.md` there holds exactly one deliberately-wrong declaration per `--check` finding class.
