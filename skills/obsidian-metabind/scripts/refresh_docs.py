#!/usr/bin/env python3
# /// script
# requires-python = ">=3.14"
# dependencies = [
#   "pyyaml>=6.0",
# ]
# ///
"""Regenerate references/field-spec.json and cache upstream Meta Bind prose.

The docs site has no sitemap and no llms.txt, but `docs/src/config/static.ts`
is a one-line re-export of the plugin's own `FieldConfigs.ts` — so the tables
the docs render from are generated here from that same source rather than
scraped. `ButtonConfig.ts` supplies the button action shapes the same way.

Two jobs, selected with --only:
  spec   parse FieldConfigs.ts + ButtonConfig.ts into references/field-spec.json
  cache  mirror the docs repo's src/content/docs/ and the JS Engine API into
         references/.cache/ (gitignored)

Version pinning: reads the plugin version from the vault's
.obsidian/plugins/obsidian-meta-bind-plugin/manifest.json and fetches that git
tag, so the spec describes the plugin actually installed. --ref overrides.

Output: JSON or text summary on stdout.
Exit codes: 0 ok, 1 invocation error, 2 fetch/parse failure (nothing written),
3 nothing matched --filter.

Network access required.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, cast

from parser import NotInVaultError, locate_vault

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_SYSTEM_ERROR = 2
EXIT_NOT_FOUND = 3

META_BIND_REPO = "mProjectsCode/obsidian-meta-bind-plugin"
META_BIND_DOCS_REPO = "mProjectsCode/obsidian-meta-bind-plugin-docs"
JS_ENGINE_REPO = "mProjectsCode/obsidian-js-engine-plugin"

META_BIND_PLUGIN_ID = "obsidian-meta-bind-plugin"
JS_ENGINE_PLUGIN_ID = "js-engine"

#: Used when there is no vault, or the vault has no manifest for the plugin.
FALLBACK_META_BIND_VERSION = "1.5.1"
FALLBACK_JS_ENGINE_VERSION = "0.3.6"

FIELD_CONFIGS_PATH = "packages/core/src/config/FieldConfigs.ts"
BUTTON_CONFIG_PATH = "packages/core/src/config/ButtonConfig.ts"
JS_ENGINE_API_PATH = "packages/js-engine-api/src/index.ts"
DOCS_CONTENT_PREFIX = "src/content/docs/"

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SPEC_PATH = SCRIPT_DIR.parent / "references" / "field-spec.json"
DEFAULT_CACHE_DIR = SCRIPT_DIR.parent / "references" / ".cache"

#: Below these counts the TS literal parser has certainly mis-read a
#: restructured upstream file. A partial spec that green-lights bad syntax is
#: worse than a stale one, so we refuse to write anything.
_BOOL_LITERALS = frozenset({"true", "false"})
_SPEC_JOBS = frozenset({"spec", "all"})
_CACHE_JOBS = frozenset({"cache", "all"})

SANITY_FLOOR = {
    "input_field_types": 15,
    "input_field_arguments": 10,
    "view_field_types": 3,
    "view_field_arguments": 2,
    "button_action_types": 10,
    "button_styles": 3,
}


class RefreshError(Exception):
    """Fetch or parse failure. Always leaves existing output untouched."""


# ---------------------------------------------------------------------------
# TypeScript literal parsing
# ---------------------------------------------------------------------------


def strip_comments(src: str) -> str:
    """Remove // and /* */ comments, leaving string literals intact."""
    out: list[str] = []
    i = 0
    while i < len(src):
        char = src[i]
        if char in "'\"`":
            j = i + 1
            while j < len(src):
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == char:
                    j += 1
                    break
                j += 1
            out.append(src[i:j])
            i = j
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = len(src) if j == -1 else j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i)
            i = len(src) if j == -1 else j + 2
            continue
        out.append(char)
        i += 1
    return "".join(out)


_ENUM_RE = re.compile(r"export enum (?P<name>\w+)\s*\{(?P<body>[^}]*)\}")
_ENUM_MEMBER_RE = re.compile(r"(?P<key>\w+)\s*=\s*'(?P<value>[^']*)'")


