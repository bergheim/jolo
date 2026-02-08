#!/usr/bin/env python3
"""Tests for jolo delete command."""

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
        args = jolo.parse_args(['delete'])
        self.assertEqual(args.command, 'delete')

    def test_delete_with_name(self):
        """delete NAME should set name."""
        args = jolo.parse_args(['delete', 'feature-x'])
        self.assertEqual(args.name, 'feature-x')

    def test_delete_name_optional(self):
        """delete without name should default to None (interactive)."""
        args = jolo.parse_args(['delete'])
        self.assertIsNone(args.name)

    def test_delete_yes_flag(self):
        """--yes should skip confirmation."""
        args = jolo.parse_args(['delete', 'feature-x', '--yes'])
        self.assertTrue(args.yes)


class TestRunDeleteMode(unittest.TestCase):
    """Test run_delete_mode dispatching."""

    @mock.patch('_jolo.commands.find_git_root')
    def test_requires_git_repo(self, mock_git_root):
        """Should error if not in a git repo."""
        mock_git_root.return_value = None
        args = jolo.parse_args(['delete', 'feature-x'])
        with self.assertRaises(SystemExit):
            jolo.run_delete_mode(args)

    @mock.patch('_jolo.commands.find_git_root')
    @mock.patch('_jolo.commands.list_worktrees')
    def test_error_when_no_worktrees(self, mock_list, mock_git_root):
        """Should error when no worktrees exist."""
        mock_git_root.return_value = Path('/fake/project')
        # Only the main worktree
        mock_list.return_value = [(Path('/fake/project'), 'abc123', 'main')]
        args = jolo.parse_args(['delete', 'feature-x'])
        with self.assertRaises(SystemExit):
            jolo.run_delete_mode(args)

    @mock.patch('_jolo.commands.find_git_root')
    @mock.patch('_jolo.commands.list_worktrees')
    def test_error_when_worktree_not_found(self, mock_list, mock_git_root):
        """Should error when specified worktree doesn't exist."""
        mock_git_root.return_value = Path('/fake/project')
        mock_list.return_value = [
            (Path('/fake/project'), 'abc123', 'main'),
            (Path('/fake/project-worktrees/other'), 'def456', 'other'),
        ]
        args = jolo.parse_args(['delete', 'nonexistent'])
        with self.assertRaises(SystemExit):
            jolo.run_delete_mode(args)

    @mock.patch('_jolo.commands.find_git_root')
    @mock.patch('_jolo.commands.list_worktrees')
    @mock.patch('_jolo.commands.stop_container')
    @mock.patch('_jolo.commands.remove_worktree')
    @mock.patch('builtins.input', return_value='y')
    def test_deletes_worktree_with_confirmation(
        self, mock_input, mock_remove, mock_stop, mock_list, mock_git_root
    ):
        """Should delete worktree after confirmation."""
        mock_git_root.return_value = Path('/fake/project')
        wt_path = Path('/fake/project-worktrees/feature-x')
        mock_list.return_value = [
            (Path('/fake/project'), 'abc123', 'main'),
            (wt_path, 'def456', 'feature-x'),
        ]
        mock_stop.return_value = True
        mock_remove.return_value = True

        args = jolo.parse_args(['delete', 'feature-x'])
        jolo.run_delete_mode(args)

        mock_remove.assert_called_once()

    @mock.patch('_jolo.commands.find_git_root')
    @mock.patch('_jolo.commands.list_worktrees')
    @mock.patch('_jolo.commands.stop_container')
    @mock.patch('_jolo.commands.remove_worktree')
    def test_yes_skips_confirmation(
        self, mock_remove, mock_stop, mock_list, mock_git_root
    ):
        """--yes should skip confirmation prompt."""
        mock_git_root.return_value = Path('/fake/project')
        wt_path = Path('/fake/project-worktrees/feature-x')
        mock_list.return_value = [
            (Path('/fake/project'), 'abc123', 'main'),
            (wt_path, 'def456', 'feature-x'),
        ]
        mock_stop.return_value = True
        mock_remove.return_value = True

        args = jolo.parse_args(['delete', 'feature-x', '--yes'])
        with mock.patch('builtins.input') as mock_input:
            jolo.run_delete_mode(args)
            mock_input.assert_not_called()

    @mock.patch('_jolo.commands.find_git_root')
    @mock.patch('_jolo.commands.list_worktrees')
    @mock.patch('builtins.input', return_value='n')
    def test_cancellation(self, mock_input, mock_list, mock_git_root):
        """Should cancel when user says no."""
        mock_git_root.return_value = Path('/fake/project')
        wt_path = Path('/fake/project-worktrees/feature-x')
        mock_list.return_value = [
            (Path('/fake/project'), 'abc123', 'main'),
            (wt_path, 'def456', 'feature-x'),
        ]

        args = jolo.parse_args(['delete', 'feature-x'])
        with mock.patch('_jolo.commands.remove_worktree') as mock_remove:
            jolo.run_delete_mode(args)
            mock_remove.assert_not_called()


if __name__ == '__main__':
    unittest.main()
