#!/usr/bin/env python3
"""Tests for jolo delete command (unified worktree + project deletion)."""

import unittest
from pathlib import Path
from unittest import mock

try:
    import jolo
except ImportError:
    jolo = None


class TestDeleteArgParsing(unittest.TestCase):
    """Test delete argument parsing."""

    def test_delete_command(self):
        """delete should set command to delete."""
        args = jolo.parse_args(["delete"])
        self.assertEqual(args.command, "delete")

    def test_delete_with_target_name(self):
        """delete TARGET should set target."""
        args = jolo.parse_args(["delete", "feature-x"])
        self.assertEqual(args.target, "feature-x")

    def test_delete_with_path_target(self):
        """delete /some/path should set target to path."""
        args = jolo.parse_args(["delete", "/tmp/myproject"])
        self.assertEqual(args.target, "/tmp/myproject")

    def test_delete_target_optional(self):
        """delete without target should default to None (interactive)."""
        args = jolo.parse_args(["delete"])
        self.assertIsNone(args.target)

    def test_delete_yes_flag(self):
        """--yes should skip confirmation."""
        args = jolo.parse_args(["delete", "feature-x", "--yes"])
        self.assertTrue(args.yes)

    def test_delete_purge_flag(self):
        """--purge should be recognized."""
        args = jolo.parse_args(["delete", "--purge"])
        self.assertTrue(args.purge)

    def test_delete_purge_default_false(self):
        """--purge should default to False."""
        args = jolo.parse_args(["delete"])
        self.assertFalse(args.purge)

    def test_destroy_command_removed(self):
        """destroy subcommand should no longer exist."""
        with self.assertRaises(SystemExit):
            jolo.parse_args(["destroy"])


class TestDeleteWorktreeByName(unittest.TestCase):
    """Test deleting a worktree by name."""

    @mock.patch("_jolo.commands.find_git_root")
    def test_requires_git_repo_for_name(self, mock_git_root):
        """Should error if not in a git repo when name given."""
        mock_git_root.return_value = None
        args = jolo.parse_args(["delete", "feature-x"])
        with self.assertRaises(SystemExit):
            jolo.run_delete_mode(args)

    @mock.patch("_jolo.commands.find_git_root")
    @mock.patch("_jolo.commands.list_worktrees")
    def test_error_when_no_worktrees(self, mock_list, mock_git_root):
        """Should error when no worktrees exist."""
        mock_git_root.return_value = Path("/fake/project")
        mock_list.return_value = [(Path("/fake/project"), "abc123", "main")]
        args = jolo.parse_args(["delete", "feature-x"])
        with self.assertRaises(SystemExit):
            jolo.run_delete_mode(args)

    @mock.patch("_jolo.commands.find_git_root")
    @mock.patch("_jolo.commands.list_worktrees")
    def test_error_when_worktree_not_found(self, mock_list, mock_git_root):
        """Should error when specified worktree doesn't exist."""
        mock_git_root.return_value = Path("/fake/project")
        mock_list.return_value = [
            (Path("/fake/project"), "abc123", "main"),
            (Path("/fake/project-worktrees/other"), "def456", "other"),
        ]
        args = jolo.parse_args(["delete", "nonexistent"])
        with self.assertRaises(SystemExit):
            jolo.run_delete_mode(args)

    @mock.patch("_jolo.commands.find_git_root")
    @mock.patch("_jolo.commands.list_worktrees")
    @mock.patch("_jolo.commands.stop_container")
    @mock.patch("_jolo.commands.remove_worktree")
    @mock.patch("builtins.input", return_value="y")
    def test_deletes_worktree_with_confirmation(
        self, mock_input, mock_remove, mock_stop, mock_list, mock_git_root
    ):
        """Should delete worktree after confirmation."""
        mock_git_root.return_value = Path("/fake/project")
        wt_path = Path("/fake/project-worktrees/feature-x")
        mock_list.return_value = [
            (Path("/fake/project"), "abc123", "main"),
            (wt_path, "def456", "feature-x"),
        ]
        mock_stop.return_value = True
        mock_remove.return_value = True

        args = jolo.parse_args(["delete", "feature-x"])
        jolo.run_delete_mode(args)

        mock_remove.assert_called_once()

    @mock.patch("_jolo.commands.find_git_root")
    @mock.patch("_jolo.commands.list_worktrees")
    @mock.patch("_jolo.commands.stop_container")
    @mock.patch("_jolo.commands.remove_worktree")
    def test_yes_skips_confirmation(
        self, mock_remove, mock_stop, mock_list, mock_git_root
    ):
        """--yes should skip confirmation prompt."""
        mock_git_root.return_value = Path("/fake/project")
        wt_path = Path("/fake/project-worktrees/feature-x")
        mock_list.return_value = [
            (Path("/fake/project"), "abc123", "main"),
            (wt_path, "def456", "feature-x"),
        ]
        mock_stop.return_value = True
        mock_remove.return_value = True

        args = jolo.parse_args(["delete", "feature-x", "--yes"])
        with mock.patch("builtins.input") as mock_input:
            jolo.run_delete_mode(args)
            mock_input.assert_not_called()

    @mock.patch("_jolo.commands.find_git_root")
    @mock.patch("_jolo.commands.list_worktrees")
    @mock.patch("builtins.input", return_value="n")
    def test_cancellation(self, mock_input, mock_list, mock_git_root):
        """Should cancel when user says no."""
        mock_git_root.return_value = Path("/fake/project")
        wt_path = Path("/fake/project-worktrees/feature-x")
        mock_list.return_value = [
            (Path("/fake/project"), "abc123", "main"),
            (wt_path, "def456", "feature-x"),
        ]

        args = jolo.parse_args(["delete", "feature-x"])
        with mock.patch("_jolo.commands.remove_worktree") as mock_remove:
            jolo.run_delete_mode(args)
            mock_remove.assert_not_called()


