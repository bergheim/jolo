#!/usr/bin/env python3
"""Tests for mode dispatch and config loading."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import jolo
except ImportError:
    jolo = None


class TestConfigLoading(unittest.TestCase):
    """Test TOML configuration loading."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_load_config_returns_defaults_when_no_files(self):
        """Should return default config when no config files exist."""
        os.chdir(self.tmpdir)
        config = jolo.load_config(global_config_dir=Path(self.tmpdir) / 'noexist')

        self.assertEqual(config['base_image'], 'localhost/emacs-gui:latest')
        self.assertEqual(config['pass_path_anthropic'], 'api/llm/anthropic')
        self.assertEqual(config['pass_path_openai'], 'api/llm/openai')

    def test_load_global_config(self):
        """Should load global config from ~/.config/jolo/config.toml."""
        config_dir = Path(self.tmpdir) / '.config' / 'jolo'
        config_dir.mkdir(parents=True)
        (config_dir / 'config.toml').write_text('base_image = "custom/image:v1"\n')

        config = jolo.load_config(global_config_dir=config_dir)

        self.assertEqual(config['base_image'], 'custom/image:v1')

    def test_load_project_config(self):
        """Should load project config from .jolo.toml."""
        os.chdir(self.tmpdir)
        Path(self.tmpdir, '.jolo.toml').write_text('base_image = "project/image:v2"\n')

        config = jolo.load_config(global_config_dir=Path(self.tmpdir) / 'noexist')

        self.assertEqual(config['base_image'], 'project/image:v2')

    def test_project_config_overrides_global(self):
        """Project config should override global config."""
        config_dir = Path(self.tmpdir) / '.config' / 'jolo'
        config_dir.mkdir(parents=True)
        (config_dir / 'config.toml').write_text('base_image = "global/image:v1"\n')

        os.chdir(self.tmpdir)
        Path(self.tmpdir, '.jolo.toml').write_text('base_image = "project/image:v2"\n')

        config = jolo.load_config(global_config_dir=config_dir)

        self.assertEqual(config['base_image'], 'project/image:v2')

    def test_config_partial_override(self):
        """Project config should only override specified keys."""
        config_dir = Path(self.tmpdir) / '.config' / 'jolo'
        config_dir.mkdir(parents=True)
        (config_dir / 'config.toml').write_text(
            'base_image = "global/image:v1"\npass_path_anthropic = "custom/path"\n'
        )

        os.chdir(self.tmpdir)
        Path(self.tmpdir, '.jolo.toml').write_text('base_image = "project/image:v2"\n')

        config = jolo.load_config(global_config_dir=config_dir)

        self.assertEqual(config['base_image'], 'project/image:v2')
        self.assertEqual(config['pass_path_anthropic'], 'custom/path')


class TestListMode(unittest.TestCase):
    """Test list functionality."""

    def test_list_flag(self):
        """list should set command to list."""
        args = jolo.parse_args(['list'])
        self.assertEqual(args.command, 'list')

    def test_list_default_false(self):
        """No command should leave command as None."""
        args = jolo.parse_args([])
        self.assertIsNone(args.command)

    def test_all_flag(self):
        """--all should set all to True."""
        args = jolo.parse_args(['list', '--all'])
        self.assertTrue(args.all)

    def test_all_short_flag(self):
        """-a should set all to True."""
        args = jolo.parse_args(['list', '-a'])
        self.assertTrue(args.all)

    def test_all_default_false(self):
        """--all should default to False."""
        args = jolo.parse_args(['list'])
        self.assertFalse(args.all)


class TestStopMode(unittest.TestCase):
    """Test down functionality."""

    def test_down_flag(self):
        """down should set command to down."""
        args = jolo.parse_args(['down'])
        self.assertEqual(args.command, 'down')

    def test_stop_default_false(self):
        """No command should leave command as None."""
        args = jolo.parse_args([])
        self.assertIsNone(args.command)


