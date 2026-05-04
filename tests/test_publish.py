#!/usr/bin/env python3
"""Tests for jolo publish (public-notes mode flip)."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import jolo
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
            }
            with mock.patch.dict(os.environ, env_overrides, clear=False):
                publish.init_notes_repo(docs)
            self.assertTrue((docs / ".git").is_dir())
            log = _run(["git", "log", "--pretty=%s"], cwd=docs).stdout.strip()
            self.assertEqual(log, "initial notes snapshot")
            # init_notes_repo must force signing off so it never prompts or
            # fails under users with commit.gpgsign=true globally.
            gpg = _run(
                ["git", "-C", str(docs), "config", "commit.gpgsign"]
            ).stdout.strip()
            self.assertEqual(gpg, "false")

    def test_untrack_docs_from_outer_removes_tracked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_outer_repo(root)
            docs = root / "docs"
            docs.mkdir()
            (docs / "TODO.org").write_text("* TODO\n")
            (docs / "MEMORY.org").write_text("* notes\n")
            _run(["git", "add", "docs/"], cwd=root)
            _run(["git", "commit", "-q", "-m", "add docs"], cwd=root)

            publish.untrack_docs_from_outer(root)

            # Files still exist on disk.
            self.assertTrue((docs / "TODO.org").exists())
            self.assertTrue((docs / "MEMORY.org").exists())
            # But the outer index no longer tracks them — ls-files shows none.
            tracked = _run(
                ["git", "ls-files", "docs/"], cwd=root
            ).stdout.strip()
            self.assertEqual(tracked, "")

    def test_untrack_docs_from_outer_noop_when_not_tracked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _make_outer_repo(root)
            # docs/ does not exist yet — command must not error.
            publish.untrack_docs_from_outer(root)


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
            env_overrides = {
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "t@example.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "t@example.com",
            }
            try:
                os.chdir(root)
                with mock.patch.dict(os.environ, env_overrides, clear=False):
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
            # Outer repo must NOT track anything under docs/ anymore — this
            # is the leak guard from review 1.
            outer_tracked = _run(
                ["git", "ls-files", "docs/"], cwd=root
            ).stdout.strip()
            self.assertEqual(outer_tracked, "")


if __name__ == "__main__":
    unittest.main()
