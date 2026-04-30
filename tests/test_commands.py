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

    def test_notify_threshold_override(self):
        """Project .jolo.toml should override notify_threshold."""
        os.chdir(self.tmpdir)
        Path(self.tmpdir, ".jolo.toml").write_text("notify_threshold = 20\n")

        config = jolo.load_config(
            global_config_dir=Path(self.tmpdir) / "noexist"
        )

        self.assertEqual(config["notify_threshold"], 20)


class TestPodmanAllowance(unittest.TestCase):
    """allow_podman creates the gate dir and starts socat. deny stops
    socat but keeps the gate dir so the bind-mount in devcontainer.json
    survives across recreates."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config_dir = Path(self.tmpdir)
        # Patch socat for the whole suite — these tests aren't about
        # whether socat works, they're about the gate-dir state machine.
        self._socat_patches = [
            mock.patch(
                "_jolo.cli._spawn_socat",
                return_value=mock.MagicMock(pid=12345),
            ),
            mock.patch("_jolo.cli._process_is_socat", return_value=True),
        ]
        for p in self._socat_patches:
            p.start()

    def tearDown(self):
        for p in self._socat_patches:
            p.stop()
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_disallowed_by_default(self):
        """Without an allow, the gate dir doesn't exist."""
        self.assertFalse(jolo.is_podman_allowed("foo", self.config_dir))

    def test_allow_creates_gate_dir(self):
        """allow_podman creates ~/.config/jolo/podman-runtime/<project>/."""
        path = jolo.allow_podman("foo", self.config_dir)
        self.assertTrue(path.is_dir())
        self.assertTrue(jolo.is_podman_allowed("foo", self.config_dir))
        self.assertEqual(path, self.config_dir / "podman-runtime" / "foo")

    def test_allow_is_idempotent(self):
        """Calling allow_podman twice doesn't error or restart socat."""
        jolo.allow_podman("foo", self.config_dir)
        jolo.allow_podman("foo", self.config_dir)
        self.assertTrue(jolo.is_podman_allowed("foo", self.config_dir))

    def test_deny_keeps_gate_dir(self):
        """deny_podman stops socat but leaves the gate dir intact, so the
        bind-mount in devcontainer.json survives across recreates and
        re-allowing later doesn't need another --recreate."""
        jolo.allow_podman("foo", self.config_dir)
        with mock.patch("os.kill"):
            self.assertTrue(jolo.deny_podman("foo", self.config_dir))
        # Gate dir persists.
        self.assertTrue(jolo.is_podman_allowed("foo", self.config_dir))
        # But proxy is gone.
        self.assertFalse(jolo.is_podman_proxy_running("foo", self.config_dir))

    def test_per_project_isolation(self):
        jolo.allow_podman("foo", self.config_dir)
        self.assertTrue(jolo.is_podman_allowed("foo", self.config_dir))
        self.assertFalse(jolo.is_podman_allowed("bar", self.config_dir))


