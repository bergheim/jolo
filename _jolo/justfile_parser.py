"""Minimal structural parsing of justfiles.

Currently only exposes two helpers used by scaffolding:

- :func:`has_import` — true if the source already imports ``justfile.common``.
- :func:`insert_import` — place the import directive after any leading
  shebang, header comments, and top-level directives (``set shell``,
  ``export FOO``, ``alias x := y``). This keeps ``set shell`` ordering
  correct so it applies to imported recipes too.

Not a full just parser; anything beyond these two helpers lives outside
this module.
"""

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
    for line in src.splitlines():
        if _IMPORT_RE.match(line):
            return True
    return False


def insert_import(src: str) -> str:
    """Insert ``import 'justfile.common'`` in the right place.

    "Right place" means after any leading shebang (``#!``), legal header
    comments, blank lines, and top-level directives like ``set shell``
    / ``export FOO`` / ``alias x := y``. This preserves the existing
    shebang execution and keeps ``set shell`` ordering (settings must
    come before the recipes they apply to, and our imported recipes
    depend on the user's shell setting).

    Idempotent: returns ``src`` unchanged if the import is already
    present anywhere at the top level.
    """
    if has_import(src):
        return src
    if not src:
        return "import 'justfile.common'\n"

    lines = src.splitlines(keepends=True)
    insert_at = 0

    # Allow a shebang on the very first line.
    if insert_at < len(lines) and lines[insert_at].startswith("#!"):
        insert_at += 1

    # Then consume any run of blank lines, top-level comments, or
    # directives (set/export/alias/mod/unexport). Stop at the first
    # recipe header.
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
    sep_before = (
        ""
        if prefix == "" or prefix.endswith("\n\n")
        else ("\n" if prefix.endswith("\n") else "\n\n")
    )
    sep_after = "\n" if suffix and not suffix.startswith("\n") else ""
    return f"{prefix}{sep_before}import 'justfile.common'\n{sep_after}{suffix}"
