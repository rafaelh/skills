---
name: obsidian
description: Use this skill when working with an Obsidian vault — reading or editing markdown notes, frontmatter (a.k.a. Properties), wikilinks, embeds, callouts, .canvas files, or .base files. Trigger when the user mentions Obsidian, a vault, wikilinks, [[ ]] syntax, properties (tags/aliases/cssclasses), backlinks, a map of content / MOC, broken links, or files under a directory containing .obsidian/, or .canvas / .base extensions. Also trigger on tasks that fit even when Obsidian isn't named — e.g. "rename this markdown file and update every link to it". Scripts locate the vault root, parse and rewrite wikilinks, edit frontmatter idempotently, rename notes while updating backlinks, list notes by tag or property, and validate canvas/base files, plus references for Obsidian's syntax and file formats. Does NOT cover Obsidian as a desktop app, plugin development, or theming — for plugin syntax invoke the matching plugin skill, and for Meta Bind (`INPUT[`, `VIEW[`, `BUTTON[`, ```meta-bind) use obsidian-metabind.
---

# Obsidian Vault

Help an agent operate on an Obsidian vault — the markdown files, links, frontmatter, canvas, and base files that live under a directory containing `.obsidian/`. This skill is about working *with* a vault, not about teaching the human how to use Obsidian.

## When you reach for this skill

The user is asking you to:

- Read, edit, or create notes inside a vault
- Add, remove, or normalize frontmatter (tags, aliases, cssclasses, custom properties)
- Rename a note and keep `[[wikilinks]]` pointing at it
- Find backlinks, build a map-of-content, or audit broken links
- Parse or generate `.canvas` or `.base` files
- Detect which Obsidian plugins a vault uses

If the user is asking how to *use* Obsidian (panels, hotkeys, settings UI), this is the wrong skill — answer from general knowledge or point them at <https://obsidian.md/help>.

## Workflow

### 1. Locate the vault root

Every other script in this skill takes `--vault PATH` or auto-discovers by walking up from cwd. Always start by establishing the vault root:

```bash
python3 scripts/vault.py [PATH]
```

Prints the absolute path of the directory containing `.obsidian/`. Exits 1 if not in a vault.

In Python:

```python
from vault import locate_vault, NotInVaultError

root = locate_vault(some_path)
```

If the user gives you a path that is not inside a vault, do not silently treat it as one. Tell them and ask for the correct vault root.

### 2. Pick the right tool for the operation

| Task                              | Script                    | Reference                                     |
|-----------------------------------|---------------------------|-----------------------------------------------|
| Locate the root, enumerate files  | `vault.py`                | `references/vault-structure.md`               |
| Resolve a wikilink target to note(s) | `resolver.py`          | `references/linking.md`                       |
| Read/write frontmatter            | `vault_frontmatter.py`    | `references/frontmatter.md`                   |
| Parse wikilinks/embeds/tags       | `links.py`                | `references/markdown-syntax.md`, `linking.md` |
| Rename a note + fix inbound links | `rename_note.py`          | `references/linking.md`                       |
| Find what links to a note         | `backlinks.py`            | `references/linking.md`                       |
| List notes by folder/tag/property | `vault_list.py`           | `references/vault-structure.md`               |
| Validate a `.canvas` file         | `canvas_validate.py`      | `references/canvas-format.md`                 |
| Validate a `.base` file           | `base_validate.py`        | `references/bases-format.md`                  |
| See what plugins are installed    | `vault_list.py --plugins` | `references/plugin-conventions.md`            |
| Refresh cached upstream docs      | `refresh_docs.py`         | n/a (writes to `references/.cache/`)          |

### 3. Load references on demand

Reference files are *not* preloaded — read them with the Read tool when the task crosses the relevant area:

- **`references/markdown-syntax.md`** — when generating or editing Obsidian-flavor markdown (wikilinks, embeds, callouts, block refs, tags, math, mermaid). Read before producing new note content.
- **`references/frontmatter.md`** — when reading or writing YAML frontmatter, especially special keys (`tags`, `aliases`, `cssclasses`, `publish`). Read before any frontmatter edit.
- **`references/vault-structure.md`** — when navigating the vault layout (`.obsidian/`, `.trash/`, attachment folders, `.md` vs `.canvas` vs `.base`).
- **`references/linking.md`** — when adding, rewriting, or auditing links. Covers shortest-path resolution, ambiguity, and case sensitivity.
- **`references/canvas-format.md`** — when reading or generating `.canvas` JSON.
- **`references/bases-format.md`** — when reading or generating `.base` YAML.
- **`references/plugin-conventions.md`** — when the vault has community plugins installed and you need to know what file conventions they imply (or which sibling skill to call).
- **`references/operations.md`** — recipes for common multi-step tasks (build a MOC, extract all tags, merge two notes, audit broken links).

If `references/.cache/` exists, it contains pages fetched by `refresh_docs.py` — useful when you hit something not covered above. Do not assume it's present.

## Gotchas

- **Wikilinks are not regex-friendly.** They can contain pipes (`[[Note|Display]]`), heading refs (`[[Note#Heading]]`), block refs (`[[Note#^abcd]]`), and embeds (`![[Note]]`). Always parse with `links.py`, never with naive regex on `\[\[(.+?)\]\]`.
- **Shortest-path link resolution is the default.** `[[alpha]]` may resolve to `notes/alpha.md` or `archive/alpha.md` depending on uniqueness — see `references/linking.md`. Do not assume a wikilink target is in the same folder as the source note.
- **Frontmatter is order-sensitive to humans.** Preserve key order when editing — `vault_frontmatter.py` does this; `yaml.safe_dump` with default args does not. Frontmatter comments are uncommon (Obsidian's Properties UI strips them) and are NOT preserved on round-trip; warn the user if you see them and they want a write.
- **`.obsidian/` belongs to the vault, not Obsidian's install.** It contains user config and plugins for *that* vault. Do not edit it unless explicitly asked.
- **Plugin folders may exist without being enabled.** Check `.obsidian/community-plugins.json` for the active list, not just directory presence.
- **`.trash/` holds soft-deleted notes.** Treat them as out-of-scope for searches and link audits unless the user asks.
- **File-name case matters on case-sensitive filesystems but not in Obsidian's resolver.** Tests must work on macOS (case-insensitive default) and Linux (case-sensitive).
- **Conflict files** like `note (conflict 2026-05-02-09-40-25).md` are produced by Sync. Skip them unless the user is resolving conflicts.

## Anti-patterns

- Hardcoding a vault path in scripts or examples. Always discover or accept `--vault`.
- Treating wikilink targets as paths. They are *names* resolved against the vault index.
- Rewriting an entire note to change one frontmatter key. Use `vault_frontmatter.py` so the body and key order stay intact.
- Stripping unknown frontmatter keys. The user (or a plugin) may rely on them.
- Generating a Dataview query as part of this skill. That belongs in a Dataview-specific sibling skill.
- Authoring or editing Meta Bind syntax here. `obsidian-metabind` owns it; this skill only recognizes it.

## Specification

- Every script is Python 3 stdlib-only except `vault_frontmatter.py`, `vault_list.py`, and `base_validate.py`, which depend on PyYAML (already present in most Python environments; install with `pip install pyyaml` if missing).
- Every script accepts `--vault PATH` and falls back to walking up from cwd.
- Every entry-point script has a sibling `tests/test_<name>.py` runnable with `python3 -m pytest scripts/tests/`. The two shared library modules have none: `models.py` is dataclasses only, and `validate_cli.py` is exercised through the canvas/base validators' own CLI tests.
- The fixture vault at `scripts/tests/fixtures/test_vault/` is the only vault any test may touch. It is the source of truth for "what a minimal valid vault looks like."
