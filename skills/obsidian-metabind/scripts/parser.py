#!/usr/bin/env python3
# agent-tool: false
# /// script
# requires-python = ">=3.14"
# dependencies = [
#   "pyyaml>=6.0",
# ]
# ///
"""Meta Bind declaration parser: the shared library behind scan.py and rename.py.

Mirrors the grammar of the plugin's own parser combinators
(`packages/core/src/parsers/nomParsers/`) rather than approximating it with
regexes. Argument values may contain brackets (`option(60, Griffon [flying])`),
so a declaration's extent is fixed by its *host* — a backtick code span or a
fenced block — and the grammar must then consume that host exactly, which is
what upstream's trailing `eof()` demands.

Library API:
    locate_vault(path) -> Path
    iter_notes(vault) -> Iterator[Path]
    read_frontmatter(path) -> dict[str, object]
    load_spec(path=None) -> FieldSpec
    parse_note(path, text=None) -> list[Declaration]
    parse_declaration(text, source, host, start, end, fence_kind=None) -> Declaration | None
    button_actions(config) -> list[Any]

Every parsed node carries a Span of absolute offsets into the file text, so
rename.py can rewrite a bind target in place without re-finding it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any, cast

import yaml

if TYPE_CHECKING:
    from collections.abc import Iterator

PathLike = str | Path

SKIP_DIRS: frozenset[str] = frozenset({".obsidian", ".trash", ".git"})

DEFAULT_SPEC_PATH = Path(__file__).resolve().parent.parent / "references" / "field-spec.json"

#: Fenced block languages that name their declaration kind outright. ``js-engine``
#: belongs to the JS Engine plugin but is recognised here because Meta Bind's API
#: is called from it. ``meta-bind`` is absent: its kind comes from the body's
#: ``INPUT[`` / ``VIEW[`` / ``BUTTON[`` prefix, like an inline code span's.
_FENCE_DECLARATION_KINDS: dict[str, str] = {
    "meta-bind-button": "button-config",
    "meta-bind-embed": "embed",
    "meta-bind-js-view": "js-view",
    "js-engine": "js-engine",
}

#: Every fenced block language Meta Bind claims.
FENCE_KINDS: frozenset[str] = frozenset({"meta-bind", *_FENCE_DECLARATION_KINDS})

#: Characters a bind target's file-path segment may not contain (`P_FilePath`).
_FILE_PATH_STOP = frozenset("{}[]#^|:?")

#: Terminators of a YAML frontmatter block, and the escapes that unescape in a
#: quoted argument value.
_FRONTMATTER_END = frozenset({"---", "..."})
_UNESCAPES = frozenset({"'", "\\"})
_QUOTES = frozenset({"'", '"'})

_IDENT_START_EXTRA = frozenset("_$")
_IDENT_REST_EXTRA = frozenset("-_$")


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Span:
    """Absolute [start, end) offsets into the containing file's text."""

    start: int
    end: int


@dataclass(frozen=True, slots=True)
class PropAccess:
    """One step of a bind target's property path.

    ``kind`` is ``ident`` (``foo``), ``quoted`` (``["foo"]``) or ``index``
    (``[0]``). Only the first two name a property; an index cannot be renamed.
    """

    kind: str
    name: str
    span: Span


@dataclass(frozen=True, slots=True)
class BindTarget:
    """`[storageType^][storagePath#]propertyPath` — see BindTargetNomParsers.ts."""

    storage_type: str | None
    storage_type_span: Span | None
    storage_path: str | None
    storage_path_span: Span | None
    props: tuple[PropAccess, ...]
    span: Span

    @property
    def prop_path(self) -> tuple[str, ...]:
        return tuple(access.name for access in self.props)

    def render(self) -> str:
        parts: list[str] = []
        if self.storage_type is not None:
            parts.append(f"{self.storage_type}^")
        if self.storage_path is not None:
            parts.append(f"{self.storage_path}#")
        for index, access in enumerate(self.props):
            if access.kind == "ident":
                parts.append(access.name if index == 0 else f".{access.name}")
            elif access.kind == "quoted":
                parts.append(f'["{access.name}"]')
            else:
                parts.append(f"[{access.name}]")
        return "".join(parts)


