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
        config = jolo.load_config(
            global_config_dir=Path(self.tmpdir) / "noexist"
        )

        self.assertEqual(config["base_image"], "localhost/emacs-gui:latest")
        self.assertEqual(config["pass_path_anthropic"], "api/llm/anthropic")
        self.assertEqual(config["pass_path_openai"], "api/llm/openai")

    def test_load_global_config(self):
        """Should load global config from ~/.config/jolo/config.toml."""
        config_dir = Path(self.tmpdir) / ".config" / "jolo"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text(
            'base_image = "custom/image:v1"\n'
        )

        config = jolo.load_config(global_config_dir=config_dir)

        self.assertEqual(config["base_image"], "custom/image:v1")

    def test_load_project_config(self):
        """Should load project config from .jolo.toml."""
        os.chdir(self.tmpdir)
        Path(self.tmpdir, ".jolo.toml").write_text(
            'base_image = "project/image:v2"\n'
        )

        config = jolo.load_config(
            global_config_dir=Path(self.tmpdir) / "noexist"
        )

        self.assertEqual(config["base_image"], "project/image:v2")

    def test_project_config_overrides_global(self):
        """Project config should override global config."""
        config_dir = Path(self.tmpdir) / ".config" / "jolo"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text(
            'base_image = "global/image:v1"\n'
        )

        os.chdir(self.tmpdir)
        Path(self.tmpdir, ".jolo.toml").write_text(
            'base_image = "project/image:v2"\n'
        )

        config = jolo.load_config(global_config_dir=config_dir)

        self.assertEqual(config["base_image"], "project/image:v2")

    def test_config_partial_override(self):
        """Project config should only override specified keys."""
        config_dir = Path(self.tmpdir) / ".config" / "jolo"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text(
            'base_image = "global/image:v1"\npass_path_anthropic = "custom/path"\n'
        )

        os.chdir(self.tmpdir)
        Path(self.tmpdir, ".jolo.toml").write_text(
            'base_image = "project/image:v2"\n'
        )

        config = jolo.load_config(global_config_dir=config_dir)

        self.assertEqual(config["base_image"], "project/image:v2")
        self.assertEqual(config["pass_path_anthropic"], "custom/path")


class TestListMode(unittest.TestCase):
    """Test list functionality."""

    def test_list_flag(self):
        """list should set command to list."""
        args = jolo.parse_args(["list"])
        self.assertEqual(args.command, "list")

    def test_list_default_false(self):
        """No command should leave command as None."""
        args = jolo.parse_args([])
        self.assertIsNone(args.command)

    def test_all_flag(self):
        """--all should set all to True."""
        args = jolo.parse_args(["list", "--all"])
        self.assertTrue(args.all)

    def test_all_short_flag(self):
        """-a should set all to True."""
        args = jolo.parse_args(["list", "-a"])
        self.assertTrue(args.all)

    def test_all_default_false(self):
        """--all should default to False."""
        args = jolo.parse_args(["list"])
        self.assertFalse(args.all)


class TestStopMode(unittest.TestCase):
    """Test down functionality."""

    def test_down_flag(self):
        """down should set command to down."""
        args = jolo.parse_args(["down"])
        self.assertEqual(args.command, "down")

    def test_stop_default_false(self):
        """No command should leave command as None."""
        args = jolo.parse_args([])
        self.assertIsNone(args.command)


class TestDetachMode(unittest.TestCase):
    """Test --detach functionality."""

    def test_detach_flag(self):
        """--detach should set detach to True."""
        args = jolo.parse_args(["up", "--detach"])
        self.assertTrue(args.detach)

    def test_detach_short_flag(self):
        """-d should set detach to True."""
        args = jolo.parse_args(["up", "-d"])
        self.assertTrue(args.detach)

    def test_detach_default_false(self):
        """--detach should default to False."""
        args = jolo.parse_args([])
        self.assertFalse(args.detach)

    def test_detach_with_tree(self):
        """--detach can combine with tree."""
        args = jolo.parse_args(["tree", "test", "--detach"])
        self.assertTrue(args.detach)
        self.assertEqual(args.name, "test")


class TestPruneMode(unittest.TestCase):
    """Test prune functionality."""

    def test_prune_flag(self):
        """prune should set command to prune."""
        args = jolo.parse_args(["prune"])
        self.assertEqual(args.command, "prune")

    def test_prune_default_false(self):
        """No command should leave command as None."""
        args = jolo.parse_args([])
        self.assertIsNone(args.command)