def parse_enums(src: str) -> dict[str, dict[str, str]]:
    """Return {EnumName: {MEMBER: 'value'}} for every string enum in src."""
    return {
        match.group("name"): {
            member.group("key"): member.group("value")
            for member in _ENUM_MEMBER_RE.finditer(match.group("body"))
        }
        for match in _ENUM_RE.finditer(src)
    }


_NUMBER_RE = re.compile(r"-?\d+(\.\d+)?")
_DOTTED_NAME_RE = re.compile(r"[A-Za-z_$][\w$]*(\.[A-Za-z_$][\w$]*)*")
_NAME_RE = re.compile(r"[A-Za-z_$][\w$]*")


class _LiteralParser:
    """Recursive-descent reader for the object literals in FieldConfigs.ts.

    Deliberately narrow: it understands objects, arrays, strings, numbers,
    booleans, computed keys and dotted enum references, which is the whole of
    what those files use. Anything else raises.
    """

    def __init__(self, src: str, enums: dict[str, dict[str, str]]) -> None:
        self.src = src
        self.enums = enums

    def _ws(self, i: int) -> int:
        while i < len(self.src) and self.src[i].isspace():
            i += 1
        return i

    def _resolve(self, expression: str) -> Any:
        if expression in _BOOL_LITERALS:
            return expression == "true"
        if expression == "null":
            return None
        if "." in expression:
            owner, _, member = expression.rpartition(".")
            if owner in self.enums and member in self.enums[owner]:
                return self.enums[owner][member]
        return expression

    def value(self, i: int) -> tuple[Any, int]:
        i = self._ws(i)
        if i >= len(self.src):
            raise RefreshError("unexpected end of TypeScript source")
        char = self.src[i]
        if char == "{":
            return self.obj(i)
        if char == "[":
            return self.array(i)
        if char in "'\"":
            return self.string(i)
        match = _NUMBER_RE.match(self.src, i)
        if match is not None:
            text = match.group(0)
            return (float(text) if "." in text else int(text)), match.end()
        match = _DOTTED_NAME_RE.match(self.src, i)
        if match is None:
            raise RefreshError(
                f"unparseable TypeScript value at offset {i}: {self.src[i : i + 40]!r}"
            )
        return self._resolve(match.group(0)), match.end()

    def string(self, i: int) -> tuple[str, int]:
        quote = self.src[i]
        out: list[str] = []
        i += 1
        while i < len(self.src):
            if self.src[i] == "\\":
                out.append(self.src[i + 1])
                i += 2
                continue
            if self.src[i] == quote:
                return "".join(out), i + 1
            out.append(self.src[i])
            i += 1
        raise RefreshError("unterminated string literal")

    def array(self, i: int) -> tuple[list[Any], int]:
        items: list[Any] = []
        i = self._ws(i + 1)
        while i < len(self.src) and self.src[i] != "]":
            item, i = self.value(i)
            items.append(item)
            i = self._ws(i)
            if i < len(self.src) and self.src[i] == ",":
                i = self._ws(i + 1)
        if i >= len(self.src):
            raise RefreshError("unterminated array literal")
        return items, i + 1

    def key(self, i: int) -> tuple[str, int]:
        i = self._ws(i)
        if self.src[i] == "[":
            end = self.src.index("]", i)
            resolved = self._resolve(self.src[i + 1 : end].strip())
            return str(resolved), end + 1
        if self.src[i] in "'\"":
            return self.string(i)
        match = _NAME_RE.match(self.src, i)
        if match is None:
            raise RefreshError(f"unparseable object key at offset {i}")
        return match.group(0), match.end()

    def obj(self, i: int) -> tuple[dict[str, Any], int]:
        out: dict[str, Any] = {}
        i = self._ws(i + 1)
        while i < len(self.src) and self.src[i] != "}":
            name, i = self.key(i)
            i = self._ws(i)
            if i >= len(self.src) or self.src[i] != ":":
                raise RefreshError(f'expected ":" after key "{name}"')
            item, i = self.value(i + 1)
            out[name] = item
            i = self._ws(i)
            if i < len(self.src) and self.src[i] == ",":
                i = self._ws(i + 1)
        if i >= len(self.src):
            raise RefreshError("unterminated object literal")
        return out, i + 1


