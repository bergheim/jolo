"""Regression: the suite must not write git config into the real repo."""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

from tests.cwd import isolate_cwd


def _repo_config() -> Path:
    repo = Path(__file__).resolve().parents[1]
    git_dir = Path(
        subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "--git-common-dir"],
            text=True,
        ).strip()
    )
    if not git_dir.is_absolute():
        git_dir = repo / git_dir
    return git_dir / "config"


class TestGitIsolation(unittest.TestCase):
    def test_addcleanup_restores_cwd_when_setup_raises(self):
        start = os.getcwd()
        leaked = []

        class Boom(unittest.TestCase):
            def setUp(self):
                isolate_cwd(self)
                leaked.append(os.getcwd())
                raise RuntimeError("boom")

            def test_never(self):
                self.fail("should not run")

        result = unittest.defaultTestLoader.loadTestsFromTestCase(Boom).run(
            unittest.TestResult()
        )
        self.assertTrue(result.errors)
        self.assertIn("boom", result.errors[0][1])
        self.assertTrue(leaked)
        self.assertNotEqual(leaked[0], start)
        self.assertEqual(os.getcwd(), start)

    def test_global_config_is_sandboxed(self):
        before = Path.home().joinpath(".gitconfig")
        before_bytes = before.read_bytes() if before.is_file() else None
        subprocess.run(
            [
                "git",
                "config",
                "--global",
                "user.name",
                "Suite Must Not Persist",
            ],
            check=True,
            capture_output=True,
        )
        after_bytes = before.read_bytes() if before.is_file() else None
        self.assertEqual(after_bytes, before_bytes)
        self.assertNotIn(
            "Suite Must Not Persist",
            _repo_config().read_text(),
        )
