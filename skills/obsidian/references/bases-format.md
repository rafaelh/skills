# Bases format (`.base`)

Read this when reading or generating `.base` files. Bases is Obsidian's database-view feature; the file format is YAML and is still evolving — treat anything beyond the structural layout below as best-effort.

Validate with `scripts/base_validate.py FILE`.

## Top-level structure

```yaml
properties:           # optional: declarations / display overrides
  file.name:
    displayName: Item
  custom-key:
    displayName: Custom

views:                # required for the base to render
  - type: table
    name: Default
    filters: ...
    order: ...
    sort: ...

formulas: ...         # optional: named computed columns
```

`properties` and `formulas` are optional. `views` is required for the file to be useful, but `base_validate.py` allows missing `views` to support partial / templated bases.

## Property declarations

```yaml
properties:
  file.name:
    displayName: Title
  bloodbowl-tier:
    displayName: Tier
```

Keys are property paths. Built-in paths Obsidian exposes:

| Path                   | Meaning                                  |
|------------------------|------------------------------------------|
| `file.name`            | Filename without extension.              |
| `file.basename`        | Same as `file.name` in current versions. |
| `file.ext`             | File extension including dot (`.md`).    |
| `file.path`            | Vault-relative path.                     |
| `file.folder`          | Containing folder.                       |
| `file.size`            | Bytes.                                   |
| `file.ctime`           | Creation time.                           |
| `file.mtime`           | Modified time.                           |
| `note.<key>`           | Frontmatter property.                    |
| Bare key (e.g. `tags`) | Frontmatter property at the top level.   |

`displayName` is the only well-supported property field today. Others may exist; treat them as opaque.

## Views

Each view has a `type` and `name`, plus type-specific configuration:

```yaml
views:
  - type: table
    name: Table
    filters:
      and:
        - file.inFolder("notes")
        - file.ext == ".md"
    order:
      - file.name
      - tags
    sort:
      - property: file.name
        direction: ASC
```

Known view types: `table`, `card`. Others may appear in newer builds. The validator accepts any string `type`.

### Filters

Filters are formulas. The two structures seen in real bases:

```yaml
# Boolean tree
filters:
  and:
    - file.inFolder("Tasks")
    - status != "done"
  or:
    - priority == "high"
    - due < now()

# Flat list (implicit AND)
filters:
  - file.ext == ".md"
```

The validator does NOT typecheck formula strings — they're free-form expressions evaluated by Obsidian.

### Order

```yaml
order:
  - file.name
  - tags
  - some-frontmatter-key
```

A list of property paths. Order in the list = column order in table view (or field order in card view).

### Sort

```yaml
sort:
  - property: file.name
    direction: ASC
  - property: file.mtime
    direction: DESC
```

`direction` must be `ASC` or `DESC`. The validator rejects other values.

## Common operators in formulas

(For readers writing filters; the validator does not enforce these.)

- Comparison: `==`, `!=`, `<`, `<=`, `>`, `>=`
- Boolean: `and()`, `or()`, `not()`, plus `&&`, `||`, `!`
- String: `contains()`, `startsWith()`, `endsWith()`
- File helpers: `file.inFolder("path")`, `file.hasTag("tag")`, `file.hasProperty("key")`
- Time: `now()`, `today()`, ISO date literals (`date("2026-05-02")`)

## Gotchas

- **Bases is moving.** New view types and operators may appear; the validator is intentionally lenient on type strings.
- **Property paths are case-sensitive.** `Tags` and `tags` are different; use whichever appears in the vault's frontmatter.
- **`file.basename` vs `file.name`** — currently equivalent for `.md` files but may diverge; prefer `file.name`.
- **Bare keys vs `note.<key>`** — both work for frontmatter properties at the top level. Older bases use bare; newer bases use `note.`. Match what's already in the vault.
- **Renaming notes does not break a base.** Bases query by formula, not by file id, so a rename won't orphan rows. Renaming a *property* in frontmatter will silently empty its column unless you update the base too.

## Source

Regenerated from <https://obsidian.md/help/bases>, <https://obsidian.md/help/bases-syntax>, plus inspection of real-world `.base` files. Run `scripts/refresh_docs.py` when upstream changes — Bases docs evolve faster than the rest of Obsidian's help.
