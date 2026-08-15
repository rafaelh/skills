# Embeds and templates

Read this when a note pulls Meta Bind declarations in from somewhere else — an embed block, an
input field template, or a button template.

## Embeds

````markdown
```meta-bind-embed
[[Other Note]]
```
````

The referenced note's content is rendered in place, with its Meta Bind declarations live. Unlike a
plain `![[Other Note]]` embed, fields inside a `meta-bind-embed` bind against the **embedding**
note, which is the whole point: one template note, many hosts.

`EMBED_MAX_DEPTH = 8` (recorded as `embed_max_depth` in `field-spec.json`). An embed chain deeper
than that is cut off — usually the sign of a cycle, since a note embedding itself hits the limit
rather than hanging.

Embeds accept a heading or alias in the wikilink, but the target must be a note. This skill's
`scan.py --list` reports the target as `embed_target`; it does not follow the chain.

## Input field templates

Configured in the Meta Bind settings UI, not in a note. A template names a reusable
`type(args)` combination, which a declaration then references:

```markdown
`INPUT[myTemplate][toggle:done]`
`INPUT[myTemplate][]`
```

The template supplies the field type and arguments; the second bracket group overrides or adds. The
empty form `INPUT[myTemplate][]` is legal precisely because the template already carries the type —
`scan.py --check` does not flag it.

## Button templates

Same mechanism for buttons: a named config in settings, referenced instead of repeated. See
[buttons.md](buttons.md).

## Where templates actually live

Both kinds are stored in `.obsidian/plugins/obsidian-meta-bind-plugin/data.json`, under the vault's
plugin config — **not** in any note. Consequences:

- The scripts in this skill cannot see them. `scan.py --check` never reports an unknown template
  name, because it has no list to check against.
- Templates do not travel with a note. Copying a note that uses `INPUT[myTemplate][]` into another
  vault silently breaks it.
- Editing `data.json` by hand is editing plugin config. Do not, unless the user asks.

If you need to know what templates a vault defines, read that `data.json` and tell the user what you
found — do not guess from usage.

## Obsidian Publish

Meta Bind does not run on Obsidian Publish. Published notes show the raw declaration text — inline
code spans render as code, fenced blocks as code blocks. If the user publishes, keep interactive
fields out of published notes, or pair each one with a plain-markdown fallback.

Live Preview and Reading view both render fields; source mode shows the raw text. That is expected,
not a bug to chase.

## Anti-patterns

- Using `meta-bind-embed` where a plain `![[note]]` would do. The embed exists to rebind fields
  against the host note; if there are no fields, it just costs a depth level.
- Assuming a template name in a note tells you the template exists. Check `data.json`.
- Building an embed chain more than a couple of levels deep. The limit is 8, but debugging a
  4-level chain is already unpleasant.