class TestDeleteProjectByPath(unittest.TestCase):
    """Test deleting a project by path."""

    @mock.patch("_jolo.commands.find_git_root")
    def test_path_target_resolves_project(self, mock_git_root):
        """Path starting with / should be treated as project deletion."""
        mock_git_root.return_value = None  # cwd git root
        args = jolo.parse_args(["delete", "/nonexistent/path"])
        with self.assertRaises(SystemExit) as cm:
            jolo.run_delete_mode(args)
        self.assertIn("does not exist", str(cm.exception))

    @mock.patch("_jolo.commands.find_git_root")
    def test_dot_path_treated_as_project(self, mock_outer_git_root):
        """Path starting with . should be treated as project deletion."""
        mock_outer_git_root.return_value = None  # for cwd check
        args = jolo.parse_args(["delete", "./nonexistent"])
        with self.assertRaises(SystemExit):
            jolo.run_delete_mode(args)

    @mock.patch("_jolo.commands.find_git_root")
    @mock.patch("_jolo.commands.get_container_runtime")
    @mock.patch("_jolo.commands.find_containers_for_project")
    @mock.patch("_jolo.commands.list_worktrees")
    @mock.patch("_jolo.commands.remove_container")
    @mock.patch("_jolo.commands.subprocess.run")
    @mock.patch("builtins.input", return_value="y")
    def test_delete_project_stops_and_removes_containers(
        self,
        mock_input,
        mock_subproc,
        mock_remove,
        mock_list,
        mock_find_containers,
        mock_runtime,
        mock_git_root,
    ):
        """Deleting a project should stop and remove its containers."""
        project = Path("/fake/project")
        # find_git_root is called twice: once for cwd (returns None), once for target path
        mock_git_root.side_effect = [None, project]
        mock_runtime.return_value = "podman"
        mock_list.return_value = [(project, "abc123", "main")]  # no worktrees
        mock_find_containers.return_value = [
            ("test-container", "/fake/project", "running", "img123")
        ]
        mock_subproc.return_value = mock.MagicMock(returncode=0)
        mock_remove.return_value = True

        with mock.patch.object(Path, "exists", return_value=True):
            with mock.patch.object(Path, "resolve", return_value=project):
                args = jolo.parse_args(["delete", "/fake/project", "--yes"])
                jolo.run_delete_mode(args)

        mock_remove.assert_called_once()

    @mock.patch("_jolo.commands.find_git_root")
    @mock.patch("_jolo.commands.get_container_runtime")
    @mock.patch("_jolo.commands.find_containers_for_project")
    @mock.patch("_jolo.commands.list_worktrees")
    @mock.patch("_jolo.commands.remove_container")
    @mock.patch("_jolo.commands.subprocess.run")
    @mock.patch("_jolo.commands.shutil.rmtree")
    def test_purge_removes_directories(
        self,
        mock_rmtree,
        mock_subproc,
        mock_remove,
        mock_list,
        mock_find_containers,
        mock_runtime,
        mock_git_root,
    ):
        """--purge should remove project directories."""
        project = Path("/fake/project")
        mock_git_root.side_effect = [None, project]
        mock_runtime.return_value = "podman"
        mock_list.return_value = [(project, "abc123", "main")]
        mock_find_containers.return_value = []
        mock_remove.return_value = True

        with mock.patch.object(Path, "exists", return_value=True):
            with mock.patch.object(Path, "resolve", return_value=project):
                args = jolo.parse_args(
                    ["delete", "/fake/project", "--purge", "--yes"]
                )
                jolo.run_delete_mode(args)

        # Should have called rmtree for the project directory
        mock_rmtree.assert_called()