@dataclass(frozen=True, slots=True)
class FieldArgument:
    name: str
    values: tuple[str, ...]
    span: Span


@dataclass(frozen=True, slots=True)
class ParseError:
    message: str
    offset: int


@dataclass(frozen=True, slots=True)
class Declaration:
    """One Meta Bind declaration located in a note.

    ``kind`` is one of ``input``, ``view``, ``js-view``, ``button-group``,
    ``button-config``, ``embed`` or ``js-engine``. Fields not meaningful for a
    kind stay at their empty default rather than being absent, so callers never
    branch on attribute presence.
    """

    kind: str
    host: str  # "inline" or "fence"
    file: Path
    line: int
    column: int
    raw: str
    span: Span
    field_type: str | None = None
    template_name: str | None = None
    arguments: tuple[FieldArgument, ...] = ()
    bind_target: BindTarget | None = None
    read_targets: tuple[BindTarget, ...] = ()
    button_ids: tuple[str, ...] = ()
    button_config: dict[str, Any] | None = None
    embed_target: str | None = None
    js_code: str | None = None
    errors: tuple[ParseError, ...] = ()

    @property
    def bind_targets(self) -> tuple[BindTarget, ...]:
        """Every bind target in the declaration, write target first."""
        if self.bind_target is None:
            return self.read_targets
        return (self.bind_target, *self.read_targets)


# ---------------------------------------------------------------------------
# Grammar primitives
# ---------------------------------------------------------------------------


class _GrammarError(Exception):
    def __init__(self, message: str, offset: int) -> None:
        super().__init__(message)
        self.message = message
        self.offset = offset


def _skip_ws(s: str, i: int) -> int:
    while i < len(s) and s[i].isspace():
        i += 1
    return i


def _ident(s: str, i: int, what: str = "identifier") -> tuple[str, int]:
    start = i
    if i >= len(s) or not (s[i].isalpha() or s[i] in _IDENT_START_EXTRA):
        raise _GrammarError(f"expected {what}", i)
    i += 1
    while i < len(s) and (s[i].isalnum() or s[i] in _IDENT_REST_EXTRA):
        i += 1
    return s[start:i], i


def _ident_with_spaces(s: str, i: int, what: str) -> tuple[str, int]:
    start = i
    _, i = _ident(s, i, what)
    while True:
        after_ws = _skip_ws(s, i)
        try:
            _, j = _ident(s, after_ws)
        except _GrammarError:
            break
        i = j
    return s[start:i], i


def _quoted_string(s: str, i: int, quote: str) -> tuple[str, int]:
    """Parse a quoted string. `\\'` and `\\\\` unescape; any other `\\x` stays literal."""
    i += 1  # opening quote
    out: list[str] = []
    while True:
        if i >= len(s):
            raise _GrammarError(f"unterminated {quote}-quoted string", i)
        char = s[i]
        if char == "\\":
            if i + 1 >= len(s):
                raise _GrammarError("trailing escape character", i)
            escaped = s[i + 1]
            out.append(escaped if escaped in _UNESCAPES else "\\" + escaped)
            i += 2
            continue
        if char == quote:
            return "".join(out), i + 1
        out.append(char)
        i += 1


def _bracket_access(s: str, i: int) -> tuple[PropAccess, int]:
    start = i
    j = i + 1
    if j < len(s) and s[j].isdigit():
        k = j
        while k < len(s) and s[k].isdigit():
            k += 1
        if k < len(s) and s[k] == "]":
            return PropAccess("index", s[j:k], Span(start, k + 1)), k + 1
    if j < len(s) and s[j] == '"':
        value, k = _quoted_string(s, j, '"')
        if k < len(s) and s[k] == "]":
            return PropAccess("quoted", value, Span(start, k + 1)), k + 1
    raise _GrammarError('expected [<number>] or ["<key>"]', start)


