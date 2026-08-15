# Meta Bind declaration syntax

Read this before writing or editing any `INPUT[…]`, `VIEW[…]` or `BUTTON[…]` declaration. The
grammar below mirrors the plugin's own parser combinators
(`packages/core/src/parsers/nomParsers/`), not the prose docs — where the two disagree, this wins.

For which field types and arguments exist, read `field-spec.json`. This file is about *shape*.

## The two hosts

A declaration is delimited by its host, and the whole host content must be exactly one declaration.

| Host | Written as | Renders |
|---|---|---|
| Inline code span | `` `INPUT[toggle:done]` `` | inline, in the flow of a sentence |
| Fenced block | ```` ```meta-bind ```` … ```` ``` ```` | as a block |

Fenced declarations may span lines freely — whitespace is insignificant between tokens:

````markdown
```meta-bind
INPUT[select(
option(option a),
option(option b)
):choice]
```
````

**Not every field type renders inline.** `select`, `multiSelect`, `editor`, `progressBar`, `list`,
`listSuggester` and `imageListSuggester` are block-only — `allow_inline: false` in
`field-spec.json`. Putting one in a code span is a silent no-render; `scan.py --check` reports it as
`metabind.inline-not-allowed`.

Fields *do* render inside callouts, table cells and list items. Those are ordinary markdown
contexts, not special hosts.

Declarations inside a plain ```` ```js ```` or ```` ```dataview ```` fence are inert, and this
skill's parser ignores them. Frontmatter is not scanned either.

## Input fields

```
INPUT[type(arg, arg):bindTarget]
INPUT[templateName][type(arg, arg):bindTarget]
```

- The type is required in the first form. `INPUT[:count]` is a parse error, not a default.
- In the template form the template supplies the type, so `INPUT[myTemplate][]` is legal.
- Arguments and bind target are both optional: `INPUT[text]` parses.

## View fields

```
VIEW[template]
VIEW[template][type(arg):writeTarget]
```

The template is free text with `{bindTarget}` placeholders. The second bracket group is optional —
`VIEW[{a} + {b}]` is a complete, valid view field, and its type defaults. Give it a type when you
want evaluation rather than interpolation:

```markdown
`VIEW[{count} * 2][math:doubled]`
```

Inside a view template, `\[`, `\]`, `\{`, `\}` and `\\` are the escapes. Everything else is literal.

## Buttons

```
BUTTON[id]
BUTTON[id, otherId, thirdId]
```

An id may not contain `[`, `]`, `,` or `^`. Whitespace around ids is trimmed. This references a
button *config* declared in a ```` ```meta-bind-button ```` block somewhere in the vault — see
[buttons.md](buttons.md).

## Bind targets

```
[storageType^][storagePath#]propertyPath
```

| Form | Means |
|---|---|
| `count` | property `count` in this note's frontmatter |
| `Other Note#title` | property `title` in another note's frontmatter |
| `nested.object` | a nested property |
| `nested["object"]` | the same, when the key needs quoting |
| `list[0]` | element 0 of a list property |
| `memory^scratch` | note-scoped memory; never written to frontmatter |
| `globalMemory^shared` | vault-scoped memory; never written to frontmatter |

The storage path may not contain `{}[]#^|:?`. The property path is dot-separated identifiers, each
optionally followed by `["key"]` or `[0]` accessors. Identifiers are unicode — `INPUT[text:こんにちは]`
is valid.

**Meta Bind creates the property on first write.** A bind target naming a key absent from
frontmatter is normal in a fresh note, which is why `scan.py --check` only reports it under
`--strict`.

## Field arguments

```
argumentName                     a flag, no values
argumentName(value)              one value
argumentName(value, otherValue)  two values
```

Values are either single-quoted strings or a run of any characters except `(`, `)`, `'` and `,`.
That exception list is short on purpose: brackets and spaces are ordinary value characters, so
`option(80, Griffon [flying])` and `option(1, Normal Pace)` both parse as written.

Inside a single-quoted string, `\'` is a literal quote and `\\` a literal backslash. Any other
`\x` stays as the two characters it is written as:

```markdown
`INPUT[inlineSelect(option(0, 'don\'t do this'), option(1, 'do this \\')):choice]`
```

Quote a value when it must contain `(`, `)`, `,` or a leading/trailing space. Otherwise leave it
bare — the example vault overwhelmingly does.

An unquoted value keeps its trailing whitespace, so `option(a , b)` yields `"a "`, not `"a"`. Put
the comma directly after the value.

## Anti-patterns

- Matching declarations with `\[(.+?)\]` or any other regex. Argument values contain brackets;
  `scan.py --list` exists so you never have to.
- Assuming `VIEW[…]` needs a second bracket group. It does not.
- Writing `^memory` — the scope goes *before* the caret: `memory^prop`.
- Adding a bind target to a field type that ignores it, or an argument to a field type that
  rejects it. `field-spec.json` records which arguments are legal where; `scan.py --check`
  enforces it.