class TestDeleteProjectWithWorktrees(unittest.TestCase):
    """Test deleting a project that has worktrees."""

    @mock.patch("_jolo.commands.find_git_root")
    @mock.patch("_jolo.commands.get_container_runtime")
    @mock.patch("_jolo.commands.find_containers_for_project")
    @mock.patch("_jolo.commands.list_worktrees")
    @mock.patch("_jolo.commands.stop_container")
    @mock.patch("_jolo.commands.remove_worktree")
    @mock.patch("_jolo.commands.remove_container")
    @mock.patch("_jolo.commands.subprocess.run")
    def test_yes_deletes_worktrees_too(
        self,
        mock_subproc,
        mock_remove_container,
        mock_remove_wt,
        mock_stop,
        mock_list,
        mock_find_containers,
        mock_runtime,
        mock_git_root,
    ):
        """With --yes, project deletion should also delete worktrees."""
        project = Path("/fake/project")
        wt_path = Path("/fake/project-worktrees/feat")
        mock_git_root.side_effect = [None, project]
        mock_runtime.return_value = "podman"
        mock_list.return_value = [
            (project, "abc123", "main"),
            (wt_path, "def456", "feat"),
        ]
        mock_find_containers.return_value = []
        mock_stop.return_value = True
        mock_remove_wt.return_value = True
        mock_remove_container.return_value = True

        with mock.patch.object(Path, "exists", return_value=True):
            with mock.patch.object(Path, "resolve", return_value=project):
                args = jolo.parse_args(["delete", "/fake/project", "--yes"])
                jolo.run_delete_mode(args)

        mock_remove_wt.assert_called_once()

    @mock.patch("_jolo.commands.find_git_root")
    @mock.patch("_jolo.commands.get_container_runtime")
    @mock.patch("_jolo.commands.list_worktrees")
    @mock.patch("_jolo.commands.find_containers_for_project")
    @mock.patch("builtins.input", return_value="n")
    def test_prompt_about_worktrees_without_yes(
        self,
        mock_input,
        mock_find_containers,
        mock_list,
        mock_runtime,
        mock_git_root,
    ):
        """Without --yes, should prompt about worktree deletion and cancel on 'n'."""
        project = Path("/fake/project")
        wt_path = Path("/fake/project-worktrees/feat")
        mock_git_root.side_effect = [None, project]
        mock_runtime.return_value = "podman"
        mock_list.return_value = [
            (project, "abc123", "main"),
            (wt_path, "def456", "feat"),
        ]
        mock_find_containers.return_value = []

        with mock.patch.object(Path, "exists", return_value=True):
            with mock.patch.object(Path, "resolve", return_value=project):
                # First input confirms project deletion, but _delete_project
                # is called internally and prompts about worktrees
                args = jolo.parse_args(["delete", "/fake/project"])
                with mock.patch("builtins.input", side_effect=["y", "n"]):
                    jolo.run_delete_mode(args)


class TestDeleteInteractivePicker(unittest.TestCase):
    """Test interactive picker mode (no target arg)."""

    @mock.patch("_jolo.commands.find_git_root")
    @mock.patch("_jolo.commands.list_all_devcontainers")
    def test_no_items_exits(self, mock_containers, mock_git_root):
        """Should exit when no items found."""
        mock_git_root.return_value = None
        mock_containers.return_value = []

        args = jolo.parse_args(["delete"])
        with self.assertRaises(SystemExit):
            jolo.run_delete_mode(args)

    @mock.patch("_jolo.commands.find_git_root")
    @mock.patch("_jolo.commands.list_all_devcontainers")
    @mock.patch("_jolo.commands.list_worktrees")
    @mock.patch("_jolo.commands.shutil.which", return_value=None)
    @mock.patch("_jolo.commands.stop_container")
    @mock.patch("_jolo.commands.remove_worktree")
    @mock.patch("builtins.input")
    def test_picker_selects_worktree(
        self,
        mock_input,
        mock_remove,
        mock_stop,
        mock_which,
        mock_list,
        mock_containers,
        mock_git_root,
    ):
        """Interactive picker should allow selecting a worktree."""
        project = Path("/fake/project")
        wt_path = Path("/fake/project-worktrees/feat")
        mock_git_root.return_value = None
        # find_git_root is called again inside _build_delete_picker_items
        with mock.patch("_jolo.commands.find_git_root") as mock_fgr:
            mock_fgr.side_effect = [None, project]
            mock_containers.return_value = [
                ("proj", "/fake/project", "running", "img123"),
            ]
            mock_list.return_value = [
                (project, "abc123", "main"),
                (wt_path, "def456", "feat"),
            ]
            with mock.patch.object(Path, "exists", return_value=True):
                # Select second item (worktree), then confirm
                mock_input.side_effect = ["2", "y"]
                mock_stop.return_value = True
                mock_remove.return_value = True

                args = jolo.parse_args(["delete"])
                jolo.run_delete_mode(args)

                mock_remove.assert_called_once()


if __name__ == "__main__":
    unittest.main()