def _prop_path(s: str, i: int) -> tuple[tuple[PropAccess, ...], int]:
    accesses: list[PropAccess] = []

    def brackets(i: int) -> int:
        while i < len(s) and s[i] == "[":
            access, i = _bracket_access(s, i)
            accesses.append(access)
        return i

    if i < len(s) and s[i] == "[":
        i = brackets(i)
    else:
        start = i
        name, i = _ident(s, i, "property name")
        accesses.append(PropAccess("ident", name, Span(start, i)))
        i = brackets(i)

    while i < len(s) and s[i] == ".":
        i += 1
        start = i
        name, i = _ident(s, i, "property name")
        accesses.append(PropAccess("ident", name, Span(start, i)))
        i = brackets(i)

    return tuple(accesses), i


def _bind_target(s: str, i: int) -> tuple[BindTarget, int]:
    start = i
    storage_type: str | None = None
    storage_type_span: Span | None = None
    try:
        name, j = _ident(s, i)
    except _GrammarError:
        pass
    else:
        if j < len(s) and s[j] == "^":
            storage_type, storage_type_span = name, Span(i, j)
            i = j + 1

    storage_path: str | None = None
    storage_path_span: Span | None = None
    j = i
    while j < len(s) and s[j] not in _FILE_PATH_STOP:
        j += 1
    if j < len(s) and s[j] == "#":
        storage_path, storage_path_span = s[i:j], Span(i, j)
        i = j + 1

    props, i = _prop_path(s, i)
    return (
        BindTarget(
            storage_type, storage_type_span, storage_path, storage_path_span, props, Span(start, i)
        ),
        i,
    )


def _try_argument_value(s: str, i: int) -> tuple[str, int] | None:
    if i < len(s) and s[i] == "'":
        return _quoted_string(s, i, "'")
    j = i
    while j < len(s) and s[j] not in "()',":
        j += 1
    if j == i:
        return None
    return s[i:j], j


def _try_field_argument(s: str, i: int) -> tuple[FieldArgument, int] | None:
    start = i
    try:
        name, j = _ident(s, i)
    except _GrammarError:
        return None
    values: tuple[str, ...] = ()
    if j < len(s) and s[j] == "(":
        k = _skip_ws(s, j + 1)
        values, k = _separated(s, k, _try_argument_value)
        k = _skip_ws(s, k)
        if k >= len(s) or s[k] != ")":
            raise _GrammarError(f'expected ")" to close the values of argument "{name}"', k)
        j = k + 1
    return FieldArgument(name, values, Span(start, j)), j


def _separated[T](s: str, i: int, parse_one: Parser[T]) -> tuple[tuple[T, ...], int]:
    """Comma-separated list, backtracking to before a comma with nothing after it."""
    first = parse_one(s, i)
    if first is None:
        return (), i
    items = [first[0]]
    i = first[1]
    while True:
        after_item = _skip_ws(s, i)
        if after_item >= len(s) or s[after_item] != ",":
            break
        after_comma = _skip_ws(s, after_item + 1)
        following = parse_one(s, after_comma)
        if following is None:
            break
        items.append(following[0])
        i = following[1]
    return tuple(items), i


if TYPE_CHECKING:
    from collections.abc import Callable

    type Parser[T] = Callable[[str, int], tuple[T, int] | None]


def _inner_field(
    s: str, i: int, *, require_type: bool
) -> tuple[str | None, tuple[FieldArgument, ...], BindTarget | None, int]:
    """`type(args):bindTarget` — every part optional except where the caller says otherwise."""
    i = _skip_ws(s, i)
    field_type: str | None = None
    try:
        field_type, i = _ident(s, i, "field type")
    except _GrammarError:
        if require_type:
            raise
    i = _skip_ws(s, i)

    arguments: tuple[FieldArgument, ...] = ()
    if i < len(s) and s[i] == "(":
        j = _skip_ws(s, i + 1)
        arguments, j = _separated(s, j, _try_field_argument)
        j = _skip_ws(s, j)
        if j >= len(s) or s[j] != ")":
            raise _GrammarError('expected ")" to close the argument list', j)
        i = _skip_ws(s, j + 1)

    bind_target: BindTarget | None = None
    if i < len(s) and s[i] == ":":
        i = _skip_ws(s, i + 1)
        bind_target, i = _bind_target(s, i)
        i = _skip_ws(s, i)

    return field_type, arguments, bind_target, i


def _expect(s: str, i: int, literal: str) -> int:
    if not s.startswith(literal, i):
        raise _GrammarError(f'expected "{literal}"', i)
    return i + len(literal)