def parse_const_object(src: str, name: str, enums: dict[str, dict[str, str]]) -> dict[str, Any]:
    """Parse `export const <name>... = { ... }` into a dict."""
    match = re.search(rf"export const {re.escape(name)}\b[^=]*=\s*", src)
    if match is None:
        raise RefreshError(f"export const {name} not found — upstream layout changed")
    start = match.end()
    if start >= len(src) or src[start] != "{":
        raise RefreshError(f"export const {name} is not an object literal")
    value, _ = _LiteralParser(src, enums).obj(start)
    return value


_INTERFACE_RE = re.compile(r"export interface (?P<name>\w+)\s*\{(?P<body>[^{}]*)\}")
_INTERFACE_FIELD_RE = re.compile(
    r"^\s*(?P<name>\w+)(?P<optional>\?)?:\s*(?P<type>[^;]+);", re.MULTILINE
)


def parse_interfaces(src: str) -> dict[str, dict[str, dict[str, Any]]]:
    """Return {InterfaceName: {field: {"optional": bool, "type": str}}}."""
    return {
        match.group("name"): {
            found.group("name"): {
                "optional": found.group("optional") is not None,
                "type": found.group("type").strip(),
            }
            for found in _INTERFACE_FIELD_RE.finditer(match.group("body"))
        }
        for match in _INTERFACE_RE.finditer(src)
    }


# ---------------------------------------------------------------------------
# Spec assembly
# ---------------------------------------------------------------------------


def _as_dict(value: Any) -> dict[str, Any]:
    """Narrow a parsed literal to a dict without losing its element types."""
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return cast("list[Any]", value) if isinstance(value, list) else []


