# JS Engine

Read this when writing a ```` ```js-engine ```` block, a ```` ```meta-bind-js-view ```` block, or a
`js` / `inlineJS` button action. Meta Bind's own API (see [api.md](api.md)) is called *from* these
blocks, so their host surface belongs here.

JS Engine is a **separate plugin** (`mProjectsCode/obsidian-js-engine-plugin`, manifest id
`js-engine`). A vault can run Meta Bind without it. Everything below is pinned to **0.3.6**; it is
hand-written rather than generated, so re-read `packages/js-engine-api/src/index.ts` (191 lines)
whenever that version moves.

## Block types

| Fence | Runs | Gets |
|---|---|---|
| ```` ```js-engine ```` | JS, renders the returned value | full globals below |
| ```` ```js-engine-debug ```` | identical, plus a rerun/stats icon | same |
| ```` ```meta-bind-js-view ```` | JS re-run whenever a bound value changes | globals plus `context.bound` |

## Globals inside a block

| Name | Is |
|---|---|
| `engine` | the JS Engine API — everything below |
| `app` | Obsidian's `App` |
| `component` | the lifecycle `Component`; pass it to anything that needs unmounting |
| `container` | the `HTMLElement` the block renders into, when there is one |
| `context` | execution context: `context.file`, `context.metadata`, `context.block` |
| `obsidian` | the Obsidian module, for `obsidian.Notice` and friends |

Return a value to render it. A returned string renders as **plain text**; wrap it in
`engine.markdown.create()` to render as markdown.

## `engine`

```js
engine.markdown.create(str)              // MarkdownString — renders as markdown
engine.markdown.createBuilder()          // MarkdownBuilder, see below
engine.getPlugin('obsidian-meta-bind-plugin')   // another plugin instance, or undefined
engine.getObsidianModule()               // same module as the `obsidian` global
engine.importJs('lib.js')                // await; imports a JS file from the vault
engine.reactive(fn, ...initialArgs)      // a ReactiveComponent that re-renders on refresh
engine.resolveLinkToTFile(link, sourcePath)
engine.parseLink(link)
engine.query.outgoingLinks(file)         // [{file, metadata, tags, frontmatterTags}]
engine.query.incomingLinks(file)
engine.message                           // notices
engine.prompt                            // suggester / modal prompts
engine.lib                               // bundled helper libraries
```

### The markdown builder

```js
const builder = engine.markdown.createBuilder();
builder.createHeading(2, 'Test Heading');
builder.createParagraph('This is a test paragraph.');
return builder;
```

Element constructors: `createText`, `createBoldText`, `createCursiveText`, `createUnderlinedText`,
`createHighlightedText`, `createCode`, `createParagraph`, `createHeading`, `createBlockQuote`,
`createCallout`, `createCollapsibleCallout`, `createCodeBlock`, `createTable`, `createList`,
`createOrderedList`.

Build with these rather than concatenating markdown strings — the builder escapes for you, and a
returned builder renders without the `engine.markdown.create()` wrapper.

## `meta-bind-js-view` blocks

The block has a header, then `---`, then the code:

````markdown
```meta-bind-js-view
{count} as count
{enemy} and children as enemies
save to {doubled}
hidden
---
return engine.markdown.create(`count is ${context.bound.count}`);
```
````

- `{bindTarget} as name` — binds a value and names it. Read it as `context.bound.name`.
- `and children` — also re-run when a *nested* property under that target changes.
- `save to {bindTarget}` — optional; the returned value is written there.
- `hidden` — optional; run without rendering.
- `---` on its own line separates header from code. It is required.

The **alias is what the JS sees**, not the property name. That decoupling is deliberate and useful:
`rename.py --property count hitPoints` rewrites `{count}` to `{hitPoints}` and leaves `as count`
alone, so `context.bound.count` keeps working.

## Generating Meta Bind syntax from JS

A common pattern — build a declaration string and render it as markdown:

```js
const options = context.bound.options.map(x => `option(${x})`).join(', ');
return engine.markdown.create(`\`INPUT[inlineSelect(${options}):selected]\``);
```

The escaped backticks matter: the declaration must end up inside an inline code span to be picked
up. This skill's parser deliberately does **not** look inside JS, so declarations generated this way
are invisible to `scan.py`. That is the trade — dynamic fields cost you static checking.

## Anti-patterns

- Returning a raw markdown string and expecting it to render. Wrap it, or use the builder.
- Assuming `js-engine` is installed because Meta Bind is. Check
  `.obsidian/plugins/js-engine/manifest.json`.
- Reaching for a `js-view` where a `VIEW[…][math:…]` would do. Math view fields are declarative,
  checkable and renameable; JS is none of those.
- Doing metadata writes with `setMetadata` in a loop. Use `updateMetadata` — see [api.md](api.md).
