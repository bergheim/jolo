#!/usr/bin/env python3
"""Tests for git worktree operations."""

import json
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


class TestWorktreePaths(unittest.TestCase):
    """Test worktree path computation."""

    def test_worktree_path_computation(self):
        """Should compute worktree path as ../PROJECT-worktrees/NAME."""
        path = jolo.get_worktree_path("/dev/myapp", "feature-x")
        self.assertEqual(path, Path("/dev/myapp-worktrees/feature-x"))

    def test_worktree_path_with_trailing_slash(self):
        """Should handle trailing slash in project path."""
        path = jolo.get_worktree_path("/dev/myapp/", "feature-x")
        self.assertEqual(path, Path("/dev/myapp-worktrees/feature-x"))


class TestModeValidation(unittest.TestCase):
    """Test validation for different modes."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_tree_mode_requires_git_repo(self):
        """--tree should fail if not in git repo."""
        os.chdir(self.tmpdir)  # Not a git repo

        with self.assertRaises(SystemExit) as cm:
            jolo.validate_tree_mode()
        self.assertIn("git", str(cm.exception.code).lower())

    def test_create_mode_forbids_git_repo(self):
        """--create should fail if already in git repo."""
        git_dir = Path(self.tmpdir) / ".git"
        git_dir.mkdir()
        os.chdir(self.tmpdir)

        with self.assertRaises(SystemExit) as cm:
            jolo.validate_create_mode("newproject")
        self.assertIn("git", str(cm.exception.code).lower())

    def test_create_mode_forbids_existing_directory(self):
        """--create should fail if directory exists."""
        os.chdir(self.tmpdir)
        existing = Path(self.tmpdir) / "existing"
        existing.mkdir()

        with self.assertRaises(SystemExit) as cm:
            jolo.validate_create_mode("existing")
        self.assertIn("exists", str(cm.exception.code).lower())


class TestWorktreeExists(unittest.TestCase):
    """Test behavior when worktree already exists."""

    def test_existing_worktree_returns_path(self):
        """Should return existing worktree path instead of erroring."""
        # If worktree exists, get_or_create_worktree should return the path
        # without trying to create it
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree_path = Path(tmpdir) / "existing-worktree"
            worktree_path.mkdir()
            (worktree_path / ".devcontainer").mkdir()

            result = jolo.get_or_create_worktree(
                git_root=Path(tmpdir),
                worktree_name="existing-worktree",
                worktree_path=worktree_path,
            )

            self.assertEqual(result, worktree_path)
            self.assertTrue(result.exists())


class TestWorktreeDevcontainer(unittest.TestCase):
    """Test worktree-specific devcontainer configuration."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_add_git_mount_to_devcontainer(self):
        """Should add mount for main repo .git directory."""
        # Create a devcontainer.json
        devcontainer_dir = Path(self.tmpdir) / ".devcontainer"
        devcontainer_dir.mkdir()
        json_file = devcontainer_dir / "devcontainer.json"

        original = {
            "name": "test",
            "mounts": ["source=/tmp,target=/tmp,type=bind"],
        }
        json_file.write_text(json.dumps(original))

        # Add git mount
        main_git_dir = Path("/home/user/project/.git")
        jolo.add_worktree_git_mount(json_file, main_git_dir)

        # Verify mount was added
        updated = json.loads(json_file.read_text())
        self.assertEqual(len(updated["mounts"]), 2)

        git_mount = updated["mounts"][1]
        self.assertIn("/home/user/project/.git", git_mount)
        self.assertIn("source=", git_mount)
        self.assertIn("target=", git_mount)

    def test_add_git_mount_creates_mounts_array(self):
        """Should create mounts array if not present."""
        devcontainer_dir = Path(self.tmpdir) / ".devcontainer"
        devcontainer_dir.mkdir()
        json_file = devcontainer_dir / "devcontainer.json"

        original = {"name": "test"}
        json_file.write_text(json.dumps(original))

        main_git_dir = Path("/home/user/project/.git")
        jolo.add_worktree_git_mount(json_file, main_git_dir)

        updated = json.loads(json_file.read_text())
        self.assertIn("mounts", updated)
        self.assertEqual(len(updated["mounts"]), 1)


