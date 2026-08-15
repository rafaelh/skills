# Link resolution

Read this when adding, rewriting, auditing, or moving links — wikilinks, embeds, or markdown-style internal links. The resolution rules are non-obvious.

## The two link styles

Obsidian supports two formats for internal links:

```
[[Note]]                  wikilink (default)
[Note](Note.md)           markdown-style
```

The `Use [[Wikilinks]]` setting in `.obsidian/app.json` controls which Obsidian generates by default; both forms always work for *resolution*. When editing programmatically, prefer the format already in use in that note. If unsure, use wikilinks.

## How a target name resolves to a file

Given `[[Alpha]]` in some source note, Obsidian resolves the target by this algorithm:

1. **Exact path match**, if the target contains a `/`. `[[notes/Alpha]]` resolves to `notes/Alpha.md` from the vault root, regardless of where the source note lives.
2. **Otherwise, search the vault index** for any file whose basename (without `.md`) equals `Alpha`, OR whose `aliases` frontmatter contains `Alpha`.
3. If exactly one match → done.
4. If multiple matches → pick the one closest to the source note. "Closest" means shortest folder distance (fewest hops up-then-down through the directory tree). Ties are broken by alphabetical path order.
5. If no match → the link is *unresolved* (rendered with a different color in the UI). The note doesn't exist yet; clicking creates it in the default new-note location.

This is sometimes called "shortest path when possible" resolution. The setting `New link format` in `.obsidian/app.json` controls how Obsidian *writes* new links: `shortest`, `relative`, or `absolute`. It does not change how it *resolves* existing links.

## Heading and block references

`[[Note#Heading]]` — resolves Note as above, then jumps to the heading.
- Heading match is case-insensitive and ignores trailing punctuation.
- Multi-level: `[[Note#H1#H2]]` is supported in newer Obsidian.

`[[Note#^block-id]]` — resolves Note, then jumps to the block tagged `^block-id` at the end of a paragraph.

`[[#Heading]]` — heading reference within the current note (target empty).

## Aliases

A note's frontmatter `aliases` list adds extra resolvable names:

```yaml
---
aliases:
  - "The Alpha Project"
  - alpha
---
```

Now `[[The Alpha Project]]` and `[[alpha]]` both resolve to this note. Aliases participate in step 2 of the resolution algorithm above. Display text from `[[Note|alias]]` is independent — it is just the rendered label, not a resolution input.

## Case sensitivity

Obsidian's resolver is case-insensitive — `[[alpha]]` and `[[Alpha]]` resolve to the same note. But the *filesystem* is case-sensitive on Linux and case-insensitive on macOS/Windows. When renaming or moving, preserve the existing case unless explicitly changing it; case-only renames may not even propagate on macOS.

## Embeds resolve identically

`![[X]]` uses the same resolution as `[[X]]`. The only difference is rendering.

## Renaming a note: what to update

When a note `Alpha.md` is renamed to `Beta.md`, Obsidian's UI updates:

1. The file itself.
2. Every wikilink whose target name was `Alpha` (or whose path was `…/Alpha`) — across the whole vault.
3. Every markdown-style link `[…](…/Alpha.md)`.
4. Embeds `![[Alpha]]` and `![…](…/Alpha.md)`.
5. Aliases — *not* updated; if the user had an alias named `Alpha`, it stays.

`rename_note.py` performs steps 1–4. It does not touch aliases.

## What does NOT get updated by a rename

- Heading text inside notes that mentioned `Alpha` (a renamed note may now contradict its own H1).
- Plain-text mentions like `the Alpha note` — those aren't links.
- Dataview / Tasks queries that filter by file name — those are plugin queries; out of scope for this skill.
- Canvas nodes that embed the note — `.canvas` files reference notes by path; they need updating too. (This is a known gap; for now, `rename_note.py` warns when canvas files contain references to the renamed note.)

## Path-based vs name-based: which to use when generating links

Generate path-based (`[[folder/Note]]`) when:
- The target name is ambiguous in this vault.
- You want stability against future name collisions.

Generate bare-name (`[[Note]]`) when:
- The target name is unique in this vault.
- The user's notes consistently use bare-name style.

Default to bare-name unless you have a reason. Match the surrounding style.

## Source

Regenerated from <https://obsidian.md/help/internal-links>, <https://obsidian.md/help/aliases>. Run `scripts/refresh_docs.py` if upstream changes.