def _expect_end(s: str, i: int, end: int) -> None:
    while i < end and s[i].isspace():
        i += 1
    if i != end:
        raise _GrammarError(f"unexpected trailing input {s[i:end]!r}", i)


# ---------------------------------------------------------------------------
# Declaration grammars
# ---------------------------------------------------------------------------


def _parse_input(s: str, start: int, end: int) -> dict[str, Any]:
    i = _expect(s, start, "INPUT")
    i = _expect(s, i, "[")

    # `INPUT[template][type(args):target]` — try the template form first, exactly
    # as P_InputFieldDeclaration's ordered choice does.
    try:
        template, j = _ident_with_spaces(s, i, "template name")
        j = _skip_ws(s, j)
        j = _expect(s, j, "]")
        j = _skip_ws(s, j)
        j = _expect(s, j, "[")
        field_type, arguments, bind_target, j = _inner_field(s, j, require_type=False)
        j = _expect(s, j, "]")
    except _GrammarError:
        pass
    else:
        _expect_end(s, j, end)
        return {
            "template_name": template,
            "field_type": field_type,
            "arguments": arguments,
            "bind_target": bind_target,
        }

    field_type, arguments, bind_target, i = _inner_field(s, i, require_type=True)
    i = _expect(s, i, "]")
    _expect_end(s, i, end)
    return {
        "template_name": None,
        "field_type": field_type,
        "arguments": arguments,
        "bind_target": bind_target,
    }


def _view_template_string(s: str, i: int) -> int:
    while i < len(s):
        if s[i] == "\\":
            if i + 1 >= len(s):
                break
            i += 2
            continue
        if s[i] in "{}[]":
            break
        i += 1
    return i


def _parse_view(s: str, start: int, end: int) -> dict[str, Any]:
    i = _expect(s, start, "VIEW")
    i = _expect(s, i, "[")

    read_targets: list[BindTarget] = []
    i = _view_template_string(s, i)
    while i < len(s) and s[i] == "{":
        target, j = _bind_target(s, i + 1)
        if j >= len(s) or s[j] != "}":
            raise _GrammarError('expected "}" to close the bind target', j)
        read_targets.append(target)
        i = _view_template_string(s, j + 1)

    i = _expect(s, i, "]")
    i = _skip_ws(s, i)

    field_type: str | None = None
    arguments: tuple[FieldArgument, ...] = ()
    write_target: BindTarget | None = None
    if i < len(s) and s[i] == "[":
        field_type, arguments, write_target, i = _inner_field(s, i + 1, require_type=False)
        i = _expect(s, i, "]")

    _expect_end(s, i, end)
    return {
        "field_type": field_type,
        "arguments": arguments,
        "bind_target": write_target,
        "read_targets": tuple(read_targets),
    }


def _parse_button_group(s: str, start: int, end: int) -> dict[str, Any]:
    i = _expect(s, start, "BUTTON")
    i = _expect(s, i, "[")

    ids: list[str] = []
    while True:
        j = i
        while j < len(s) and s[j] not in "[],^":
            j += 1
        ids.append(s[i:j].strip())
        i = j
        after_ws = _skip_ws(s, i)
        if after_ws < len(s) and s[after_ws] == ",":
            i = _skip_ws(s, after_ws + 1)
            continue
        break

    i = _expect(s, i, "]")
    _expect_end(s, i, end)
    if not any(ids):
        raise _GrammarError("button group references no button ids", start)
    return {"button_ids": tuple(ids)}


_JS_VIEW_MAPPING_RE = re.compile(
    r"^\{(?P<target>[^}]*)\}(?P<children> and children)? as (?P<name>.+)$"
)
_JS_VIEW_SAVE_RE = re.compile(r"^save to \{(?P<target>[^}]*)\}$")