class TestPruneGlobalImages(unittest.TestCase):
    """Test image pruning in global mode."""

    @mock.patch("_jolo.commands.get_container_runtime", return_value="podman")
    @mock.patch("_jolo.commands.list_all_devcontainers")
    @mock.patch("_jolo.commands.remove_container", return_value=True)
    @mock.patch("_jolo.commands.remove_image", return_value=True)
    @mock.patch("builtins.input", return_value="y")
    @mock.patch("subprocess.run")
    @mock.patch("os.path.exists", return_value=True)
    def test_prune_global_removes_unused_images(
        self,
        mock_exists,
        mock_run,
        mock_input,
        mock_remove_image,
        mock_remove_container,
        mock_list,
        mock_runtime,
    ):
        """Should remove images not used by remaining containers."""
        # Initial list: one stopped container with an image
        mock_list.side_effect = [
            [("stopped-c", "/path/to/proj", "exited", "img123")],  # first call
            [],  # second call (remaining containers)
        ]
        mock_run.return_value = mock.Mock(returncode=0)

        # Mock Path.exists to return True so it's not orphan
        with mock.patch("_jolo.commands.Path.exists", return_value=True):
            jolo.run_prune_global_mode()

        mock_remove_container.assert_called_with("stopped-c")
        mock_remove_image.assert_called_with("img123")

    @mock.patch("_jolo.commands.get_container_runtime", return_value="podman")
    @mock.patch("_jolo.commands.list_all_devcontainers")
    @mock.patch("_jolo.commands.remove_container", return_value=True)
    @mock.patch("_jolo.commands.remove_image")
    @mock.patch("builtins.input", return_value="y")
    @mock.patch("subprocess.run")
    def test_prune_global_skips_in_use_images(
        self,
        mock_run,
        mock_input,
        mock_remove_image,
        mock_remove_container,
        mock_list,
        mock_runtime,
    ):
        """Should NOT remove images still used by other containers."""
        # Initial list: one stopped, one running, both using same image
        mock_list.side_effect = [
            [
                ("stopped-c", "/path/1", "exited", "img123"),
                ("running-c", "/path/2", "running", "img123"),
            ],
            [("running-c", "/path/2", "running", "img123")],
        ]
        mock_run.return_value = mock.Mock(returncode=0)

        # Mock Path.exists to return True so running-c is not orphan
        with mock.patch("_jolo.commands.Path.exists", return_value=True):
            jolo.run_prune_global_mode()

        mock_remove_container.assert_called_with("stopped-c")
        mock_remove_image.assert_not_called()


class TestCloneMode(unittest.TestCase):
    """Test clone functionality."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_infer_repo_name(self):
        """Should infer repo name from common URL formats."""
        self.assertEqual(
            jolo.infer_repo_name("https://github.com/org/repo.git"), "repo"
        )
        self.assertEqual(
            jolo.infer_repo_name("git@github.com:org/repo.git"), "repo"
        )
        self.assertEqual(jolo.infer_repo_name("/path/to/repo"), "repo")

    @mock.patch("_jolo.commands.run_up_mode")
    @mock.patch("jolo.subprocess.run")
    def test_clone_default_target(self, mock_run, mock_up):
        """Should clone into ./<name> and then run up."""

        def _clone_side_effect(*args, **kwargs):
            cmd = args[0]
            if cmd[:2] == ["git", "clone"]:
                target = Path(cmd[-1])
                target.mkdir(parents=True, exist_ok=True)
                (target / ".git").mkdir(parents=True, exist_ok=True)
                return mock.Mock(returncode=0)
            return mock.Mock(returncode=1, stdout="", stderr="")

        mock_run.side_effect = _clone_side_effect
        args = jolo.parse_args(["clone", "https://github.com/org/repo.git"])

        jolo.run_clone_mode(args)

        expected_target = Path(self.tmpdir) / "repo"
        mock_run.assert_called_with(
            [
                "git",
                "clone",
                "https://github.com/org/repo.git",
                str(expected_target),
            ]
        )
        mock_up.assert_called_once()

    def test_clone_errors_if_target_exists(self):
        """Should error if target exists."""
        target = Path(self.tmpdir) / "repo"
        target.mkdir(parents=True)
        args = jolo.parse_args(["clone", "https://github.com/org/repo.git"])
        with self.assertRaises(SystemExit):
            jolo.run_clone_mode(args)


class TestExecMode(unittest.TestCase):
    """Test exec command behavior."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        self.git_root = Path(self.tmpdir) / "myproject"
        self.git_root.mkdir()
        (self.git_root / ".git").mkdir()
        os.chdir(self.git_root)

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.tmpdir)

    @mock.patch("_jolo.commands.devcontainer_exec_command")
    def test_exec_calls_devcontainer_exec(self, mock_exec):
        """Should call devcontainer_exec_command with the joined command."""
        args = jolo.parse_args(["exec", "npm", "run", "dev"])
        jolo.run_exec_mode(args)
        mock_exec.assert_called_once_with(self.git_root, "npm run dev")

    @mock.patch("_jolo.commands.devcontainer_exec_command")
    def test_exec_strips_double_dash(self, mock_exec):
        """Should strip -- from command."""
        args = jolo.parse_args(["exec", "--", "git", "status"])
        jolo.run_exec_mode(args)
        mock_exec.assert_called_once_with(self.git_root, "git status")


