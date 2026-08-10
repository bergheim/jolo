#!/usr/bin/env python3
"""Tests for container/wt's link_ignored.

The function text is lifted out of the real script and sourced, because
`wt new` needs a live tmux session. What earns the coverage is the exclude
bookkeeping: gitignore patterns written as "data/" match directories only and
never a symlink, so without the anchored entry these links show up as untracked
and assert_worktree_clean rejects the worktree on the next sync or land.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "container" / "wt"

GITIGNORE = """data/
node_modules/
.venv/
.devcontainer/
scratch/
__pycache__/
docs/notes/
docs/TODO.org
.coverage
"""


def link_ignored_lib():
    """The WT_NO_LINK..link_ignored block, verbatim from the real script."""
    text = SCRIPT.read_text()
    start = text.index("WT_NO_LINK=")
    end = text.index("\n}\n", text.index("link_ignored()")) + len("\n}\n")
    return text[start:end]


class LinkIgnoredTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir(parents=True)
        self.git("init", "-q")

        (self.repo / ".gitignore").write_text(GITIGNORE)
        for directory in (
            "data",
            "docs/notes",
            "node_modules",
            ".venv",
            ".devcontainer",
            "scratch",
            "__pycache__",
        ):
            (self.repo / directory).mkdir(parents=True)
        (self.repo / "data" / "catalog.jsonl").write_text("row\n")
        (self.repo / "docs" / "notes" / "n1.org").write_text("note\n")
        (self.repo / "docs" / "TODO.org").write_text("* TODO thing\n")
        (self.repo / "docs" / "README.md").write_text("tracked\n")
        (self.repo / "node_modules" / "pkg").write_text("dep\n")
        (self.repo / ".venv" / "pyvenv.cfg").write_text("cfg\n")
        (self.repo / ".devcontainer" / "devcontainer.json").write_text("{}\n")
        (self.repo / "scratch" / "tmp.txt").write_text("tmp\n")
        (self.repo / "__pycache__" / "x.pyc").write_text("pyc\n")
        (self.repo / ".coverage").write_text("cov\n")

        self.git("add", ".gitignore", "docs/README.md")
        self.git(
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-qm",
            "init",
        )
        self.wt = self.repo / ".worktrees" / "wtA"
        self.git("worktree", "add", "-q", str(self.wt), "-b", "wtA")

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *args, cwd=None):
        return subprocess.run(
            ["git", "-C", str(cwd or self.repo), *args],
            capture_output=True,
            text=True,
            check=True,
        )

    def link(self):
        script = f'WS="{self.repo}"\n{link_ignored_lib()}\nlink_ignored "{self.wt}"\n'
        result = subprocess.run(
            ["sh", "-c", script], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_links_data_and_nested_notes(self):
        self.link()
        self.assertEqual(
            (self.wt / "data" / "catalog.jsonl").read_text(), "row\n"
        )
        self.assertEqual(
            (self.wt / "docs" / "TODO.org").read_text(), "* TODO thing\n"
        )
        self.assertEqual(
            (self.wt / "docs" / "notes" / "n1.org").read_text(), "note\n"
        )

    def test_nested_link_targets_are_relative_and_depth_correct(self):
        self.link()
        self.assertEqual(
            (self.wt / "data").readlink().as_posix(), "../../data"
        )
        self.assertEqual(
            (self.wt / "docs" / "notes").readlink().as_posix(),
            "../../../docs/notes",
        )

    def test_environments_caches_and_devcontainer_are_not_linked(self):
        """Installing through these would rewrite the main workspace."""
        self.link()
        for skipped in (
            "node_modules",
            ".venv",
            ".devcontainer",
            "__pycache__",
            ".coverage",
        ):
            self.assertFalse(
                (self.wt / skipped).exists(), f"{skipped} must not be linked"
            )

    def test_worktree_stays_clean(self):
        """Untracked symlinks would break wt sync and wt land."""
        self.link()
        status = self.git("status", "--porcelain", cwd=self.wt).stdout
        self.assertEqual(status, "", f"worktree not clean:\n{status}")

    def test_main_tree_stays_clean(self):
        self.link()
        status = self.git("status", "--porcelain").stdout
        self.assertNotIn("data", status)
        self.assertNotIn("docs/", status)

    def test_is_idempotent(self):
        self.link()
        second = self.link()
        self.assertEqual(
            second.strip(), "", f"re-linked on second run:\n{second}"
        )
        self.assertFalse(
            (self.repo / "data" / "data").exists(),
            "self-referential link created inside the main tree",
        )

    def test_does_not_clobber_a_path_tracked_on_the_branch(self):
        (self.wt / "data").mkdir()
        (self.wt / "data" / "branch-owned.txt").write_text("mine\n")
        self.link()
        self.assertFalse((self.wt / "data").is_symlink())
        self.assertEqual(
            (self.wt / "data" / "branch-owned.txt").read_text(), "mine\n"
        )


if __name__ == "__main__":
    unittest.main()