class TestAttachMode(unittest.TestCase):
    """Test attach functionality."""

    def test_attach_flag(self):
        """attach should set command to attach."""
        args = jolo.parse_args(['attach'])
        self.assertEqual(args.command, 'attach')

    def test_attach_default_false(self):
        """No command should leave command as None."""
        args = jolo.parse_args([])
        self.assertIsNone(args.command)


class TestDetachMode(unittest.TestCase):
    """Test --detach functionality."""

    def test_detach_flag(self):
        """--detach should set detach to True."""
        args = jolo.parse_args(['up', '--detach'])
        self.assertTrue(args.detach)

    def test_detach_short_flag(self):
        """-d should set detach to True."""
        args = jolo.parse_args(['up', '-d'])
        self.assertTrue(args.detach)

    def test_detach_default_false(self):
        """--detach should default to False."""
        args = jolo.parse_args([])
        self.assertFalse(args.detach)

    def test_detach_with_tree(self):
        """--detach can combine with tree."""
        args = jolo.parse_args(['tree', 'test', '--detach'])
        self.assertTrue(args.detach)
        self.assertEqual(args.name, 'test')


class TestPruneMode(unittest.TestCase):
    """Test prune functionality."""

    def test_prune_flag(self):
        """prune should set command to prune."""
        args = jolo.parse_args(['prune'])
        self.assertEqual(args.command, 'prune')

    def test_prune_default_false(self):
        """No command should leave command as None."""
        args = jolo.parse_args([])
        self.assertIsNone(args.command)


class TestPruneGlobalImages(unittest.TestCase):
    """Test image pruning in global mode."""

    @mock.patch('_jolo.commands.get_container_runtime', return_value='podman')
    @mock.patch('_jolo.commands.list_all_devcontainers')
    @mock.patch('_jolo.commands.remove_container', return_value=True)
    @mock.patch('_jolo.commands.remove_image', return_value=True)
    @mock.patch('builtins.input', return_value='y')
    @mock.patch('subprocess.run')
    @mock.patch('os.path.exists', return_value=True)
    def test_prune_global_removes_unused_images(
        self, mock_exists, mock_run, mock_input, mock_remove_image, mock_remove_container,
        mock_list, mock_runtime
    ):
        """Should remove images not used by remaining containers."""
        # Initial list: one stopped container with an image
        mock_list.side_effect = [
            [("stopped-c", "/path/to/proj", "exited", "img123")],  # first call
            []  # second call (remaining containers)
        ]
        mock_run.return_value = mock.Mock(returncode=0)

        # Mock Path.exists to return True so it's not orphan
        with mock.patch('_jolo.commands.Path.exists', return_value=True):
            jolo.run_prune_global_mode()

        mock_remove_container.assert_called_with("stopped-c")
        mock_remove_image.assert_called_with("img123")

    @mock.patch('_jolo.commands.get_container_runtime', return_value='podman')
    @mock.patch('_jolo.commands.list_all_devcontainers')
    @mock.patch('_jolo.commands.remove_container', return_value=True)
    @mock.patch('_jolo.commands.remove_image')
    @mock.patch('builtins.input', return_value='y')
    @mock.patch('subprocess.run')
    def test_prune_global_skips_in_use_images(
        self, mock_run, mock_input, mock_remove_image, mock_remove_container,
        mock_list, mock_runtime
    ):
        """Should NOT remove images still used by other containers."""
        # Initial list: one stopped, one running, both using same image
        mock_list.side_effect = [
            [
                ("stopped-c", "/path/1", "exited", "img123"),
                ("running-c", "/path/2", "running", "img123")
            ],
            [("running-c", "/path/2", "running", "img123")]
        ]
        mock_run.return_value = mock.Mock(returncode=0)

        # Mock Path.exists to return True so running-c is not orphan
        with mock.patch('_jolo.commands.Path.exists', return_value=True):
            jolo.run_prune_global_mode()

        mock_remove_container.assert_called_with("stopped-c")
        mock_remove_image.assert_not_called()



if __name__ == '__main__':
    unittest.main()