class TestListWorktrees(unittest.TestCase):
    """Test worktree listing functionality."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_list_worktrees_empty_on_non_git(self):
        """Should return empty list for non-git directory."""
        os.chdir(self.tmpdir)
        result = jolo.list_worktrees(Path(self.tmpdir))
        self.assertEqual(result, [])

    def test_list_worktrees_returns_main_repo(self):
        """Should return main repo as first worktree."""
        os.chdir(self.tmpdir)
        subprocess.run(["git", "init"], cwd=self.tmpdir, capture_output=True)
        # Create an initial commit so git worktree list works
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=self.tmpdir,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=self.tmpdir,
            capture_output=True,
        )
        Path(self.tmpdir, "README").write_text("test")
        subprocess.run(
            ["git", "add", "."], cwd=self.tmpdir, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=self.tmpdir,
            capture_output=True,
        )

        result = jolo.list_worktrees(Path(self.tmpdir))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], Path(self.tmpdir))

    def test_find_project_workspaces_includes_main(self):
        """Should always include main repo in workspaces."""
        os.chdir(self.tmpdir)
        subprocess.run(["git", "init"], cwd=self.tmpdir, capture_output=True)

        git_root = Path(self.tmpdir)
        result = jolo.find_project_workspaces(git_root)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], git_root)
        self.assertEqual(result[0][1], "main")


class TestFromBranch(unittest.TestCase):
    """Test --from BRANCH functionality."""

    def test_from_flag(self):
        """--from should set from_branch."""
        args = jolo.parse_args(["tree", "test", "--from", "main"])
        self.assertEqual(args.from_branch, "main")

    def test_from_default_none(self):
        """--from should default to None."""
        args = jolo.parse_args(["tree", "test"])
        self.assertIsNone(args.from_branch)

    def test_from_with_tree(self):
        """--from can combine with tree."""
        args = jolo.parse_args(["tree", "feature", "--from", "develop"])
        self.assertEqual(args.name, "feature")
        self.assertEqual(args.from_branch, "develop")


class TestBranchExists(unittest.TestCase):
    """Test branch existence checking."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        # Set up a git repo with a commit
        subprocess.run(["git", "init"], cwd=self.tmpdir, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=self.tmpdir,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=self.tmpdir,
            capture_output=True,
        )
        Path(self.tmpdir, "README").write_text("test")
        subprocess.run(
            ["git", "add", "."], cwd=self.tmpdir, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=self.tmpdir,
            capture_output=True,
        )

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_branch_exists_for_existing_branch(self):
        """Should return True for existing branch."""
        result = jolo.branch_exists(Path(self.tmpdir), "master")
        self.assertTrue(result)

    def test_branch_exists_for_nonexistent_branch(self):
        """Should return False for nonexistent branch."""
        result = jolo.branch_exists(Path(self.tmpdir), "nonexistent")
        self.assertFalse(result)


class TestFindStaleWorktrees(unittest.TestCase):
    """Test stale worktree detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_find_stale_worktrees_returns_empty_for_fresh_repo(self):
        """Should return empty list when no stale worktrees."""
        os.chdir(self.tmpdir)
        subprocess.run(["git", "init"], cwd=self.tmpdir, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=self.tmpdir,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=self.tmpdir,
            capture_output=True,
        )
        Path(self.tmpdir, "README").write_text("test")
        subprocess.run(
            ["git", "add", "."], cwd=self.tmpdir, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=self.tmpdir,
            capture_output=True,
        )

        result = jolo.find_stale_worktrees(Path(self.tmpdir))
        self.assertEqual(result, [])


class TestRemoveWorktree(unittest.TestCase):
    """Test worktree removal."""

    def test_remove_worktree_calls_git(self):
        """Should call git worktree remove."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0)
            result = jolo.remove_worktree(
                Path("/project"), Path("/project-worktrees/foo")
            )
            self.assertTrue(result)
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            self.assertIn("worktree", args)
            self.assertIn("remove", args)


if __name__ == "__main__":
    unittest.main()