def _argument_table(configs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    table: dict[str, dict[str, Any]] = {}
    for name, raw_config in sorted(configs.items()):
        if name == "invalid" or not isinstance(raw_config, dict):
            continue
        config = _as_dict(raw_config)
        signatures = [
            [
                {
                    "name": str(_as_dict(value).get("name", "")),
                    "allowed": [str(a) for a in _as_list(_as_dict(value).get("allowed"))],
                }
                for value in _as_list(signature)
                if isinstance(value, dict)
            ]
            for signature in _as_list(config.get("values"))
            if isinstance(signature, list)
        ]
        table[name] = {
            "allowed_field_types": sorted(
                str(t) for t in _as_list(config.get("allowedFieldTypes")) if str(t) != "invalid"
            ),
            "allow_multiple": bool(config.get("allowMultiple", False)),
            "arities": sorted({len(signature) for signature in signatures}),
            "signatures": signatures,
        }
    return table


def build_spec(
    field_configs_ts: str, button_config_ts: str, provenance: dict[str, str]
) -> dict[str, Any]:
    """Turn the two upstream TypeScript sources into the field-spec.json payload."""
    fields_src = strip_comments(field_configs_ts)
    buttons_src = strip_comments(button_config_ts)
    field_enums = parse_enums(fields_src)
    button_enums = parse_enums(buttons_src)

    for enum_name, src_name in (
        ("InputFieldType", "FieldConfigs.ts"),
        ("ViewFieldType", "FieldConfigs.ts"),
        ("InputFieldArgumentType", "FieldConfigs.ts"),
        ("ViewFieldArgumentType", "FieldConfigs.ts"),
    ):
        if enum_name not in field_enums:
            raise RefreshError(
                f"enum {enum_name} not found in {src_name} — upstream layout changed"
            )
    for enum_name in ("ButtonActionType", "ButtonStyleType"):
        if enum_name not in button_enums:
            raise RefreshError(
                f"enum {enum_name} not found in ButtonConfig.ts — upstream layout changed"
            )

    input_configs = parse_const_object(fields_src, "InputFieldConfigs", field_enums)
    input_types: dict[str, dict[str, Any]] = {
        name: {
            "allow_in_block": bool(_as_dict(config).get("allowInBlock", False)),
            "allow_inline": bool(_as_dict(config).get("allowInline", False)),
        }
        for name, config in sorted(input_configs.items())
        if name != "invalid" and isinstance(config, dict)
    }

    view_types: dict[str, dict[str, Any]] = {
        value: {} for value in sorted(field_enums["ViewFieldType"].values()) if value != "invalid"
    }

    interfaces = parse_interfaces(buttons_src)

    # Each `*ButtonAction` interface names its action through `type: ButtonActionType.X`.
    # Index them by action type in one pass rather than rescanning per action.
    action_members = button_enums["ButtonActionType"]
    interface_by_action: dict[str, dict[str, dict[str, Any]]] = {}
    for name, fields in interfaces.items():
        member = str(fields.get("type", {}).get("type", "")).rpartition(".")[2]
        if name.endswith("ButtonAction") and member in action_members:
            interface_by_action.setdefault(action_members[member], fields)

    action_types: dict[str, dict[str, Any]] = {}
    for action_type in sorted(action_members.values()):
        interface = interface_by_action.get(action_type)
        if interface is None:
            raise RefreshError(
                f"no interface found for button action {action_type!r} — upstream layout changed"
            )
        action_types[action_type] = {
            "required": sorted(
                name for name, meta in interface.items() if name != "type" and not meta["optional"]
            ),
            "optional": sorted(
                name for name, meta in interface.items() if name != "type" and meta["optional"]
            ),
        }

    button_config = interfaces.get("ButtonConfig", {})
    if not button_config:
        raise RefreshError("interface ButtonConfig not found — upstream layout changed")

    embed_depth = re.search(r"export const EMBED_MAX_DEPTH\s*=\s*(\d+)", fields_src)
    if embed_depth is None:
        raise RefreshError("EMBED_MAX_DEPTH not found in FieldConfigs.ts — upstream layout changed")

    spec: dict[str, Any] = {
        "provenance": provenance,
        "embed_max_depth": int(embed_depth.group(1)),
        "input_field_types": input_types,
        "input_field_arguments": _argument_table(
            parse_const_object(fields_src, "InputFieldArgumentConfigs", field_enums)
        ),
        "view_field_types": view_types,
        "view_field_arguments": _argument_table(
            parse_const_object(fields_src, "ViewFieldArgumentConfigs", field_enums)
        ),
        "button_styles": sorted(button_enums["ButtonStyleType"].values()),
        "button_action_types": action_types,
        "button_config_fields": {
            "required": sorted(
                name for name, meta in button_config.items() if not meta["optional"]
            ),
            "optional": sorted(name for name, meta in button_config.items() if meta["optional"]),
        },
    }

    for key, floor in SANITY_FLOOR.items():
        found = len(spec[key])
        if found < floor:
            raise RefreshError(
                f"sanity floor: parsed only {found} {key} (expected at least {floor}) — "
                "the upstream TypeScript layout has probably changed; field-spec.json "
                "was left untouched"
            )
    return spec


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def http_get(url: str, timeout: int = 30) -> bytes:
    # Deferred: every caller in the test suite injects its own fetcher, so a
    # whole test run never pays for urllib.request's import.
    import urllib.error
    import urllib.request

    request = urllib.request.Request(  # noqa: S310
        url,
        headers={"User-Agent": "obsidian-metabind-skill", "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            data: bytes = response.read()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise RefreshError(f"fetch failed for {url}: {exc}") from exc
    return data


def raw_url(repo: str, ref: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{ref}/{path}"


def resolve_commit(repo: str, ref: str, fetcher: Any) -> str:
    """Return the commit SHA a ref points at, or "" if the API is unavailable."""
    try:
        payload: Any = json.loads(fetcher(f"https://api.github.com/repos/{repo}/commits/{ref}"))
    except RefreshError, json.JSONDecodeError:
        return ""
    return str(_as_dict(payload).get("sha", ""))


def list_tree(repo: str, ref: str, fetcher: Any) -> list[str]:
    payload = _as_dict(
        json.loads(fetcher(f"https://api.github.com/repos/{repo}/git/trees/{ref}?recursive=1"))
    )
    if not isinstance(payload.get("tree"), list):
        raise RefreshError(f"unexpected git tree response for {repo}@{ref}")
    paths: list[str] = []
    for raw_entry in _as_list(payload["tree"]):
        entry = _as_dict(raw_entry)
        if entry.get("type") == "blob" and "path" in entry:
            paths.append(str(entry["path"]))
    return paths


def plugin_version(vault: Path | None, plugin_id: str, fallback: str) -> tuple[str, str]:
    """Return (version, source) from the vault's plugin manifest, else the fallback."""
    if vault is None:
        return fallback, "fallback"
    manifest = vault / ".obsidian" / "plugins" / plugin_id / "manifest.json"
    try:
        payload: Any = json.loads(manifest.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return fallback, "fallback"
    version = _as_dict(payload).get("version")
    if isinstance(version, str):
        return version, "vault-manifest"
    return fallback, "fallback"


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def refresh_spec(
    *, ref: str, meta_bind_version: str, js_engine_version: str, spec_path: Path, fetcher: Any
) -> dict[str, Any]:
    field_configs = fetcher(raw_url(META_BIND_REPO, ref, FIELD_CONFIGS_PATH)).decode("utf-8")
    button_config = fetcher(raw_url(META_BIND_REPO, ref, BUTTON_CONFIG_PATH)).decode("utf-8")
    provenance = {
        # No wall-clock timestamp: the spec must regenerate byte-identically
        # from a pinned ref. The commit SHA pins it more precisely anyway.
        "generated_by": "scripts/refresh_docs.py",
        "source_repo": f"https://github.com/{META_BIND_REPO}",
        "source_ref": ref,
        "source_commit": resolve_commit(META_BIND_REPO, ref, fetcher),
        "source_files": f"{FIELD_CONFIGS_PATH}, {BUTTON_CONFIG_PATH}",
        "meta_bind_version": meta_bind_version,
        "js_engine_version": js_engine_version,
        "license": (
            "Derived from GPL-3.0 sources (c) mProjectsCode. This file contains "
            "enum names, arities and allow-lists extracted from them."
        ),
    }
    spec = build_spec(field_configs, button_config, provenance)
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "path": str(spec_path),
        "input_field_types": len(spec["input_field_types"]),
        "input_field_arguments": len(spec["input_field_arguments"]),
        "view_field_types": len(spec["view_field_types"]),
        "button_action_types": len(spec["button_action_types"]),
        "source_commit": provenance["source_commit"],
    }


def refresh_cache(
    *,
    docs_ref: str,
    js_engine_ref: str,
    cache_dir: Path,
    name_filter: str | None,
    fetcher: Any,
) -> dict[str, Any]:
    wanted: list[tuple[str, str, Path]] = [
        (JS_ENGINE_REPO, "README.md", cache_dir / "js-engine" / "README.md"),
        (JS_ENGINE_REPO, JS_ENGINE_API_PATH, cache_dir / "js-engine" / "index.ts"),
    ]
    wanted = [
        (repo, path, out)
        for repo, path, out in wanted
        if name_filter is None or name_filter in path
    ]
    refs = {JS_ENGINE_REPO: js_engine_ref, META_BIND_DOCS_REPO: docs_ref}

    for path in list_tree(META_BIND_DOCS_REPO, docs_ref, fetcher):
        if not path.startswith(DOCS_CONTENT_PREFIX) or not path.endswith((".md", ".mdx")):
            continue
        if name_filter is not None and name_filter not in path:
            continue
        relative = path[len(DOCS_CONTENT_PREFIX) :]
        wanted.append((META_BIND_DOCS_REPO, path, cache_dir / "docs" / relative))

    written: list[str] = []
    unchanged: list[str] = []
    errors: list[dict[str, str]] = []
    for repo, path, out in wanted:
        try:
            body = fetcher(raw_url(repo, refs[repo], path)).decode("utf-8")
        except RefreshError as exc:
            errors.append({"path": path, "error": str(exc)})
            continue
        if out.exists() and out.read_text(encoding="utf-8") == body:
            unchanged.append(path)
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
        written.append(path)

    return {
        "cache_dir": str(cache_dir),
        "written": len(written),
        "unchanged": len(unchanged),
        "errors": errors,
        "matched": len(wanted),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _emit_error(message: str, code: str, hint: str | None = None) -> None:
    payload: dict[str, str] = {"error": message, "code": code}
    if hint is not None:
        payload["hint"] = hint
    print(json.dumps(payload), file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n", 1)[0],
        epilog=(
            "examples:\n"
            "  refresh_docs.py --only spec              # regenerate field-spec.json only\n"
            "  refresh_docs.py --vault ~/vault          # pin to the plugin that vault installs\n"
            "  refresh_docs.py --ref 1.5.0 --only spec  # regenerate against an older tag\n"
            "  refresh_docs.py --only cache --filter button --json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--vault", help="vault root (default: walk up from cwd)")
    parser.add_argument("--ref", help="git ref to fetch (default: the installed plugin version)")
    parser.add_argument(
        "--only",
        choices=("spec", "cache", "all"),
        default="all",
        help="which job to run (default: all)",
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--spec-path", type=Path, default=DEFAULT_SPEC_PATH)
    parser.add_argument("--filter", dest="name_filter", help="only cache paths containing this")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument("--json", action="store_true", help="alias for --format json")
    parser.add_argument("--quiet", action="store_true", help="suppress informational stderr")
    return parser


def main(argv: list[str] | None = None, fetcher: Any = http_get) -> int:
    args = _build_parser().parse_args(argv)
    as_json = args.json or args.format == "json"

    vault: Path | None = None
    try:
        vault = locate_vault(args.vault or Path.cwd())
    except NotInVaultError as exc:
        # No vault around cwd is fine — the pinned fallback versions cover it.
        if args.vault:
            _emit_error(str(exc), "NOT_IN_VAULT", hint="pass --vault pointing at the vault root")
            return EXIT_USER_ERROR

    meta_bind_version, version_source = plugin_version(
        vault, META_BIND_PLUGIN_ID, FALLBACK_META_BIND_VERSION
    )
    js_engine_version, _ = plugin_version(vault, JS_ENGINE_PLUGIN_ID, FALLBACK_JS_ENGINE_VERSION)
    ref = args.ref or meta_bind_version

    if not args.quiet:
        print(
            f"refresh_docs: meta-bind {meta_bind_version} ({version_source}), "
            f"ref {ref}, js-engine {js_engine_version}",
            file=sys.stderr,
        )

    summary: dict[str, Any] = {"ref": ref, "meta_bind_version": meta_bind_version}
    try:
        if args.only in _SPEC_JOBS:
            summary["spec"] = refresh_spec(
                ref=ref,
                meta_bind_version=meta_bind_version,
                js_engine_version=js_engine_version,
                spec_path=args.spec_path,
                fetcher=fetcher,
            )
        if args.only in _CACHE_JOBS:
            summary["cache"] = refresh_cache(
                docs_ref="master",
                js_engine_ref=js_engine_version,
                cache_dir=args.cache_dir,
                name_filter=args.name_filter,
                fetcher=fetcher,
            )
    except RefreshError as exc:
        _emit_error(
            str(exc),
            "REFRESH_FAILED",
            hint="re-run with --ref pointing at a known-good tag; nothing was written",
        )
        return EXIT_SYSTEM_ERROR
    except Exception as exc:
        _emit_error(str(exc), "UNEXPECTED_ERROR", hint="re-run with --only spec to narrow it down")
        return EXIT_SYSTEM_ERROR

    if as_json:
        print(json.dumps(summary, indent=2))
    else:
        if "spec" in summary:
            spec = summary["spec"]
            print(
                f"spec: {spec['path']} "
                f"({spec['input_field_types']} input types, "
                f"{spec['input_field_arguments']} input arguments, "
                f"{spec['button_action_types']} button actions)"
            )
        if "cache" in summary:
            cache = summary["cache"]
            print(
                f"cache: {cache['cache_dir']} "
                f"(written={cache['written']} unchanged={cache['unchanged']} "
                f"errors={len(cache['errors'])})"
            )

    if "cache" in summary and summary["cache"]["matched"] == 0:
        if not args.quiet:
            print("refresh_docs: no cache paths matched --filter", file=sys.stderr)
        return EXIT_NOT_FOUND
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