class TestPodmanProxyLifecycle(unittest.TestCase):
    """socat-based proxy is what makes the cross-container access toggle
    instant: starting/stopping socat at the gate path is what flips
    the feature on/off for an already-running container."""

    def setUp(self):
        from _jolo.cli import (
            _podman_proxy_pidfile,
            _podman_proxy_socket,
            _podman_runtime_dir,
        )

        self._dir = _podman_runtime_dir
        self._sock = _podman_proxy_socket
        self._pidfile = _podman_proxy_pidfile
        self.tmpdir = tempfile.mkdtemp()
        self.config_dir = Path(self.tmpdir)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_paths_are_keyed_by_project(self):
        """Per-project gate dir contains the sentinel + socket + pidfile."""
        d = self._dir("foo", self.config_dir)
        self.assertEqual(d, self.config_dir / "podman-runtime" / "foo")
        self.assertEqual(self._sock("foo", self.config_dir), d / "podman.sock")
        self.assertEqual(
            self._pidfile("foo", self.config_dir), d / "socat.pid"
        )

    def test_is_running_false_when_no_pidfile(self):
        self.assertFalse(jolo.is_podman_proxy_running("foo", self.config_dir))

    def test_start_writes_pidfile_and_returns_pid(self):
        """start_podman_proxy spawns socat, writes its PID, returns it."""
        with (
            mock.patch("_jolo.cli._spawn_socat") as fake_spawn,
            mock.patch("_jolo.cli._process_is_socat", return_value=True),
        ):
            fake_proc = mock.MagicMock()
            fake_proc.pid = 12345
            fake_spawn.return_value = fake_proc

            pid = jolo.start_podman_proxy("foo", self.config_dir)

            self.assertEqual(pid, 12345)
            pidfile = self._pidfile("foo", self.config_dir)
            self.assertEqual(pidfile.read_text().strip(), "12345")

    def test_start_is_idempotent_when_already_running(self):
        """If a live socat already runs for this project, start returns its PID."""
        pidfile = self._pidfile("foo", self.config_dir)
        pidfile.parent.mkdir(parents=True, exist_ok=True)
        pidfile.write_text("99999\n")
        with (
            mock.patch("_jolo.cli._process_is_socat", return_value=True),
            mock.patch("_jolo.cli._spawn_socat") as fake_spawn,
        ):
            pid = jolo.start_podman_proxy("foo", self.config_dir)
            self.assertEqual(pid, 99999)
            fake_spawn.assert_not_called()

    def test_start_replaces_stale_pidfile(self):
        """A pidfile pointing at a dead/non-socat process is recreated."""
        pidfile = self._pidfile("foo", self.config_dir)
        pidfile.parent.mkdir(parents=True, exist_ok=True)
        pidfile.write_text("99999\n")
        with (
            mock.patch("_jolo.cli._process_is_socat", return_value=False),
            mock.patch("_jolo.cli._spawn_socat") as fake_spawn,
        ):
            fake_proc = mock.MagicMock()
            fake_proc.pid = 12345
            fake_spawn.return_value = fake_proc

            pid = jolo.start_podman_proxy("foo", self.config_dir)
            self.assertEqual(pid, 12345)
            self.assertEqual(pidfile.read_text().strip(), "12345")

    def test_stop_kills_pid_and_returns_true(self):
        pidfile = self._pidfile("foo", self.config_dir)
        pidfile.parent.mkdir(parents=True, exist_ok=True)
        pidfile.write_text("12345\n")
        with (
            mock.patch("_jolo.cli._process_is_socat", return_value=True),
            mock.patch("os.kill") as fake_kill,
        ):
            self.assertTrue(jolo.stop_podman_proxy("foo", self.config_dir))
            fake_kill.assert_called_once()
            self.assertFalse(pidfile.exists())

    def test_stop_returns_false_when_not_running(self):
        self.assertFalse(jolo.stop_podman_proxy("foo", self.config_dir))

    def test_pid_with_wrong_listen_path_is_treated_as_dead(self):
        """If a recycled PID happens to be running socat for a different
        project, our project's start/stop/is_running must not treat it
        as ours."""
        pidfile = self._pidfile("foo", self.config_dir)
        pidfile.parent.mkdir(parents=True, exist_ok=True)
        pidfile.write_text("99999\n")
        # Simulate: PID is socat, but listening on a different path.
        with (
            mock.patch("_jolo.cli._process_is_socat", return_value=False),
            mock.patch("_jolo.cli._spawn_socat") as fake_spawn,
        ):
            fake_spawn.return_value = mock.MagicMock(pid=12345)
            pid = jolo.start_podman_proxy("foo", self.config_dir)
            # Treated as dead → spawned a fresh one.
            self.assertEqual(pid, 12345)
            fake_spawn.assert_called_once()


