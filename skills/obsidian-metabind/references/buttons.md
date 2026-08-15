# Meta Bind buttons

Read this when writing or editing a ```` ```meta-bind-button ```` block, or a `` `BUTTON[id]` ``
reference. Button config is YAML — a different shape from the bracket grammar in
[syntax.md](syntax.md), which is why it gets its own file.

The authoritative field lists live in `field-spec.json` under `button_config_fields` and
`button_action_types`. This file explains the shape and the traps.

## The config block

````markdown
```meta-bind-button
label: Increment
style: primary
id: count-increment
hidden: true
action:
  type: updateMetadata
  bindTarget: count
  evaluate: true
  value: x + 1
```
````

| Key | Required | Notes |
|---|---|---|
| `label` | yes | text on the button |
| `style` | yes | `default`, `primary`, `destructive`, `plain` |
| `icon` | no | shown before the label |
| `class` | no | CSS class |
| `cssStyle` | no | inline CSS |
| `backgroundImage` | no | vault images can't be loaded from pure CSS, hence this key |
| `tooltip` | no | hover text |
| `id` | no | required if you want to reference the button by `BUTTON[id]` |
| `hidden` | no | hide the block itself; the usual companion to `id` |
| `action` | no | a single action |
| `actions` | no | a list of actions, run in order |

**`action` and `actions` are mutually exclusive.** Setting both is an error, not a merge.

## Inline references

A config block with `id` and `hidden: true` acts as a definition; reference it anywhere in the
vault:

```markdown
`BUTTON[count-increment]`
`BUTTON[count-decrement, count-reset, count-increment]`
```

Ids resolve **vault-wide**, not per note — the definition and the reference may live in different
files. `scan.py --check` reports `metabind.unresolved-button-id` when no config anywhere declares
the id.

Set `hidden: true` on a definition you only reference. Otherwise it renders twice: once where it is
defined and once where it is referenced.

## Actions

Fourteen action types. Required fields are listed first; optional ones are marked `?`.

| `type` | Fields |
|---|---|
| `command` | `command` |
| `open` | `link`, `newTab?` |
| `input` | `str` |
| `sleep` | `ms` |
| `js` | `file`, `args?` |
| `inlineJS` | `code`, `args?` |
| `updateMetadata` | `bindTarget`, `evaluate`, `value` |
| `createNote` | `fileName`, `folderPath?`, `openNote?`, `openIfAlreadyExists?` |
| `templaterCreateNote` | `templateFile`, `folderPath?`, `fileName?`, `openNote?`, `openIfAlreadyExists?` |
| `runTemplaterFile` | `templateFile` |
| `replaceInNote` | `fromLine`, `toLine`, `replacement`, `templater?` |
| `replaceSelf` | `replacement`, `templater?` |
| `regexpReplaceInNote` | `regexp`, `replacement`, `regexpFlags?` |
| `insertIntoNote` | `line`, `value`, `templater?` |

`scan.py --check` validates this table for you — missing required fields and unknown fields are
both reported as `metabind.button-action-field`.

### `updateMetadata`

```yaml
action:
  type: updateMetadata
  bindTarget: count
  evaluate: true
  value: x + 1
```

`bindTarget` takes the full bind target grammar from [syntax.md](syntax.md), cross-note targets
included. With `evaluate: true`, `value` is a JS expression and `x` is the current value; with
`evaluate: false`, `value` is used literally.

This is the one place a bind target hides inside YAML rather than inside brackets, and it is why
`rename.py --property` parses button blocks rather than only bracket declarations.

### `js` and `inlineJS`

```yaml
action:
  type: inlineJS
  code: console.log(engine.getMetadata('count'));
```

`js` takes a `file` path in the vault; `inlineJS` takes `code` directly. Both receive `args` as an
object.

**Property names inside JS are never rewritten automatically.** `rename.py` reports these sites as
needing manual attention instead — pattern-rewriting identifiers inside arbitrary JS eventually
corrupts working code. After any `--property` rename, grep the reported files yourself.

## Button templates

The plugin settings hold a list of button templates. A config may name one instead of repeating
itself. Templates are configured in the Meta Bind settings UI and stored in
`.obsidian/plugins/obsidian-meta-bind-plugin/data.json` — not in a note, so this skill's scripts
cannot see them. If `scan.py --check` reports an unresolved id you are sure exists, check whether it
is defined as a template rather than in a block.

## Anti-patterns

- Referencing a button by its `label`. Only `id` resolves.
- Leaving `hidden` off a definition you only reference — it renders in both places.
- Reaching for `inlineJS` for something `updateMetadata` already does. The JS path is opaque to
  every tool here, including rename.
- Quoting a YAML value that does not need it, or leaving one unquoted when it starts with `[`,
  `{` or `*`. Button configs are ordinary YAML and fail in the ordinary YAML ways.
