# Canvas format (`.canvas`)

Read this when reading or generating `.canvas` files. The format is JSON Canvas — an open spec used by Obsidian and a few other tools.

Validate any canvas you generate with `scripts/canvas_validate.py FILE`.

## Top-level structure

```json
{
  "nodes": [ ... ],
  "edges": [ ... ]
}
```

Both arrays are required (use `[]` for empty). Anything outside these two keys is ignored by Obsidian but preserved on save.

## Node common fields

Every node has:

| Field    | Type   | Required | Notes                                                                             |
|----------|--------|----------|-----------------------------------------------------------------------------------|
| `id`     | string | yes      | Unique within the canvas. Obsidian uses 16-hex-char ids; any unique string works. |
| `type`   | string | yes      | One of `text`, `file`, `link`, `group`.                                           |
| `x`      | number | yes      | Top-left x in canvas units. Negatives allowed.                                    |
| `y`      | number | yes      | Top-left y. Y grows downward.                                                     |
| `width`  | number | yes      | Pixel width at zoom = 1.                                                          |
| `height` | number | yes      | Pixel height at zoom = 1.                                                         |
| `color`  | string | no       | Hex `"#rrggbb"` or named preset `"1"` through `"6"` (the six theme color slots).  |

## Node types

### `text`

```json
{
  "id": "abc",
  "type": "text",
  "x": 0, "y": 0, "width": 250, "height": 100,
  "text": "# A heading\n\nMarkdown body."
}
```

Required extra: `text` (string). Markdown is rendered.

### `file`

```json
{
  "id": "def",
  "type": "file",
  "x": 0, "y": 0, "width": 400, "height": 300,
  "file": "notes/Alpha.md",
  "subpath": "#Heading"
}
```

Required extra: `file` (vault-relative path including extension).
Optional: `subpath` — a heading or block reference like `#Section` or `#^abc`.

### `link`

```json
{
  "id": "ghi",
  "type": "link",
  "x": 0, "y": 0, "width": 300, "height": 200,
  "url": "https://example.com"
}
```

Required extra: `url` (string).

### `group`

```json
{
  "id": "jkl",
  "type": "group",
  "x": 0, "y": 0, "width": 600, "height": 400,
  "label": "Things",
  "background": "image.png",
  "backgroundStyle": "cover"
}
```

No required type-specific fields. Optional: `label`, `background`, `backgroundStyle` (one of `cover`, `ratio`, `repeat`).

## Edges

```json
{
  "id": "e1",
  "fromNode": "abc",
  "fromSide": "right",
  "fromEnd": "none",
  "toNode": "def",
  "toSide": "left",
  "toEnd": "arrow",
  "color": "1",
  "label": "implies"
}
```

Required: `id`, `fromNode`, `toNode`. Optional:

- `fromSide` / `toSide`: `top | right | bottom | left`. Determines anchor point.
- `fromEnd` / `toEnd`: `none | arrow`. Default `none`.
- `color`: as in nodes.
- `label`: text rendered along the edge.

## Generation patterns

When generating a canvas programmatically:

1. Use ascending integer ids (`"n1"`, `"n2"`, …) or 16-hex ids — anything unique.
2. Lay out nodes on a coarse grid; defaults Obsidian uses are 250 × 100 for text nodes, 400 × 300 for file nodes.
3. Default edge: `toEnd: "arrow"`, `fromEnd: "none"`, no sides set (Obsidian picks the closest side).
4. Always run `canvas_validate.py` after writing.

## Gotchas

- **Coordinates are not pixels.** They're virtual canvas units. Use 250 × 100 for a small node.
- **`file` paths are vault-relative.** Do not include a leading `/`. Use forward slashes even on Windows.
- **Renaming a referenced note breaks the canvas.** `rename_note.py` does not rewrite canvas references — it warns. Update them with a JSON-aware tool.
- **Backgrounds in groups** need the image to exist in the vault. If missing, Obsidian renders the group with no background but no error.
- **Pretty-printing matters for diffs.** Obsidian writes compact JSON. If you reformat, expect every save to produce a diff. Match the existing file's style.

## Source

JSON Canvas spec: <https://jsoncanvas.org/spec/1.0/>. Obsidian's Canvas help: <https://obsidian.md/help/canvas>.