def _parse_js_view(s: str, start: int, end: int) -> dict[str, Any]:
    """`{prop} as name` lines, optional `save to {prop}` / `hidden`, `---`, then JS."""
    body = s[start:end]
    separator = re.search(r"^---$", body, re.MULTILINE)
    if separator is None:
        raise _GrammarError('js view field has no "---" separating its header from its code', start)
    header_end = start + separator.start()

    read_targets: list[BindTarget] = []
    write_target: BindTarget | None = None
    offset = start
    for raw_line in s[start:header_end].splitlines(keepends=True):
        stripped = raw_line.strip()
        line_start = offset + (len(raw_line) - len(raw_line.lstrip()))
        offset += len(raw_line)
        if not stripped:
            continue
        if stripped == "hidden":
            continue
        if _JS_VIEW_SAVE_RE.match(stripped) is not None:
            write_target, _ = _bind_target(s, line_start + len("save to {"))
            continue
        if _JS_VIEW_MAPPING_RE.match(stripped) is None:
            raise _GrammarError(f"expected `{{prop}} as name`, got {stripped!r}", line_start)
        target, _ = _bind_target(s, line_start + 1)
        read_targets.append(target)

    return {
        "bind_target": write_target,
        "read_targets": tuple(read_targets),
        "js_code": s[start + separator.end() : end].strip(),
    }


_BIND_TARGET_LINE_RE = re.compile(r"^(\s*-?\s*bindTarget:\s*)(?P<value>\S.*?)\s*$")
_EMBED_RE = re.compile(r"^!?\[\[(?P<target>[^\]|]+)(\|[^\]]*)?\]\]$")


def _parse_embed(s: str, start: int, end: int) -> dict[str, Any]:
    body = s[start:end].strip()
    match = _EMBED_RE.match(body)
    if match is None:
        raise _GrammarError(f"expected an embed wikilink like [[Note]], got {body!r}", start)
    return {"embed_target": match.group("target").strip()}


# ---------------------------------------------------------------------------
# Declaration assembly
# ---------------------------------------------------------------------------


def _line_col(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    line_start = text.rfind("\n", 0, offset) + 1
    return line, offset - line_start + 1


def _declaration_kind(body: str, fence_kind: str | None) -> str | None:
    if fence_kind in _FENCE_DECLARATION_KINDS:
        return _FENCE_DECLARATION_KINDS[fence_kind]
    if body.startswith("INPUT["):
        return "input"
    if body.startswith("VIEW["):
        return "view"
    if body.startswith("BUTTON["):
        return "button-group"
    return None


def _parse_button_config(
    text: str, start: int, end: int
) -> tuple[dict[str, Any], tuple[ParseError, ...]]:
    body = text[start:end]
    try:
        loaded: Any = yaml.safe_load(body)
    except yaml.YAMLError as exc:
        return {}, (ParseError(f"button YAML is not parseable: {exc}", start),)
    if loaded is None:
        return {}, (ParseError("button config is empty", start),)
    if not isinstance(loaded, dict):
        return {}, (ParseError("button config is not a YAML mapping", start),)
    config = cast("dict[str, Any]", loaded)

    # Bind targets inside button YAML are plain strings; parsing them off the
    # `bindTarget:` lines keeps their file offsets, which the YAML load discards.
    read_targets: list[BindTarget] = []
    errors: list[ParseError] = []
    offset = start
    for raw_line in body.splitlines(keepends=True):
        line_start = offset
        offset += len(raw_line)
        match = _BIND_TARGET_LINE_RE.match(raw_line)
        if match is None:
            continue
        value_start = line_start + len(match.group(1))
        value = match.group("value")
        quote = value[0] if value[:1] in _QUOTES else ""
        if quote:
            value = value.strip(quote)
            value_start += 1
        try:
            target, consumed = _bind_target(text, value_start)
        except _GrammarError as exc:
            errors.append(ParseError(f"button bindTarget is malformed: {exc.message}", exc.offset))
            continue
        if consumed != value_start + len(value):
            errors.append(ParseError(f"button bindTarget is malformed: {value!r}", value_start))
            continue
        read_targets.append(target)

    return {"button_config": config, "read_targets": tuple(read_targets)}, tuple(errors)


def button_actions(config: dict[str, Any]) -> list[Any]:
    """Every action a button config declares, from `action:` and/or `actions:`.

    Upstream rejects a config setting both, but this reads whatever is there so
    callers can report on a config that does.
    """
    actions: list[Any] = []
    if "action" in config:
        actions.append(config["action"])
    raw_actions = config.get("actions")
    if isinstance(raw_actions, list):
        actions.extend(cast("list[Any]", raw_actions))
    return actions


_PARSERS = {
    "input": _parse_input,
    "view": _parse_view,
    "button-group": _parse_button_group,
    "js-view": _parse_js_view,
    "embed": _parse_embed,
}


def parse_declaration(
    text: str, source: Path, host: str, start: int, end: int, fence_kind: str | None = None
) -> Declaration | None:
    """Parse the declaration occupying `text[start:end]`, or None if it isn't one."""
    raw = text[start:end]
    body = raw.strip()
    kind = _declaration_kind(body, fence_kind)
    if kind is None:
        return None

    inner_start = start + (len(raw) - len(raw.lstrip()))
    inner_end = inner_start + len(body)
    line, column = _line_col(text, inner_start)
    base: dict[str, Any] = {
        "kind": kind,
        "host": host,
        "file": source,
        "line": line,
        "column": column,
        "raw": body,
        "span": Span(inner_start, inner_end),
    }

    if kind == "js-engine":
        return Declaration(**base, js_code=body)
    if kind == "button-config":
        parsed, errors = _parse_button_config(text, inner_start, inner_end)
        return Declaration(**base, **parsed, errors=errors)

    try:
        parsed = _PARSERS[kind](text, inner_start, inner_end)
    except _GrammarError as exc:
        return Declaration(**base, errors=(ParseError(exc.message, exc.offset),))
    return Declaration(**base, **parsed)


# ---------------------------------------------------------------------------
# Note scanning
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^(?P<indent>[ ]{0,3})(?P<marker>`{3,}|~{3,})[ \t]*(?P<info>[^\s`]*)")


