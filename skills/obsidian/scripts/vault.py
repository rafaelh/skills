#!/usr/bin/env python3
"""Vault primitives: locate the root and enumerate its contents.

Every other script in this skill builds on this module. It owns the
convention for "what counts as in-vault content" — the SKIP_DIRS set,
the supported file extensions, and the relpath shape used in wikilinks.

Library API:
    locate_vault(path) -> Path                  # walk up to find .obsidian/
    iter_notes(vault) -> Iterable[Path]         # *.md, skipping .obsidian/.trash/.git
    iter_canvas(vault) -> Iterable[Path]
    iter_bases(vault) -> Iterable[Path]
    relpath_no_ext(vault, file) -> str          # forward-slash path, no extension
    SKIP_DIRS                                   # frozen set of dir names to ignore

CLI:
    vault.py [PATH]    # prints absolute vault root, exits 1 if not in a vault

The CLI behavior is the original `vault_locate` interface, preserved so
existing shell invocations continue to work.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

PathLike = str | Path

SKIP_DIRS: frozenset[str] = frozenset({".obsidian", ".trash", ".git"})


class NotInVaultError(Exception):
    """Raised when the given path has no .obsidian/ ancestor."""


def locate_vault(path: PathLike) -> Path:
    """Return the resolved vault root containing path.

    Walks up from path (or its parent if it's a file) until it finds a
    directory containing a .obsidian subdirectory. Raises NotInVaultError if
    no such ancestor exists, or if path itself does not exist.
    """
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


def _iter_with_suffix(vault: Path, suffix: str) -> Iterable[Path]:
    vault = Path(vault)
    for path in vault.rglob(f"*{suffix}"):
        if any(part in SKIP_DIRS for part in path.relative_to(vault).parts):
            continue
        yield path


def iter_notes(vault: PathLike) -> Iterable[Path]:
    """Yield every `.md` file in the vault, skipping SKIP_DIRS."""
    return _iter_with_suffix(Path(vault), ".md")


def iter_canvas(vault: PathLike) -> Iterable[Path]:
    """Yield every `.canvas` file in the vault, skipping SKIP_DIRS."""
    return _iter_with_suffix(Path(vault), ".canvas")


def iter_bases(vault: PathLike) -> Iterable[Path]:
    """Yield every `.base` file in the vault, skipping SKIP_DIRS."""
    return _iter_with_suffix(Path(vault), ".base")


def relpath_no_ext(vault: PathLike, file: PathLike) -> str:
    """Return file's vault-relative path, no extension, forward-slash separated.

    This is the form Obsidian uses for path-style wikilinks like
    `[[notes/Alpha]]`.
    """
    rel = Path(file).resolve().relative_to(Path(vault).resolve())
    return str(rel.with_suffix("")).replace("\\", "/")


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Print the root of an Obsidian vault.")
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="path to search from (default: current directory)",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="emit JSON ({input, vault_root}) on stdout",
    )
    args = parser.parse_args(argv)

    try:
        root = locate_vault(args.path)
    except NotInVaultError as exc:
        if args.as_json:
            print(json.dumps({"input": args.path, "error": str(exc)}))
        else:
            print(f"vault: {exc}", file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps({"input": args.path, "vault_root": str(root)}))
    else:
        print(root)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
