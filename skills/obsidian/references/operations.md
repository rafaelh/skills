# Common operations

Recipes for multi-step tasks. Read this when the user asks for an operation that combines several scripts.

## Build a Map of Content (MOC)

Goal: a note that links to every note in a folder (or matching a tag), grouped sensibly.

```python
from pathlib import Path
from vault_list import list_notes
from vault import locate_vault

vault = locate_vault(".")
notes = list_notes(vault, folder="3. Tech")

lines = ["# Tech MOC\n"]
for note in sorted(notes, key=lambda p: str(p.relative_to(vault))):
    name = note.stem
    rel = str(note.relative_to(vault).with_suffix(""))
    lines.append(f"- [[{rel}|{name}]]")

(vault / "3. Tech" / "MOC.md").write_text("\n".join(lines) + "\n")
```

Choices:
- Use `[[path/Name|Display]]` form to disambiguate; the display is the basename.
- Sort by full path so siblings group; switch to sorted-by-stem if folder doesn't matter.
- Skip notes already containing a `moc: true` frontmatter to avoid recursive listings.

## Audit broken wikilinks

Goal: list every wikilink whose target doesn't resolve to any note in the vault.

```python
from vault_list import list_notes
from vault import locate_vault
from links import parse_links

vault = locate_vault(".")
all_notes = list_notes(vault)
basenames = {p.stem for p in all_notes}
relpaths = {str(p.relative_to(vault).with_suffix("")) for p in all_notes}

# Aliases also count as resolvable names.
from vault_frontmatter import read

aliases = set()
for note in all_notes:
    fm, _ = read(note)
    aliases.update(fm.get("aliases") or [])

resolvable = basenames | relpaths | aliases

broken = []
for note in all_notes:
    text = note.read_text(encoding="utf-8")
    for link in parse_links(text):
        if link.target == "":  # self heading/block ref
            continue
        if link.target not in resolvable:
            broken.append((note, link))

for note, link in broken:
    print(f"{note}: {link.raw}")
```

Caveat: this approximates Obsidian's resolver. It does not handle case-only differences (Obsidian is case-insensitive, this script is case-sensitive). Acceptable for a first pass; for full fidelity, lowercase both sides.

## Extract every tag in the vault

```python
from collections import Counter
from vault_list import list_notes
from vault import locate_vault
from links import parse_tags
from vault_frontmatter import read

vault = locate_vault(".")
counts = Counter()
for note in list_notes(vault):
    fm, body = read(note)
    fm_tags = fm.get("tags") or []
    if isinstance(fm_tags, str):
        fm_tags = [fm_tags]
    for t in fm_tags:
        counts[t] += 1
    for t in parse_tags(body):
        counts[t.name] += 1

for tag, n in counts.most_common():
    print(f"{n:>5}  #{tag}")
```

## Merge two notes

There is no script for this — it is too policy-heavy. Use this checklist when doing it manually:

1. Decide which note is the survivor and which is the donor.
2. Concatenate donor body into survivor body, with a clear separator (`## From {donor name}`).
3. Merge frontmatter: union tags/aliases; ask the user about conflicting scalar properties.
4. Add donor's basename to survivor's `aliases` so old links keep resolving.
5. Run `backlinks.py DONOR.md` and rewrite each backlink:
   ```bash
   python3 scripts/links.py rewrite SOURCE.md "DonorName" "SurvivorName"
   ```
6. Move donor to `.trash/` (or delete) once backlinks all point at survivor.
7. If a `.canvas` file referenced the donor, update it manually (`canvas_validate.py` after).

## Bulk add a tag to notes matching a property

```python
from vault_list import list_notes
from vault import locate_vault
from vault_frontmatter import read, write

vault = locate_vault(".")
for note in list_notes(vault, has_property="status", property_value="draft"):
    fm, body = read(note)
    tags = list(fm.get("tags") or [])
    if "needs-review" not in tags:
        tags.append("needs-review")
    fm["tags"] = tags
    write(note, fm, body)
```

Always show a dry-run to the user before running a bulk write.

## Split a long note at heading boundaries

There is no script for this. The general flow:

1. Read the source note (`vault_frontmatter.read`).
2. Split the body on `^## ` (or whichever heading level is the splitting axis).
3. For each split, create a new note named after the heading, copy frontmatter (tags only, not custom properties), and write.
4. Replace the original note's body with a list of links to the new notes (essentially a MOC).
5. Run `backlinks.py ORIGINAL.md` and decide whether old backlinks should now point at the new notes — usually no, since the original now serves as a hub.

## Check vault health

A combined sweep before a major change:

```bash
# Parse everything; failures here usually mean malformed frontmatter.
python3 -c "
from vault_list import list_notes
from vault_frontmatter import read
from vault import locate_vault
for n in list_notes(locate_vault('.')):
    try:
        read(n)
    except Exception as e:
        print(f'{n}: {e}')
"

# Validate every canvas and base.
find . -name '*.canvas' -not -path '*/.obsidian/*' -exec python3 scripts/canvas_validate.py {} \;
find . -name '*.base'   -not -path '*/.obsidian/*' -exec python3 scripts/base_validate.py {} \;
```
