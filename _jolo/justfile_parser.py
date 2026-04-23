"""Structural helpers for justfile import placement."""

from __future__ import annotations

import re

_IDENT = r"[A-Za-z_][A-Za-z0-9_-]*"
_RECIPE_HEADER_RE = re.compile(
    rf"^(?P<name>{_IDENT})(?:\s+[^:\n]*)?:\s*(?:#.*)?$"
)
_RESERVED_DIRECTIVES = frozenset(
    {"set", "export", "alias", "import", "unexport", "mod"}
)
_IMPORT_RE = re.compile(
    r"""^\s*import\s+['"]justfile\.common['"]\s*(?:#.*)?$"""
)


def _is_top_level(line: str) -> bool:
    if not line:
        return True
    return not line[0].isspace()


def _is_recipe_header(line: str) -> str | None:
    if not _is_top_level(line):
        return None
    stripped = line.rstrip("\n").rstrip()
    if not stripped:
        return None
    m = _RECIPE_HEADER_RE.match(stripped)
    if not m:
        return None
    name = m.group("name")
    if name in _RESERVED_DIRECTIVES:
        return None
    return name


def has_import(src: str) -> bool:
    """True if ``src`` already contains ``import 'justfile.common'``."""
    return any(_IMPORT_RE.match(line) for line in src.splitlines())


def insert_import(src: str) -> str:
    """Return ``src`` with ``import 'justfile.common'`` placed after any
    leading shebang, header comments, and top-level directives. Idempotent.

    Placement preserves ``set shell := ...`` ordering so imported recipes
    still run under the user's shell.
    """
    if has_import(src):
        return src
    if not src:
        return "import 'justfile.common'\n"

    lines = src.splitlines(keepends=True)
    insert_at = 0

    if insert_at < len(lines) and lines[insert_at].startswith("#!"):
        insert_at += 1

    while insert_at < len(lines):
        line = lines[insert_at]
        if line.strip() == "":
            insert_at += 1
            continue
        if _is_recipe_header(line):
            break
        if _is_top_level(line):
            stripped = line.rstrip("\n").lstrip()
            first = stripped.split(None, 1)[0] if stripped else ""
            if first in _RESERVED_DIRECTIVES or stripped.startswith("#"):
                insert_at += 1
                continue
        break

    prefix = "".join(lines[:insert_at])
    suffix = "".join(lines[insert_at:])
    if prefix == "" or prefix.endswith("\n\n"):
        sep_before = ""
    elif prefix.endswith("\n"):
        sep_before = "\n"
    else:
        sep_before = "\n\n"
    sep_after = "\n" if suffix and not suffix.startswith("\n") else ""
    return f"{prefix}{sep_before}import 'justfile.common'\n{sep_after}{suffix}"