class TestPodmanAllowRollback(unittest.TestCase):
    """First allow on a project must roll back the gate dir if socat
    fails to start, so the next attempt gets the first-time UX
    (including the `jolo up --recreate` hint)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config_dir = Path(self.tmpdir)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_first_allow_rolls_back_on_socat_failure(self):
        from _jolo.cli import _podman_runtime_dir

        with mock.patch(
            "_jolo.cli._spawn_socat",
            side_effect=RuntimeError("socat missing"),
        ):
            with self.assertRaises(RuntimeError):
                jolo.allow_podman("foo", self.config_dir)
        self.assertFalse(_podman_runtime_dir("foo", self.config_dir).exists())

    def test_subsequent_allow_does_not_roll_back_on_failure(self):
        """A failure on a re-allow must NOT remove the existing gate
        dir — it was already retrofitted in devcontainer.json and the
        user shouldn't have to recreate just because socat happened
        to be down at the moment of re-allow."""
        from _jolo.cli import _podman_runtime_dir

        # First successful allow.
        with (
            mock.patch(
                "_jolo.cli._spawn_socat", return_value=mock.MagicMock(pid=1)
            ),
            mock.patch("_jolo.cli._process_is_socat", return_value=True),
        ):
            jolo.allow_podman("foo", self.config_dir)
        gate = _podman_runtime_dir("foo", self.config_dir)
        self.assertTrue(gate.is_dir())

        # Second allow with socat broken.
        with (
            mock.patch(
                "_jolo.cli._spawn_socat",
                side_effect=RuntimeError("socat missing"),
            ),
            mock.patch("_jolo.cli._process_is_socat", return_value=False),
        ):
            with self.assertRaises(RuntimeError):
                jolo.allow_podman("foo", self.config_dir)
        # Gate dir survives.
        self.assertTrue(gate.is_dir())


class TestPodmanWiring(unittest.TestCase):
    """`_sync_config` must propagate is_podman_allowed(name) into
    sync_devcontainer's cross_container kwarg. A regression here
    would silently disable the feature for --recreate flows."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project_path = Path(self.tmpdir) / "myproj"
        self.project_path.mkdir()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def _run_with_allowed(self, allowed: bool):
        with (
            mock.patch(
                "_jolo.commands.is_podman_allowed", return_value=allowed
            ),
            mock.patch("_jolo.commands.sync_devcontainer") as fake_sync,
            mock.patch("_jolo.commands.sync_skill_templates"),
            mock.patch("_jolo.commands.sync_template_files"),
        ):
            from _jolo import commands

            commands._sync_config(
                "myproj", self.project_path, {"base_image": "x"}
            )
            return fake_sync

    def test_sync_passes_cross_container_true_when_allowed(self):
        fake = self._run_with_allowed(True)
        kwargs = fake.call_args.kwargs
        self.assertTrue(kwargs.get("cross_container"))

    def test_sync_passes_cross_container_false_when_not_allowed(self):
        fake = self._run_with_allowed(False)
        kwargs = fake.call_args.kwargs
        self.assertFalse(kwargs.get("cross_container"))


class TestAllowDenySubcommands(unittest.TestCase):
    """`jolo allow podman <project>` and `jolo deny podman <project>` parse
    correctly and end up calling allow_podman/deny_podman."""

    def test_allow_command_parses(self):
        args = jolo.parse_args(["allow", "podman", "myproject"])
        self.assertEqual(args.command, "allow")
        self.assertEqual(args.feature, "podman")
        self.assertEqual(args.project, "myproject")

    def test_deny_command_parses(self):
        args = jolo.parse_args(["deny", "podman", "myproject"])
        self.assertEqual(args.command, "deny")
        self.assertEqual(args.feature, "podman")
        self.assertEqual(args.project, "myproject")

    def test_allow_requires_project(self):
        """Project name must be explicit — no auto-infer, prevents accidental misuse."""
        with self.assertRaises(SystemExit):
            jolo.parse_args(["allow", "podman"])

    def test_allow_rejects_unknown_feature(self):
        with self.assertRaises(SystemExit):
            jolo.parse_args(["allow", "wat", "myproject"])


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
        args = jolo.parse_args(["exec", "pnpm", "run", "dev"])
        jolo.run_exec_mode(args)
        mock_exec.assert_called_once_with(self.git_root, "pnpm run dev")

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

    def test_port_rejects_invalid_range(self):
        """jolo port 70000 should error."""
        self._write_config(
            {"containerEnv": {"PORT": "4500"}, "runArgs": ["-p", "4500:4500"]}
        )
        args = jolo.parse_args(["port", "70000"])
        with self.assertRaises(SystemExit):
            jolo.run_port_mode(args)

    def test_port_rejects_random_with_number(self):
        """jolo port 4200 --random should error."""
        self._write_config(
            {"containerEnv": {"PORT": "4500"}, "runArgs": ["-p", "4500:4500"]}
        )
        args = jolo.parse_args(["port", "4200", "--random"])
        with self.assertRaises(SystemExit):
            jolo.run_port_mode(args)

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

    def test_set_port_errors_without_devcontainer(self):
        """Should exit if devcontainer.json doesn't exist."""
        ws = Path(self.tmpdir) / "empty"
        ws.mkdir()
        (ws / ".devcontainer").mkdir()

        from _jolo.container import set_port

        with self.assertRaises(SystemExit):
            set_port(ws, 4200)

    def test_set_port_creates_container_env_if_missing(self):
        """Should create containerEnv if not present."""
        self._write_config({"runArgs": ["-p", "4500:4500"]})

        from _jolo.container import set_port

        set_port(self.ws, 4200)
        config = self._read_config()
        self.assertEqual(config["containerEnv"]["PORT"], "4200")

    def test_set_port_leaves_other_args_unchanged(self):
        """Should only update PORT and -p flag, not other runArgs."""
        self._write_config(
            {
                "containerEnv": {"PORT": "4500"},
                "runArgs": ["--name", "myapp", "-p", "4500:4500"],
            }
        )

        from _jolo.container import set_port

        set_port(self.ws, 4200)
        config = self._read_config()
        self.assertEqual(config["containerEnv"]["PORT"], "4200")
        self.assertIn("--name", config["runArgs"])
        self.assertIn("myapp", config["runArgs"])


