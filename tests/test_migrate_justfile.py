#!/usr/bin/env python3
"""End-to-end tests for `jolo migrate-justfile`.

Uses argparse.Namespace directly rather than CLI parse to keep the
test focused on the migration logic.
"""

import argparse
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _jolo.commands import run_migrate_justfile_mode


def _make_python_project(tmp: Path, justfile_content: str) -> Path:
    """Create a fake python project under tmp with a given justfile."""
    project = tmp / "demo"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    (project / "justfile").write_text(justfile_content)
    # detect_flavors checks for git; seed a minimal marker.
    return project


class TestMigrateJustfile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self.orig_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.orig_cwd)
        self.tmp.cleanup()

    def _run(self, project: Path):
        args = argparse.Namespace(verbose=False)
        with mock.patch("_jolo.commands.pick_project", return_value=project):
            run_migrate_justfile_mode(args)

    def test_monolith_with_perf_is_split(self):
        """Pre-split project with tool-owned recipes in its justfile."""
        src = (
            'set shell := ["bash"]\n\n'
            "# User's own recipe\n"
            "dev:\n    uv run uvicorn demo.app:app --port $PORT\n\n"
            "# Open in browser\n"
            "browse:\n    chromium http://localhost:$PORT\n\n"
            "perf:\n    echo stale perf\n"
        )
        project = _make_python_project(self.tmpdir, src)

        self._run(project)

        justfile = (project / "justfile").read_text()
        common = (project / "justfile.common").read_text()
        backup = project / "justfile.migration-backup"

        # Template recipes no longer in user justfile.
        self.assertNotIn("\nperf:", "\n" + justfile)
        self.assertNotIn("\nbrowse:", "\n" + justfile)
        # User recipe and settings preserved.
        self.assertIn("dev:", justfile)
        self.assertIn("set shell", justfile)
        # Import present and placed after `set shell` so the setting
        # still applies to imported recipes.
        self.assertIn("import 'justfile.common'", justfile)
        self.assertLess(
            justfile.index("set shell"),
            justfile.index("import 'justfile.common'"),
        )
        self.assertLess(
            justfile.index("import 'justfile.common'"),
            justfile.index("dev:"),
        )
        # Fresh common file has current template content.
        self.assertIn("perf:", common)
        self.assertIn("browse:", common)
        self.assertIn("PERF_TESTBED:=dev-container-demo", common)
        # Backup saved old tool-owned recipes.
        self.assertTrue(backup.exists())
        backup_content = backup.read_text()
        self.assertIn("echo stale perf", backup_content)
        self.assertIn("Automatically extracted", backup_content)

    def test_pre_perf_project_just_gets_common_plus_import(self):
        """Project that predates any template recipes — no backup needed."""
        src = (
            'set shell := ["bash"]\n\n'
            "dev:\n    uv run uvicorn demo.app:app --port $PORT\n\n"
            "test:\n    uv run pytest\n"
        )
        project = _make_python_project(self.tmpdir, src)

        self._run(project)

        justfile = (project / "justfile").read_text()
        common = (project / "justfile.common").read_text()

        # Import placed after leading `set shell` directive.
        self.assertIn("import 'justfile.common'", justfile)
        self.assertLess(
            justfile.index("set shell"),
            justfile.index("import 'justfile.common'"),
        )
        self.assertIn("dev:", justfile)
        self.assertIn("test:", justfile)
        self.assertIn("perf:", common)
        # No backup file because nothing was extracted.
        self.assertFalse((project / "justfile.migration-backup").exists())

    def test_idempotent_when_up_to_date(self):
        """Running migrate on a project already split with current template
        is a no-op."""
        from _jolo.templates import get_justfile_common_content

        src = "import 'justfile.common'\n\ndev:\n    echo dev\n"
        project = _make_python_project(self.tmpdir, src)
        (project / "justfile.common").write_text(
            get_justfile_common_content("demo")
        )

        before_justfile = (project / "justfile").read_text()
        before_common = (project / "justfile.common").read_text()

        self._run(project)

        self.assertEqual((project / "justfile").read_text(), before_justfile)
        self.assertEqual(
            (project / "justfile.common").read_text(), before_common
        )

    def test_refreshes_stale_common_as_repair_path(self):
        """Migrate doubles as a repair: stale justfile.common gets regenerated."""
        src = "import 'justfile.common'\n\ndev:\n    echo dev\n"
        project = _make_python_project(self.tmpdir, src)
        # Deliberately stale common file.
        (project / "justfile.common").write_text("perf:\n    echo stale\n")

        self._run(project)

        common = (project / "justfile.common").read_text()
        self.assertNotIn("echo stale", common)
        # Fresh template content landed.
        self.assertIn("PERF_TESTBED:=dev-container-demo", common)

    def test_absent_justfile_errors(self):
        project = self.tmpdir / "no-justfile"
        project.mkdir()
        (project / "pyproject.toml").write_text("[project]\nname='x'\n")

        with self.assertRaises(SystemExit):
            self._run(project)


class TestCreateFlowProducesSplit(unittest.TestCase):
    """Fresh project scaffolded via get_justfile_* emits both files."""

    def test_user_justfile_imports_common(self):
        from _jolo.templates import (
            get_justfile_common_content,
            get_justfile_content,
        )

        user = get_justfile_content("python", "demo")
        common = get_justfile_common_content("demo")

        # Import present and placed after `set shell` for template's flavor files.
        self.assertIn("import 'justfile.common'", user)
        self.assertLess(
            user.index("set shell"), user.index("import 'justfile.common'")
        )
        self.assertIn("dev:", user)
        self.assertNotIn("\nperf:", "\n" + user)  # moved to common
        self.assertIn("perf:", common)
        self.assertIn("browse:", common)


if __name__ == "__main__":
    unittest.main()