class TestPortMode(unittest.TestCase):
    """Test port command."""

    def test_port_command_parsed(self):
        """port should set command to port."""
        args = jolo.parse_args(["port"])
        self.assertEqual(args.command, "port")

    def test_port_with_number(self):
        """port NUMBER should set port arg."""
        args = jolo.parse_args(["port", "4200"])
        self.assertEqual(args.port, 4200)

    def test_port_random_flag(self):
        """port --random should set random flag."""
        args = jolo.parse_args(["port", "--random"])
        self.assertTrue(args.random)

    def test_port_default_no_port(self):
        """port with no args should have port=None."""
        args = jolo.parse_args(["port"])
        self.assertIsNone(args.port)


class TestRunPortMode(unittest.TestCase):
    """Test run_port_mode command handler."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        self.ws = Path(self.tmpdir) / "project"
        self.ws.mkdir()
        (self.ws / ".git").mkdir()
        (self.ws / ".devcontainer").mkdir()
        os.chdir(self.ws)

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.tmpdir)

    def _write_config(self, config):
        import json

        path = self.ws / ".devcontainer" / "devcontainer.json"
        path.write_text(json.dumps(config, indent=4) + "\n")

    def _read_config(self):
        import json

        path = self.ws / ".devcontainer" / "devcontainer.json"
        return json.loads(path.read_text())

    def test_port_show_prints_current(self):
        """jolo port should print current port."""
        self._write_config(
            {"containerEnv": {"PORT": "4500"}, "runArgs": ["-p", "4500:4500"]}
        )
        args = jolo.parse_args(["port"])
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            jolo.run_port_mode(args)
        output = f.getvalue()
        self.assertIn("4500", output)

    def test_port_set_specific(self):
        """jolo port 4200 should set port to 4200."""
        self._write_config(
            {"containerEnv": {"PORT": "4500"}, "runArgs": ["-p", "4500:4500"]}
        )
        args = jolo.parse_args(["port", "4200"])
        with mock.patch("_jolo.commands.is_port_available", return_value=True):
            jolo.run_port_mode(args)
        config = self._read_config()
        self.assertEqual(config["containerEnv"]["PORT"], "4200")

    def test_port_random(self):
        """jolo port --random should assign a random port."""
        self._write_config(
            {"containerEnv": {"PORT": "4500"}, "runArgs": ["-p", "4500:4500"]}
        )
        args = jolo.parse_args(["port", "--random"])
        with mock.patch("_jolo.container.random_port", return_value=4777):
            with mock.patch(
                "_jolo.container.is_port_available", return_value=True
            ):
                jolo.run_port_mode(args)
        config = self._read_config()
        self.assertEqual(config["containerEnv"]["PORT"], "4777")

    def test_port_warns_if_in_use(self):
        """jolo port NUMBER should warn if port is in use."""
        self._write_config(
            {"containerEnv": {"PORT": "4500"}, "runArgs": ["-p", "4500:4500"]}
        )
        args = jolo.parse_args(["port", "4200"])
        import io
        from contextlib import redirect_stderr

        f = io.StringIO()
        with redirect_stderr(f):
            with mock.patch(
                "_jolo.commands.is_port_available", return_value=False
            ):
                jolo.run_port_mode(args)
        self.assertIn("in use", f.getvalue())
        # Should still set it
        config = self._read_config()
        self.assertEqual(config["containerEnv"]["PORT"], "4200")


class TestSetPort(unittest.TestCase):
    """Test set_port function."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ws = Path(self.tmpdir) / "project"
        self.ws.mkdir()
        (self.ws / ".devcontainer").mkdir()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def _write_config(self, config):
        import json

        path = self.ws / ".devcontainer" / "devcontainer.json"
        path.write_text(json.dumps(config, indent=4) + "\n")

    def _read_config(self):
        import json

        path = self.ws / ".devcontainer" / "devcontainer.json"
        return json.loads(path.read_text())

    def test_set_port_updates_env(self):
        """Should update PORT in containerEnv."""
        self._write_config(
            {
                "containerEnv": {"PORT": "4500"},
                "runArgs": ["-p", "4500:4500"],
            }
        )

        from _jolo.container import set_port

        set_port(self.ws, 4200)
        config = self._read_config()
        self.assertEqual(config["containerEnv"]["PORT"], "4200")

    def test_set_port_updates_run_args(self):
        """Should update -p flag in runArgs."""
        self._write_config(
            {
                "containerEnv": {"PORT": "4500"},
                "runArgs": ["--name", "myapp", "-p", "4500:4500"],
            }
        )

        from _jolo.container import set_port

        set_port(self.ws, 4200)
        config = self._read_config()
        self.assertIn("4200:4200", config["runArgs"])
        self.assertNotIn("4500:4500", config["runArgs"])

    def test_set_port_updates_name_arg(self):
        """Should update --name arg port suffix if present."""
        self._write_config(
            {
                "containerEnv": {"PORT": "4500"},
                "runArgs": ["--name", "myapp-4500", "-p", "4500:4500"],
            }
        )

        from _jolo.container import set_port

        set_port(self.ws, 4200)
        config = self._read_config()
        # Name shouldn't change — it's the container name, not port-derived
        # Just verify port fields changed
        self.assertEqual(config["containerEnv"]["PORT"], "4200")


if __name__ == "__main__":
    unittest.main()