class TestFmtSize(unittest.TestCase):
    """Test _fmt_size helper."""

    def test_bytes(self):
        from _jolo.commands import _fmt_size

        self.assertEqual(_fmt_size(0), "0 B")
        self.assertEqual(_fmt_size(512), "512 B")

    def test_kilobytes(self):
        from _jolo.commands import _fmt_size

        self.assertEqual(_fmt_size(1024), "1.0 KB")
        self.assertEqual(_fmt_size(1536), "1.5 KB")

    def test_megabytes(self):
        from _jolo.commands import _fmt_size

        self.assertEqual(_fmt_size(1024 * 1024), "1.0 MB")

    def test_gigabytes(self):
        from _jolo.commands import _fmt_size

        self.assertEqual(_fmt_size(1024**3), "1.0 GB")


class TestDoctorMode(unittest.TestCase):
    """Test jolo doctor command."""

    @mock.patch("_jolo.commands.get_container_runtime", return_value="podman")
    @mock.patch("_jolo.commands.find_git_root", return_value=None)
    @mock.patch("_jolo.commands.list_all_devcontainers", return_value=[])
    @mock.patch("subprocess.run")
    def test_doctor_exits_nonzero_on_failures(
        self, mock_run, mock_list, mock_git, mock_runtime
    ):
        """Doctor should exit 1 when checks fail."""
        mock_run.return_value = mock.Mock(returncode=0)
        with mock.patch.dict(os.environ, {}, clear=True):
            args = jolo.parse_args(["doctor"])
            with self.assertRaises(SystemExit) as cm:
                jolo.run_doctor_mode(args)
            self.assertEqual(cm.exception.code, 1)


class TestPickProject(unittest.TestCase):
    """Test pick_project() — resolve project or fzf-pick."""

    @mock.patch("_jolo.commands.find_git_root")
    def test_returns_git_root_when_in_repo(self, mock_fgr):
        """Should return git root directly when inside a repo."""
        mock_fgr.return_value = Path("/home/user/myproject")
        result = jolo.pick_project()
        self.assertEqual(result, Path("/home/user/myproject"))

    @mock.patch("_jolo.commands.find_git_root", return_value=None)
    @mock.patch("_jolo.commands.list_all_devcontainers")
    def test_exits_when_no_containers(self, mock_list, mock_fgr):
        """Should exit when not in a repo and no containers running."""
        mock_list.return_value = []
        with self.assertRaises(SystemExit):
            jolo.pick_project()

    @mock.patch("_jolo.commands.find_git_root", return_value=None)
    @mock.patch("_jolo.commands.list_all_devcontainers")
    def test_auto_selects_single_container(self, mock_list, mock_fgr):
        """Should auto-select when only one running container."""
        mock_list.return_value = [
            ("myapp", "/home/user/myapp", "running", "img1"),
        ]
        with mock.patch.object(Path, "exists", return_value=True):
            result = jolo.pick_project()
        self.assertEqual(result, Path("/home/user/myapp"))


if __name__ == "__main__":
    unittest.main()