@dataclass(frozen=True, slots=True)
class _Region:
    start: int
    end: int
    fence_kind: str | None


def _split_regions(text: str) -> tuple[list[_Region], list[_Region]]:
    """Return (fenced regions with a Meta Bind info string, prose regions)."""
    fenced: list[_Region] = []
    prose: list[_Region] = []

    lines = text.splitlines(keepends=True)
    offsets: list[int] = []
    running = 0
    for raw_line in lines:
        offsets.append(running)
        running += len(raw_line)

    index = 0
    prose_start = 0
    # YAML frontmatter is not note body; nothing Meta Bind renders lives there.
    if lines and lines[0].rstrip("\r\n") == "---":
        for closing, line in enumerate(lines[1:], start=1):
            if line.rstrip("\r\n") in _FRONTMATTER_END:
                index = closing + 1
                prose_start = offsets[index] if index < len(lines) else len(text)
                break

    while index < len(lines):
        match = _FENCE_RE.match(lines[index])
        if match is None:
            index += 1
            continue
        marker = match.group("marker")
        info = match.group("info")
        content_start = offsets[index] + len(lines[index])
        closing = index + 1
        while closing < len(lines):
            close_match = _FENCE_RE.match(lines[closing])
            if (
                close_match is not None
                and close_match.group("marker")[0] == marker[0]
                and len(close_match.group("marker")) >= len(marker)
                and not close_match.group("info")
            ):
                break
            closing += 1
        content_end = offsets[closing] if closing < len(lines) else len(text)

        prose.append(_Region(prose_start, offsets[index], None))
        if info in FENCE_KINDS:
            fenced.append(_Region(content_start, content_end, info))
        index = closing + 1
        prose_start = offsets[index] if index < len(lines) else len(text)

    prose.append(_Region(prose_start, len(text), None))
    return fenced, prose


def _iter_code_spans(text: str, start: int, end: int) -> Iterator[tuple[int, int]]:
    """Yield (start, end) of each backtick code span's content within [start, end)."""
    i = start
    while i < end:
        if text[i] != "`":
            i += 1
            continue
        run = 0
        while i + run < end and text[i + run] == "`":
            run += 1
        j = i + run
        closed = False
        while j < end:
            if text[j] != "`":
                j += 1
                continue
            close_run = 0
            while j + close_run < end and text[j + close_run] == "`":
                close_run += 1
            if close_run == run:
                yield i + run, j
                i = j + close_run
                closed = True
                break
            j += close_run
        if not closed:
            i += run


