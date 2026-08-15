# Frontmatter (Properties)

Read this before reading or writing YAML frontmatter in a note. Use `vault_frontmatter.py` for any actual edit — manual rewrites lose insertion order.

## Format

Frontmatter is a YAML block at the very top of the file, fenced by `---` lines:

```markdown
---
title: My Note
tags:
  - work
  - urgent
created: 2026-05-02
---

# Body starts here
```

Rules:
- The opening `---` must be the first line of the file.
- Frontmatter is optional. A `---` later in the file is just a horizontal rule.
- The block must close with another `---` line. An unclosed block is malformed.
- An empty block (`---\n---\n`) is valid; treat it as no properties.
- Anything between the fences is parsed as YAML 1.1 (Obsidian uses a JS YAML parser; types follow YAML 1.1 not 1.2).

## Default property names

Obsidian's UI ("Properties") recognizes a few special keys with built-in semantics:

| Key       | Type            | Meaning                                                                               |
|-----------|-----------------|---------------------------------------------------------------------------------------|
| `tags` | list of strings | Inline tags equivalent. Supports `tags: [a, b]` or block list. Single string also works (`tags: foo`). |
| `aliases` | list of strings | Alternate names this note can be linked to. `[[some-alias]]` resolves to the note.    |
| `cssclasses` | list of strings | CSS classes applied to the note's preview/edit view. (Obsolete spelling: `cssclass`.) |
| `publish` | boolean         | If `false`, Obsidian Publish skips this note.                                         |

Everything else is user-defined. Plugins (Templater, Dataview, etc.) read whatever keys they want.

## Type coercion in Obsidian's UI

When the user edits a property in the Properties UI, Obsidian applies a type:

- **Text** — string scalar.
- **List** — YAML list. Single-element lists may render as a flow scalar (`[x]`) or block list.
- **Number** — int or float.
- **Checkbox** — boolean (`true` / `false`).
- **Date** — ISO date `2026-05-02`.
- **Datetime** — ISO datetime `2026-05-02T13:45:00`.

The type is stored separately from the file. The file just contains YAML; Obsidian remembers the chosen type per-key in `.obsidian/types.json`. Do not edit that file unless asked.

## Gotchas

- **Tags in frontmatter use the bare name, not `#tag`.** Both forms parse, but Obsidian's UI canonicalizes to bare. Always emit bare.
- **Inline `tags: foo` is valid for a single tag.** Multiple tags require a list.
- **Booleans with capital letters** (`Yes`, `No`, `On`, `Off`) are parsed as booleans by YAML 1.1. Quote them if you mean strings.
- **Versions and dates** like `1.0` parse as float, `2026-05-02` as date. Quote if you want strings.
- **Aliases work case-insensitively** in Obsidian's resolver. The stored value preserves case.
- **Properties UI strips inline YAML comments** (`# this is a comment`) on save. Don't put load-bearing comments in frontmatter.
- **Ordering matters to humans, not to Obsidian.** `vault_frontmatter.py` preserves insertion order; raw `yaml.safe_dump` does not.
- **Multiple frontmatter blocks are not supported.** Only the first `---`-fenced block at the start of the file counts.

## Editing patterns

### Add or replace one key, preserving order

```python
from vault_frontmatter import set_key

set_key("note.md", "status", "published")
```

### Add a tag without duplicating

```python
from vault_frontmatter import read, write

fm, body = read("note.md")
tags = list(fm.get("tags") or [])
if "urgent" not in tags:
    tags.append("urgent")
fm["tags"] = tags
write("note.md", fm, body)
```

### Bulk update across the vault

Walk notes via `vault_list.py`, read frontmatter, decide, write. Always keep the read-modify-write transactional — do not stream lines.

## Source

Regenerated from <https://obsidian.md/help/properties>, <https://obsidian.md/help/properties-types>. Run `scripts/refresh_docs.py` if something here looks stale.
