"""Metadata contract for docs/TODO.org.

Every entry carrying a TODO keyword must have :ID: and :CREATED: so
agenda tooling and cross-session correlation work. Best-effort fields
(:LAST_AGENT:, LOGBOOK session lines) are never required. Fix violations
with `org-backfill docs/TODO.org` for legacy entries; new entries get
both stamps from `bergheim/agent-org-task-create`.
"""

import re
from pathlib import Path

TODO_ORG = Path(__file__).parent.parent / "docs" / "TODO.org"

KEYWORDS = {
    "TODO",
    "PROJ",
    "INPROGRESS",
    "NEXT",
    "WAITING",
    "BLOCKED",
    "SOMEDAY",
    "DONE",
    "CANCELLED",
    "OBSOLETE",
    "BUG",
    "FIXED",
    "IGNORED",
}
HEADING_RE = re.compile(r"^(\*+)\s+([A-Z]+)(\s+|$)")


def todo_entries() -> list[tuple[str, str]]:
    lines = TODO_ORG.read_text().splitlines()
    entries = []
    current = None
    for line in lines:
        m = HEADING_RE.match(line)
        if m:
            if current:
                entries.append(current)
            current = (line, []) if m.group(2) in KEYWORDS else None
        elif current:
            current[1].append(line)
    if current:
        entries.append(current)
    return [(heading, "\n".join(body)) for heading, body in entries]


def test_every_todo_entry_has_id_and_created():
    missing = []
    for heading, body in todo_entries():
        if not re.search(r"^\s*:ID:\s+\S", body, re.M):
            missing.append(f"{heading!r}: no :ID:")
        if not re.search(r"^\s*:CREATED:\s+\[", body, re.M):
            missing.append(f"{heading!r}: no :CREATED:")
    assert not missing, "run org-backfill docs/TODO.org:\n" + "\n".join(
        missing
    )
