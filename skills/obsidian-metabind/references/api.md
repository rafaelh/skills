# Meta Bind API

Read this when a `js-engine` block or a `js` / `inlineJS` button action needs to build fields or
touch metadata programmatically rather than declaratively. For the host surface those blocks run in,
read [js-engine.md](js-engine.md).

Thin by design: the full TypeDoc tree is large and generated. This file names the entry points worth
knowing; `references/.cache/` holds the rest.

## Getting the API

```js
const mb = engine.getPlugin('obsidian-meta-bind-plugin').api;
```

Returns `undefined` when the plugin is not loaded. Guard it in anything you ship to someone else's
vault.

## Bind targets

Every metadata call takes a parsed bind target, never a string:

```js
const target = mb.parseBindTarget('select', context.file.path);
const target2 = mb.createBindTarget('frontmatter', context.file.path, ['nested', 'object']);
```

`parseBindTarget` takes the same grammar as a declaration — `Other Note#title`, `memory^scratch`,
`nested["object"]` all parse. The second argument is the note the target is relative to.

## Metadata

```js
mb.getMetadata(target);
mb.setMetadata(target, value);
mb.updateMetadata(target, value => value + 1);
const unsubscribe = mb.subscribeToMetadata(target, /* … */);
```

Prefer `updateMetadata` over `getMetadata` + `setMetadata`: it is one atomic pass, so it does not
lose a concurrent write from a field the user is typing into.

## Mounting fields

The pattern is always the same — create a mountable, then wrap it in a markdown render child:

```js
const mountable = mb.createInputFieldMountable(context.file.path, {
  renderChildType: 'block',
  declaration: {
    inputFieldType: 'select',
    bindTarget: mb.parseBindTarget('select', context.file.path),
    arguments: [
      { name: 'option', value: ['a'] },
      { name: 'title', value: ['Pick one'] },
    ],
  },
});

mb.wrapInMDRC(mountable, container, component);
```

`arguments` is a list of `{name, value}` where `value` is always an **array**, matching the arity
table in `field-spec.json`.

Mountable constructors: `createInputFieldMountable`, `createViewFieldMountable`,
`createJsViewFieldMountable`, `createButtonMountable`, `createButtonGroupMountable`,
`createTableMountable`, `createEmbedMountable`, `createExcludedMountable`.

`renderChildType` is `'block'` or `'inline'` and must match the host — a block field mounted inline
does not render.

## Building from a declaration string

When you already have a declaration as text:

```js
mb.createInlineFieldFromString('INPUT[toggle:done]', context.file.path, undefined);
mb.isInlineFieldDeclarationAndGetType(str);   // which kind of field, or undefined
```

## Other entry points

```js
mb.createSignal(initialValue);   // reactive value the fields understand
mb.createNotePosition(lineStart, lineEnd);
mb.mathJSImport(object, options);  // extend the math view field's function set
```

## The cache

`refresh_docs.py` mirrors the docs repo's `src/content/docs/` — guides, reference, and the
TypeDoc-generated `api/` tree — into `references/.cache/`, along with JS Engine's `README.md` and
`index.ts`. It is gitignored and may be absent.

```bash
python3 scripts/refresh_docs.py --only cache
python3 scripts/refresh_docs.py --only cache --filter api
```

Read from `references/.cache/docs/` when you need a signature this file does not name. If the
directory is missing, run the command above rather than guessing at an API shape.

## Anti-patterns

- Passing a bind target string where a parsed target is expected. Every metadata call wants the
  parsed form.
- Building fields with the API when a declaration would do. Declarative fields are greppable,
  checkable by `scan.py --check`, and renameable by `rename.py`; API-built ones are none of those.
- Forgetting `wrapInMDRC`. A mountable that is never wrapped never renders and never errors.
- Skipping the `component` argument. Without it the field leaks its subscriptions when the note
  closes.
