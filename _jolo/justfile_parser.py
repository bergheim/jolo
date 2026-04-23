"""Structural line-scanner for justfiles.

Scope is narrow: identify and excise named top-level recipes during the
split-justfile migration. Not a full just parser — we don't evaluate
expressions, imports, or dependencies; we just need to locate recipe
boundaries so ``jolo migrate-justfile`` can extract tool-owned recipes
out of a monolithic user justfile.

Rules implemented:

- A top-level line is one that starts in column 0 (no leading whitespace).
- A recipe header matches ``^<name>(\\s[^:]*)?:\\s*$`` at the top level,
  where ``<name>`` is a justfile identifier (letters, digits, ``-``, ``_``).
  Headers with dependencies after ``:`` also match.
- ``set``, ``export``, ``alias``, ``import``, ``unexport`` are reserved
  top-level directives and are **not** recipes.
- The body of a recipe is every subsequent line that is indented or
  blank; it ends at the first top-level line (recipe or directive).
- The "owned" lines of a recipe also include any immediately preceding
  top-level comment lines and attribute lines (``[private]`` etc.) that
  are directly above the header with no blank line separator.
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
_IMPORT_RE = re.compile(r"""^\s*import\s+['"]justfile\.common['"]\s*$""")


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


def _find_leading_adopt_start(lines: list[str], header_idx: int) -> int:
    """Walk backward from ``header_idx`` adopting attribute/comment lines.

    Stops at a blank line, another recipe body, or top-of-file.
    """
    start = header_idx
    i = header_idx - 1
    while i >= 0:
        line = lines[i].rstrip("\n")
        if line == "":
            break
        if not _is_top_level(lines[i]):
            break
        s = line.lstrip()
        if s.startswith("#") or s.startswith("["):
            start = i
            i -= 1
            continue
        break
    return start


def _recipe_end(lines: list[str], header_idx: int) -> int:
    """Return the exclusive end index of the recipe that starts at header_idx."""
    i = header_idx + 1
    while i < len(lines):
        line = lines[i]
        # Blank lines are part of the body (justfile recipes can contain
        # empty lines between commands via line continuation / shebang).
        if line.strip() == "":
            i += 1
            continue
        if _is_top_level(line) and _is_recipe_header(line) is not None:
            break
        if _is_top_level(line):
            # Another directive (`set`, `import`, ...) ends the body too.
            stripped = line.rstrip("\n").lstrip()
            first = stripped.split(None, 1)[0] if stripped else ""
            if first in _RESERVED_DIRECTIVES:
                break
            # Top-level non-blank, non-directive, non-recipe-header — this
            # is unusual (user garbage) but still ends the body.
            break
        i += 1
    # Trim trailing blank lines out of this recipe's owned range.
    while i > header_idx + 1 and lines[i - 1].strip() == "":
        i -= 1
    return i


def extract_recipes(src: str, names: set[str]) -> dict[str, str]:
    """Return ``{name: source_chunk}`` for each requested top-level recipe.

    Unknown names are silently absent from the result.
    """
    if not src or not names:
        return {}
    lines = src.splitlines(keepends=True)
    out: dict[str, str] = {}
    i = 0
    while i < len(lines):
        name = _is_recipe_header(lines[i])
        if name is not None and name in names:
            start = _find_leading_adopt_start(lines, i)
            end = _recipe_end(lines, i)
            out[name] = "".join(lines[start:end])
            i = end
            continue
        i += 1
    return out


def remove_recipes(src: str, names: set[str]) -> str:
    """Return ``src`` with the named top-level recipes (and their adopted
    leading comments/attributes) removed.

    Trailing blank lines around removed ranges are collapsed to keep the
    result readable. Non-targeted content is preserved verbatim.
    """
    if not src or not names:
        return src
    lines = src.splitlines(keepends=True)
    keep = [True] * len(lines)
    i = 0
    while i < len(lines):
        name = _is_recipe_header(lines[i])
        if name is not None and name in names:
            start = _find_leading_adopt_start(lines, i)
            end = _recipe_end(lines, i)
            for j in range(start, end):
                keep[j] = False
            i = end
            continue
        i += 1
    # Collapse runs of blank lines produced by deletion.
    out_lines: list[str] = []
    prev_blank = False
    for idx, line in enumerate(lines):
        if not keep[idx]:
            continue
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        out_lines.append(line)
        prev_blank = is_blank
    return "".join(out_lines)


def has_import(src: str) -> bool:
    """True if ``src`` already contains ``import 'justfile.common'``."""
    for line in src.splitlines():
        if _IMPORT_RE.match(line):
            return True
    return False
