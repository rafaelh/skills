# Vault structure

Read this when navigating the vault layout — finding notes, attachments, plugin data, or deciding what to skip during a sweep.

## What makes a vault

A vault is **any directory that contains a `.obsidian/` subdirectory**. That's the entire definition. There is no marker file, no manifest, no version stamp. The vault root may be at any depth on the filesystem.

`vault.py` walks up from a path until it finds `.obsidian/`. That is the canonical way to discover the root.

## Top-level layout

```
vault-root/
├── .obsidian/                 vault config and plugins (Obsidian-managed)
├── .trash/                    soft-deleted notes (Obsidian-managed, only if local trash is enabled)
├── any/user/folders/          notes, organized however the user likes
└── attachments/               where new attachments default to (configurable)
```

The user's folder structure is theirs. Common conventions you may see:
- Numeric-prefix top-level folders for ordering: `0. Meta/`, `1. Tools/`, `2. Personal/`.
- A `templates/` or `_templates/` folder for note templates.
- A `daily/` or `journal/` folder for daily notes.
- A `_attachments/` or `assets/` folder for media.

Treat folder structure as user data. Do not reorganize without explicit instruction.

## Inside `.obsidian/`

The contents are Obsidian's. You read them; you don't edit them unless asked.

| Path | Contains |
|------|----------|
| `app.json` | Core app settings (auto-pair, line break behavior, etc.). |
| `appearance.json` | Theme, font, accent color. |
| `core-plugins.json` | List of enabled core plugins. (Format changed across Obsidian versions; may be array of names or object.) |
| `community-plugins.json` | List of enabled community plugin ids. |
| `plugins/<plugin-id>/` | One folder per installed community plugin. Contains `manifest.json`, `main.js`, optional `styles.css`, and plugin-specific data. |
| `themes/<theme-name>/` | Installed themes. |
| `snippets/*.css` | User CSS snippets. |
| `workspace.json` / `workspaces.json` | UI layout state. Volatile; do not parse for content. |
| `types.json` | Per-property type assignments (text/number/date/etc.). |
| `daily-notes.json` | Daily notes plugin config (only if enabled). |
| `templates.json` | Templates plugin config (only if enabled). |
| `bookmarks.json` | User-bookmarked notes/searches. |

## File types in a vault

| Extension                           | Format | Notes                                                             |
|-------------------------------------|--------|-------------------------------------------------------------------|
| `.md` | UTF-8 markdown with optional YAML frontmatter | Primary note format. |
| `.canvas` | JSON | Free-form node-and-edge canvas. See `references/canvas-format.md`. |
| `.base`                             | YAML   | Database view (Obsidian Bases). See `references/bases-format.md`. |
| `.png` `.jpg` `.gif` `.webp` `.svg` `.bmp` | image | Attachments. |
| `.pdf`                              | PDF    | Attachments; Obsidian renders inline.                             |
| `.mp3` `.wav` `.m4a` `.ogg` `.flac` | audio  | Attachments.                                                      |
| `.mp4` `.webm` `.mov` `.mkv`        | video  | Attachments.                                                      |

Anything else (e.g. `.html`, `.txt`, `.csv`) shows up in the file tree but is not opened in the editor.

## What to skip during a vault sweep

Always exclude:
- `.obsidian/` — config, not user content.
- `.trash/` — deleted notes.
- Hidden files anywhere (`.DS_Store`, `.git/`, `.gitignore` — though those last two are user-managed).

Conditionally exclude (ask first):
- Files matching `* (conflict YYYY-MM-DD-HH-MM-SS).md` — Sync conflicts.
- Files matching `* (\d+).md` — duplicate-name copies.

## Discovering plugin presence

To know what a vault uses:

1. Read `.obsidian/community-plugins.json` — JSON array of plugin ids that are *enabled*.
2. Cross-reference with `.obsidian/plugins/` directory contents — these are *installed* but not necessarily enabled.
3. For core plugins, read `.obsidian/core-plugins.json`.

`vault_list.py --plugins` does this. See `references/plugin-conventions.md` for what each common plugin implies.

## Source

Regenerated from <https://obsidian.md/help/vault>, <https://obsidian.md/help/configure-obsidian>. Run `scripts/refresh_docs.py` if something here looks stale.
