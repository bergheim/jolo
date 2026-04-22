"""SQLite run ledger.

Source of truth for "what happened on this commit?". VM/profile-tree
become views over this.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    sha TEXT NOT NULL,
    branch TEXT NOT NULL,
    dirty INTEGER NOT NULL,
    testbed TEXT NOT NULL,
    sut_mode TEXT NOT NULL,
    sut_image_digest TEXT,
    k6_version TEXT NOT NULL,
    rig_schema_version INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    validity_status TEXT NOT NULL,
    failure_reason TEXT,
    grafana_url TEXT,
    bencher_report_url TEXT,
    profile_urls TEXT,
    summary_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_project_sha ON runs(project, sha);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at);
"""


class Ledger:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(DDL)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def insert_started(self, row: dict[str, Any]) -> None:
        cols = ",".join(row.keys())
        placeholders = ",".join("?" * len(row))
        with self._conn() as c:
            c.execute(
                f"INSERT INTO runs ({cols}) VALUES ({placeholders})",
                list(row.values()),
            )

    def update_finished(self, run_id: str, **fields: Any) -> None:
        if "profile_urls" in fields and not isinstance(fields["profile_urls"], str):
            fields["profile_urls"] = json.dumps(fields["profile_urls"])
        if "summary_json" in fields and not isinstance(fields["summary_json"], str):
            fields["summary_json"] = json.dumps(fields["summary_json"])
        sets = ",".join(f"{k}=?" for k in fields)
        with self._conn() as c:
            c.execute(
                f"UPDATE runs SET {sets} WHERE run_id=?",
                [*fields.values(), run_id],
            )

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            return dict(row) if row else None

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def projects(self) -> list[dict[str, Any]]:
        """One row per project with run counts and latest run."""
        with self._conn() as c:
            rows = c.execute(
                """
                SELECT
                    project,
                    COUNT(*) AS total_runs,
                    SUM(CASE WHEN validity_status='pass' THEN 1 ELSE 0 END) AS pass_runs,
                    SUM(CASE WHEN validity_status='fail' THEN 1 ELSE 0 END) AS fail_runs,
                    MAX(started_at) AS last_run_at,
                    (SELECT run_id FROM runs r2 WHERE r2.project=r1.project
                     ORDER BY started_at DESC LIMIT 1) AS last_run_id
                FROM runs r1
                GROUP BY project
                ORDER BY last_run_at DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]