def parse_note(source: PathLike, text: str | None = None) -> list[Declaration]:
    """Parse every Meta Bind declaration in a note, in document order."""
    path = Path(source)
    if text is None:
        text = path.read_text(encoding="utf-8")

    fenced, prose = _split_regions(text)
    declarations: list[Declaration] = []

    for region in fenced:
        declaration = parse_declaration(
            text, path, "fence", region.start, region.end, region.fence_kind
        )
        if declaration is not None:
            declarations.append(declaration)

    for region in prose:
        for span_start, span_end in _iter_code_spans(text, region.start, region.end):
            declaration = parse_declaration(text, path, "inline", span_start, span_end)
            if declaration is not None:
                declarations.append(declaration)

    declarations.sort(key=lambda d: d.span.start)
    return declarations


# ---------------------------------------------------------------------------
# Vault access
# ---------------------------------------------------------------------------


class NotInVaultError(Exception):
    """Raised when the given path has no .obsidian/ ancestor."""


def locate_vault(path: PathLike) -> Path:
    """Return the resolved vault root containing path."""
    candidate = Path(path).expanduser()
    try:
        candidate = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise NotInVaultError(f"path does not exist: {path}") from exc
    if candidate.is_file():
        candidate = candidate.parent
    for directory in [candidate, *candidate.parents]:
        if (directory / ".obsidian").is_dir():
            return directory
    raise NotInVaultError(f"no .obsidian/ ancestor found above {path}")


def iter_notes(root: PathLike) -> Iterator[Path]:
    """Yield every `.md` file under root, skipping SKIP_DIRS."""
    base = Path(root)
    if base.is_file():
        yield base
        return
    for path in sorted(base.rglob("*.md")):
        if any(part in SKIP_DIRS for part in path.relative_to(base).parts):
            continue
        yield path


def read_frontmatter(source: PathLike) -> dict[str, object]:
    """Return a note's YAML frontmatter, or {} when absent or not a mapping."""
    text = Path(source).read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != "---":
        return {}
    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip() in _FRONTMATTER_END:
            try:
                loaded: Any = yaml.safe_load("\n".join(lines[1:index]))
            except yaml.YAMLError:
                return {}
            if not isinstance(loaded, dict):
                return {}
            return cast("dict[str, object]", loaded)
    return {}


# ---------------------------------------------------------------------------
# Field spec
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """The generated field/argument/action tables from references/field-spec.json."""

    raw: dict[str, Any] = field(default_factory=dict[str, Any])

    @property
    def input_field_types(self) -> dict[str, dict[str, Any]]:
        return self.raw.get("input_field_types", {})

    @property
    def input_field_arguments(self) -> dict[str, dict[str, Any]]:
        return self.raw.get("input_field_arguments", {})

    @property
    def view_field_types(self) -> dict[str, dict[str, Any]]:
        return self.raw.get("view_field_types", {})

    @property
    def view_field_arguments(self) -> dict[str, dict[str, Any]]:
        return self.raw.get("view_field_arguments", {})

    @property
    def button_action_types(self) -> dict[str, dict[str, Any]]:
        return self.raw.get("button_action_types", {})

    @property
    def button_config_fields(self) -> dict[str, Any]:
        return self.raw.get("button_config_fields", {})

    def arguments_for(self, kind: str) -> dict[str, dict[str, Any]]:
        return self.input_field_arguments if kind == "input" else self.view_field_arguments

    def types_for(self, kind: str) -> dict[str, dict[str, Any]]:
        return self.input_field_types if kind == "input" else self.view_field_types


class SpecError(Exception):
    """Raised when field-spec.json is missing or unusable."""


def load_spec(path: PathLike | None = None) -> FieldSpec:
    """Load references/field-spec.json. Raises SpecError if absent or malformed."""
    spec_path = Path(path) if path is not None else DEFAULT_SPEC_PATH
    try:
        raw: Any = json.loads(spec_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SpecError(
            f"field-spec.json not found at {spec_path} — run refresh_docs.py to generate it"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecError(f"field-spec.json at {spec_path} is unreadable: {exc}") from exc
    if not isinstance(raw, dict):
        raise SpecError(f"field-spec.json at {spec_path} is not a JSON object")
    return FieldSpec(cast("dict[str, Any]", raw))
