#!/usr/bin/env python3
"""Tests for jolo publish (public-notes mode flip)."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import jolo
except ImportError:
    jolo = None

from _jolo import publish


def _run(cmd, cwd=None, check=True):
    return subprocess.run(
        cmd, cwd=cwd, check=check, capture_output=True, text=True
    )


def _make_outer_repo(root: Path) -> None:
    _run(["git", "init", "-q", "-b", "main"], cwd=root)
    _run(["git", "config", "user.email", "t@example.com"], cwd=root)
    _run(["git", "config", "user.name", "Test"], cwd=root)
    _run(["git", "config", "commit.gpgsign", "false"], cwd=root)
    (root / "README.md").write_text("# test repo\n")
    _run(["git", "add", "."], cwd=root)
    _run(["git", "commit", "-q", "-m", "init"], cwd=root)


class TestPublishArgParsing(unittest.TestCase):
    def test_publish_command(self):
        args = jolo.parse_args(["publish"])
        self.assertEqual(args.command, "publish")
        self.assertFalse(args.scrub)
        self.assertFalse(args.dry_run)
        self.assertFalse(args.yes)

    def test_publish_flags(self):
        args = jolo.parse_args(["publish", "--scrub", "--dry-run", "--yes"])
        self.assertTrue(args.scrub)
        self.assertTrue(args.dry_run)
        self.assertTrue(args.yes)


class TestHelpers(unittest.TestCase):
    def test_outer_repo_dirty_on_clean_repo(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_outer_repo(root)
            self.assertFalse(publish.outer_repo_dirty(root))

    def test_outer_repo_dirty_on_dirty_repo(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_outer_repo(root)
            (root / "new.txt").write_text("x")
            self.assertTrue(publish.outer_repo_dirty(root))

    def test_update_outer_gitignore_drops_scrub_lines(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".gitignore").write_text(
                "# header\n"
                ".env\n"
                "docs/TODO.org\n"
                "docs/notes/\n"
                "docs/2026-*.org\n"
                "scratch/\n"
            )
            publish.update_outer_gitignore(root)
            content = (root / ".gitignore").read_text()
            self.assertIn("docs/", content)
            self.assertIn(publish.PUBLISH_GITIGNORE_MARKER, content)
            # Legacy per-file lines removed
            self.assertNotIn("docs/TODO.org", content.replace("# docs/", ""))
            self.assertNotIn(
                "docs/notes/", content.replace("# docs/notes", "")
            )
            # Non-scrub entries preserved
            self.assertIn(".env", content)
            self.assertIn("scratch/", content)

    def test_update_outer_gitignore_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".gitignore").write_text(".env\n")
            publish.update_outer_gitignore(root)
            first = (root / ".gitignore").read_text()
            publish.update_outer_gitignore(root)
            second = (root / ".gitignore").read_text()
            self.assertEqual(first, second)

    def test_move_project_org_moves_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            docs = root / "docs"
            docs.mkdir()
            (docs / "PROJECT.org").write_text("# architecture\n")
            publish.move_project_org(docs, root)
            self.assertFalse((docs / "PROJECT.org").exists())
            self.assertTrue((root / "PROJECT.org").exists())

    def test_move_project_org_noop_when_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            docs = root / "docs"
            docs.mkdir()
            publish.move_project_org(docs, root)
            self.assertFalse((root / "PROJECT.org").exists())

    def test_move_project_org_skips_on_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            docs = root / "docs"
            docs.mkdir()
            (docs / "PROJECT.org").write_text("from docs\n")
            (root / "PROJECT.org").write_text("from root\n")
            publish.move_project_org(docs, root)
            self.assertEqual((root / "PROJECT.org").read_text(), "from root\n")
            self.assertTrue((docs / "PROJECT.org").exists())

    def test_init_notes_repo(self):
        with tempfile.TemporaryDirectory() as td:
            docs = Path(td)
            (docs / "TODO.org").write_text("* TODO test\n")
            env_overrides = {
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "t@example.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "t@example.com",
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "commit.gpgsign",
                "GIT_CONFIG_VALUE_0": "false",
            }
            with mock.patch.dict(os.environ, env_overrides, clear=False):
                publish.init_notes_repo(docs)
            self.assertTrue((docs / ".git").is_dir())
            log = _run(["git", "log", "--pretty=%s"], cwd=docs).stdout.strip()
            self.assertEqual(log, "initial notes snapshot")


class TestPublishSmoke(unittest.TestCase):
    """End-to-end: publish with --yes on a prepared temp repo, no scrub."""

    def test_publish_noscrub_flow(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_outer_repo(root)
            docs = root / "docs"
            docs.mkdir()
            (docs / "TODO.org").write_text("* TODO foo\n")
            (docs / "PROJECT.org").write_text("# architecture\n")
            _run(["git", "add", "docs"], cwd=root)
            _run(["git", "commit", "-q", "-m", "seed docs"], cwd=root)

            # Run publish in the temp root. Simulate `jolo publish --yes`.
            args = jolo.parse_args(["publish", "--yes"])
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                # init_notes_repo runs git without overriding commit.gpgsign.
                # Mirror what the fixture did globally for this test only.
                with mock.patch.object(
                    publish, "init_notes_repo", _init_notes_repo_unsigned
                ):
                    publish.run_publish_mode(args)
            finally:
                os.chdir(old_cwd)

            # docs/.git exists
            self.assertTrue((docs / ".git").is_dir())
            # PROJECT.org moved to root
            self.assertTrue((root / "PROJECT.org").exists())
            self.assertFalse((docs / "PROJECT.org").exists())
            # outer .gitignore has docs/
            gi = (root / ".gitignore").read_text()
            self.assertIn(publish.PUBLISH_GITIGNORE_MARKER, gi)
            # outer repo has a new commit
            last = _run(
                ["git", "log", "-1", "--pretty=%s"], cwd=root
            ).stdout.strip()
            self.assertIn("public-notes mode", last)


def _init_notes_repo_unsigned(docs_dir: Path) -> None:
    """Test helper: same as publish.init_notes_repo but disables signing."""
    _run(["git", "-C", str(docs_dir), "init", "-q", "-b", "main"])
    _run(["git", "-C", str(docs_dir), "config", "user.email", "t@example.com"])
    _run(["git", "-C", str(docs_dir), "config", "user.name", "Test"])
    _run(
        [
            "git",
            "-C",
            str(docs_dir),
            "config",
            "commit.gpgsign",
            "false",
        ]
    )
    _run(["git", "-C", str(docs_dir), "add", "-A"])
    _run(
        [
            "git",
            "-C",
            str(docs_dir),
            "commit",
            "-q",
            "-m",
            "initial notes snapshot",
        ]
    )


if __name__ == "__main__":
    unittest.main()
