# Plugin conventions

Read this when the vault has community plugins enabled and you need to know what file conventions or in-note syntax those plugins introduce. The goal is *recognition*, not action — for any deeper plugin-specific behavior, defer to a sibling skill if one exists for that plugin.

Discover which plugins are present:

```bash
python3 scripts/vault_list.py --plugins
```

This emits JSON with `enabled_community`, `installed_community`, and `enabled_core`.

## How to use this file

When you see the listed plugin in `enabled_community`:

1. Recognize that the in-note syntax / files described below may appear.
2. Do NOT generate that syntax from this skill. If the user wants you to generate, e.g., a Dataview query, ask for a Dataview-specific skill or tell them you can copy what's already there but won't author new queries.
3. When *editing* notes that already contain plugin syntax, preserve it byte-for-byte unless the user explicitly asks for a change.

## Plugins commonly seen in personal vaults

### `dataview`

In-note syntax:
- Inline: `(field:: value)` or `[field:: value]` — adds a queryable field.
- Block:
  ````
  ```dataview
  TABLE file.name FROM "folder"
  ```
  ````
- DataviewJS: ```dataviewjs ... ``` — runs JS.

What this means for you:
- Treat ```dataview``` and ```dataviewjs``` fenced blocks as opaque code; do not reformat their contents.
- `inline:: fields` are stored in the note body, not frontmatter; they coexist with frontmatter properties.

### `templater-obsidian`

In-note syntax:
- `<% tp.something() %>` — evaluated when the template is invoked.
- `<%* ... %>` — JS expression block.

What this means for you:
- Files in a `templates/` folder may contain unexpanded `<% %>` directives. Do not "fix" them.
- When generating new notes, do not author Templater syntax; use plain markdown.

### `obsidian-tasks-plugin`

In-note syntax:
- Task lines: `- [ ] do thing 📅 2026-05-15 🔁 every week #tag`
- Emoji metadata: 📅 due, ⏳ scheduled, 🛫 start, ✅ done, 🔁 recurrence, 🔼 priority.
- Block: ```tasks ... ``` — query.

What this means for you:
- Preserve emoji metadata on task lines.
- Treat ```tasks``` blocks as opaque queries.

### `obsidian-excalidraw-plugin`

Files: `*.excalidraw.md` — markdown with embedded JSON drawing data.

What this means for you:
- Treat these files as binary-ish: do not reformat. Use them only via wikilink or embed.

### `bases` (core, not community)

Files: `*.base`. See `references/bases-format.md`.

### `daily-notes` (core)

Folder: configurable, often `daily/` or `journal/`. Filename from `daily-notes.json`'s `format` (moment.js).

What this means for you:
- This skill explicitly does not handle daily-note path computation. If the user wants today's daily note, ask them for the path.

### `obsidian-git`

Files: `.gitignore` typically excludes `.obsidian/workspace*.json`, plugin caches.

What this means for you:
- The vault may be a git repo. Use `gh` / `git` for staging and pushes; do not commit on the user's behalf without confirmation.

### `kanban`

Files: `*.md` with frontmatter `kanban-plugin: basic` and a markdown structure of headings + task lists.

What this means for you:
- Recognize the frontmatter signal. Edits to a Kanban note should preserve heading-as-column / task-as-card structure.

### `homepage`

Adds a default note shown on launch. No special file format. Recognition only.

## Recognition cheatsheet

| Signal in a note                   | Likely plugin                |
|------------------------------------|------------------------------|
| ```` ```dataview ```` block        | `dataview`                   |
| ```` ```dataviewjs ```` block      | `dataview`                   |
| `(key:: value)` inline             | `dataview`                   |
| `<% tp.foo() %>`                   | `templater-obsidian`         |
| `📅 2026-...` after a task          | `obsidian-tasks-plugin`      |
| ```` ```tasks ```` block           | `obsidian-tasks-plugin`      |
| Filename ends in `.excalidraw.md`  | `obsidian-excalidraw-plugin` |
| Filename ends in `.base`           | Bases (core)                 |
| Frontmatter `kanban-plugin: basic` | `kanban`                     |

## When to invoke a sibling skill

If the user asks you to *write* plugin-specific syntax (a Dataview query, Templater template, Tasks query), check whether a `dataview-queries`, `templater`, or `obsidian-tasks` skill is installed. If it is, defer to it. If not, tell the user you don't have plugin-specific authoring loaded and offer to copy/edit existing examples in the vault verbatim.

## Source

Plugin metadata at <https://obsidian.md/plugins>. Specific plugins documented at their own repos:
- Dataview: <https://blacksmithgu.github.io/obsidian-dataview/>
- Templater: <https://silentvoid13.github.io/Templater/>
- Tasks: <https://publish.obsidian.md/tasks/>
- Excalidraw: <https://github.com/zsviczian/obsidian-excalidraw-plugin>
