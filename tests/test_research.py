#!/usr/bin/env python3
"""Tests for jolo research command."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import jolo
except ImportError:
    jolo = None


class TestResearchArgParsing(unittest.TestCase):
    """Test CLI argument parsing for research subcommand."""

    def test_research_command(self):
        args = jolo.parse_args(["research", "my topic"])
        self.assertEqual(args.command, "research")
        self.assertEqual(args.prompt, "my topic")

    def test_research_requires_prompt(self):
        with self.assertRaises(SystemExit):
            jolo.parse_args(["research"])

    def test_research_agent_default(self):
        args = jolo.parse_args(["research", "topic"])
        self.assertIsNone(args.agent)

    def test_research_agent_override(self):
        args = jolo.parse_args(["research", "--agent", "gemini", "topic"])
        self.assertEqual(args.agent, "gemini")

    def test_research_topic_default(self):
        args = jolo.parse_args(["research", "topic"])
        self.assertIsNone(args.topic)

    def test_research_topic_override(self):
        args = jolo.parse_args(["research", "--topic", "test-topic", "topic"])
        self.assertEqual(args.topic, "test-topic")

    def test_research_verbose_flag(self):
        args = jolo.parse_args(["research", "-v", "topic"])
        self.assertTrue(args.verbose)

    def test_research_all_flags(self):
        args = jolo.parse_args(
            [
                "research",
                "--agent",
                "claude",
                "--topic",
                "mytopic",
                "-v",
                "research question here",
            ]
        )
        self.assertEqual(args.command, "research")
        self.assertEqual(args.prompt, "research question here")
        self.assertEqual(args.agent, "claude")
        self.assertEqual(args.topic, "mytopic")
        self.assertTrue(args.verbose)


class TestResearchMode(unittest.TestCase):
    """Test run_research_mode logic."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        self.git_root = Path(self.tmpdir) / "project"
        self.git_root.mkdir()
        (self.git_root / ".git").mkdir()
        os.chdir(self.git_root)

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.tmpdir)

    @mock.patch("_jolo.commands._spawn_research_watcher")
    @mock.patch("_jolo.commands.devcontainer_up", return_value=True)
    @mock.patch("_jolo.commands.setup_stash")
    @mock.patch("_jolo.commands.setup_emacs_config")
    @mock.patch("_jolo.commands.setup_notification_hooks")
    @mock.patch("_jolo.commands.setup_credential_cache")
    @mock.patch("_jolo.commands.get_secrets", return_value={})
    @mock.patch("_jolo.commands.get_or_create_worktree")
    @mock.patch("_jolo.commands.load_config")
    def test_research_creates_worktree_with_prefix(
        self,
        mock_config,
        mock_worktree,
        mock_secrets,
        mock_creds,
        mock_notify,
        mock_emacs,
        mock_stash,
        mock_up,
        mock_watcher,
    ):
        mock_config.return_value = {
            "agents": ["claude", "gemini"],
            "agent_commands": {"claude": "claude", "gemini": "gemini"},
        }
        wt_path = self.git_root / "wt"
        wt_path.mkdir()
        (wt_path / ".devcontainer").mkdir()
        mock_worktree.return_value = wt_path

        args = jolo.parse_args(["research", "test topic"])
        jolo.run_research_mode(args)

        # Worktree name starts with "research-"
        call_args = mock_worktree.call_args
        wt_name = call_args[0][1]
        self.assertTrue(wt_name.startswith("research-"))

    @mock.patch("_jolo.commands._spawn_research_watcher")
    @mock.patch("_jolo.commands.devcontainer_up", return_value=True)
    @mock.patch("_jolo.commands.setup_stash")
    @mock.patch("_jolo.commands.setup_emacs_config")
    @mock.patch("_jolo.commands.setup_notification_hooks")
    @mock.patch("_jolo.commands.setup_credential_cache")
    @mock.patch("_jolo.commands.get_secrets", return_value={})
    @mock.patch("_jolo.commands.get_or_create_worktree")
    @mock.patch("_jolo.commands.load_config")
    def test_research_writes_prompt_file(
        self,
        mock_config,
        mock_worktree,
        mock_secrets,
        mock_creds,
        mock_notify,
        mock_emacs,
        mock_stash,
        mock_up,
        mock_watcher,
    ):
        mock_config.return_value = {
            "agents": ["claude"],
            "agent_commands": {"claude": "claude"},
        }
        wt_path = self.git_root / "wt"
        wt_path.mkdir()
        (wt_path / ".devcontainer").mkdir()
        mock_worktree.return_value = wt_path

        args = jolo.parse_args(["research", "container security"])
        jolo.run_research_mode(args)

        prompt_file = wt_path / ".devcontainer" / ".agent-prompt"
        self.assertTrue(prompt_file.exists())
        self.assertEqual(
            prompt_file.read_text(), "/research container security"
        )

    @mock.patch("_jolo.commands._spawn_research_watcher")
    @mock.patch("_jolo.commands.devcontainer_up", return_value=True)
    @mock.patch("_jolo.commands.setup_stash")
    @mock.patch("_jolo.commands.setup_emacs_config")
    @mock.patch("_jolo.commands.setup_notification_hooks")
    @mock.patch("_jolo.commands.setup_credential_cache")
    @mock.patch("_jolo.commands.get_secrets", return_value={})
    @mock.patch("_jolo.commands.get_or_create_worktree")
    @mock.patch("_jolo.commands.load_config")
    def test_research_writes_research_mode_flag(
        self,
        mock_config,
        mock_worktree,
        mock_secrets,
        mock_creds,
        mock_notify,
        mock_emacs,
        mock_stash,
        mock_up,
        mock_watcher,
    ):
        mock_config.return_value = {
            "agents": ["claude"],
            "agent_commands": {"claude": "claude"},
        }
        wt_path = self.git_root / "wt"
        wt_path.mkdir()
        (wt_path / ".devcontainer").mkdir()
        mock_worktree.return_value = wt_path

        args = jolo.parse_args(["research", "topic"])
        jolo.run_research_mode(args)

        flag = wt_path / ".devcontainer" / ".research-mode"
        self.assertTrue(flag.exists())

    @mock.patch("_jolo.commands._spawn_research_watcher")
    @mock.patch("_jolo.commands.devcontainer_up", return_value=True)
    @mock.patch("_jolo.commands.setup_stash")
    @mock.patch("_jolo.commands.setup_emacs_config")
    @mock.patch("_jolo.commands.setup_notification_hooks")
    @mock.patch("_jolo.commands.setup_credential_cache")
    @mock.patch("_jolo.commands.get_secrets", return_value={})
    @mock.patch("_jolo.commands.get_or_create_worktree")
    @mock.patch("_jolo.commands.load_config")
    def test_research_spawns_watcher(
        self,
        mock_config,
        mock_worktree,
        mock_secrets,
        mock_creds,
        mock_notify,
        mock_emacs,
        mock_stash,
        mock_up,
        mock_watcher,
    ):
        mock_config.return_value = {
            "agents": ["claude"],
            "agent_commands": {"claude": "claude"},
        }
        wt_path = self.git_root / "wt"
        wt_path.mkdir()
        (wt_path / ".devcontainer").mkdir()
        mock_worktree.return_value = wt_path

        args = jolo.parse_args(["research", "topic"])
        jolo.run_research_mode(args)

        mock_watcher.assert_called_once()
        call_args = mock_watcher.call_args[0]
        self.assertEqual(call_args[0], wt_path)
        self.assertEqual(call_args[1], self.git_root)

    @mock.patch("_jolo.commands._spawn_research_watcher")
    @mock.patch("_jolo.commands.devcontainer_up", return_value=True)
    @mock.patch("_jolo.commands.setup_stash")
    @mock.patch("_jolo.commands.setup_emacs_config")
    @mock.patch("_jolo.commands.setup_notification_hooks")
    @mock.patch("_jolo.commands.setup_credential_cache")
    @mock.patch("_jolo.commands.get_secrets", return_value={})
    @mock.patch("_jolo.commands.get_or_create_worktree")
    @mock.patch("_jolo.commands.load_config")
    def test_research_overrides_ntfy_topic(
        self,
        mock_config,
        mock_worktree,
        mock_secrets,
        mock_creds,
        mock_notify,
        mock_emacs,
        mock_stash,
        mock_up,
        mock_watcher,
    ):
        mock_config.return_value = {
            "agents": ["claude"],
            "agent_commands": {"claude": "claude"},
        }
        wt_path = self.git_root / "wt"
        wt_path.mkdir()
        devcontainer_dir = wt_path / ".devcontainer"
        devcontainer_dir.mkdir()
        devcontainer_json = devcontainer_dir / "devcontainer.json"
        devcontainer_json.write_text(
            json.dumps({"containerEnv": {"NTFY_TOPIC": "jolo"}})
        )
        mock_worktree.return_value = wt_path

        args = jolo.parse_args(
            ["research", "--topic", "custom-topic", "topic"]
        )
        jolo.run_research_mode(args)

        content = json.loads(devcontainer_json.read_text())
        self.assertEqual(content["containerEnv"]["NTFY_TOPIC"], "custom-topic")

    @mock.patch("_jolo.commands._spawn_research_watcher")
    @mock.patch("_jolo.commands.devcontainer_up", return_value=True)
    @mock.patch("_jolo.commands.setup_stash")
    @mock.patch("_jolo.commands.setup_emacs_config")
    @mock.patch("_jolo.commands.setup_notification_hooks")
    @mock.patch("_jolo.commands.setup_credential_cache")
    @mock.patch("_jolo.commands.get_secrets", return_value={})
    @mock.patch("_jolo.commands.get_or_create_worktree")
    @mock.patch("_jolo.commands.load_config")
    def test_research_uses_explicit_agent(
        self,
        mock_config,
        mock_worktree,
        mock_secrets,
        mock_creds,
        mock_notify,
        mock_emacs,
        mock_stash,
        mock_up,
        mock_watcher,
    ):
        mock_config.return_value = {
            "agents": ["claude", "gemini", "codex"],
            "agent_commands": {
                "claude": "claude",
                "gemini": "gemini",
                "codex": "codex",
            },
        }
        wt_path = self.git_root / "wt"
        wt_path.mkdir()
        (wt_path / ".devcontainer").mkdir()
        mock_worktree.return_value = wt_path

        args = jolo.parse_args(["research", "--agent", "gemini", "topic"])
        jolo.run_research_mode(args)

        # Agent name file should be "gemini"
        agent_file = wt_path / ".devcontainer" / ".agent-name"
        self.assertEqual(agent_file.read_text(), "gemini")

    @mock.patch("_jolo.commands._spawn_research_watcher")
    @mock.patch("_jolo.commands.devcontainer_up", return_value=True)
    @mock.patch("_jolo.commands.setup_stash")
    @mock.patch("_jolo.commands.setup_emacs_config")
    @mock.patch("_jolo.commands.setup_notification_hooks")
    @mock.patch("_jolo.commands.setup_credential_cache")
    @mock.patch("_jolo.commands.get_secrets", return_value={})
    @mock.patch("_jolo.commands.get_or_create_worktree")
    @mock.patch("_jolo.commands.load_config")
    def test_research_empty_agents_falls_back_to_claude(
        self,
        mock_config,
        mock_worktree,
        mock_secrets,
        mock_creds,
        mock_notify,
        mock_emacs,
        mock_stash,
        mock_up,
        mock_watcher,
    ):
        mock_config.return_value = {
            "agents": [],
            "agent_commands": {},
        }
        wt_path = self.git_root / "wt"
        wt_path.mkdir()
        (wt_path / ".devcontainer").mkdir()
        mock_worktree.return_value = wt_path

        args = jolo.parse_args(["research", "topic"])
        jolo.run_research_mode(args)

        agent_file = wt_path / ".devcontainer" / ".agent-name"
        self.assertEqual(agent_file.read_text(), "claude")

    @mock.patch("_jolo.commands._spawn_research_watcher")
    @mock.patch("_jolo.commands.devcontainer_up", return_value=False)
    @mock.patch("_jolo.commands.setup_stash")
    @mock.patch("_jolo.commands.setup_emacs_config")
    @mock.patch("_jolo.commands.setup_notification_hooks")
    @mock.patch("_jolo.commands.setup_credential_cache")
    @mock.patch("_jolo.commands.get_secrets", return_value={})
    @mock.patch("_jolo.commands.get_or_create_worktree")
    @mock.patch("_jolo.commands.load_config")
    def test_research_exits_on_container_failure(
        self,
        mock_config,
        mock_worktree,
        mock_secrets,
        mock_creds,
        mock_notify,
        mock_emacs,
        mock_stash,
        mock_up,
        mock_watcher,
    ):
        mock_config.return_value = {
            "agents": ["claude"],
            "agent_commands": {"claude": "claude"},
        }
        wt_path = self.git_root / "wt"
        wt_path.mkdir()
        (wt_path / ".devcontainer").mkdir()
        mock_worktree.return_value = wt_path

        args = jolo.parse_args(["research", "topic"])
        with self.assertRaises(SystemExit):
            jolo.run_research_mode(args)

    @mock.patch("_jolo.commands.remove_worktree")
    @mock.patch("_jolo.commands._spawn_research_watcher")
    @mock.patch("_jolo.commands.devcontainer_up", return_value=False)
    @mock.patch("_jolo.commands.setup_stash")
    @mock.patch("_jolo.commands.setup_emacs_config")
    @mock.patch("_jolo.commands.setup_notification_hooks")
    @mock.patch("_jolo.commands.setup_credential_cache")
    @mock.patch("_jolo.commands.get_secrets", return_value={})
    @mock.patch("_jolo.commands.get_or_create_worktree")
    @mock.patch("_jolo.commands.load_config")
    def test_research_cleans_up_worktree_on_failure(
        self,
        mock_config,
        mock_worktree,
        mock_secrets,
        mock_creds,
        mock_notify,
        mock_emacs,
        mock_stash,
        mock_up,
        mock_watcher,
        mock_remove_wt,
    ):
        mock_config.return_value = {
            "agents": ["claude"],
            "agent_commands": {"claude": "claude"},
        }
        wt_path = self.git_root / "wt"
        wt_path.mkdir()
        (wt_path / ".devcontainer").mkdir()
        mock_worktree.return_value = wt_path

        args = jolo.parse_args(["research", "topic"])
        with self.assertRaises(SystemExit):
            jolo.run_research_mode(args)

        mock_remove_wt.assert_called_once_with(self.git_root, wt_path)


class TestResearchWatcher(unittest.TestCase):
    """Test _spawn_research_watcher."""

    @mock.patch("_jolo.commands.get_container_runtime", return_value="podman")
    @mock.patch("_jolo.commands.subprocess.Popen")
    def test_watcher_spawns_background_process(self, mock_popen, mock_runtime):
        from _jolo.commands import _spawn_research_watcher

        wt_path = Path("/tmp/fake-worktree")
        git_root = Path("/tmp/fake-root")

        _spawn_research_watcher(wt_path, git_root)

        mock_popen.assert_called_once()
        call_kwargs = mock_popen.call_args[1]
        self.assertTrue(call_kwargs["start_new_session"])

    @mock.patch("_jolo.commands.get_container_runtime", return_value="docker")
    @mock.patch("_jolo.commands.subprocess.Popen")
    def test_watcher_uses_correct_runtime(self, mock_popen, mock_runtime):
        from _jolo.commands import _spawn_research_watcher

        wt_path = Path("/tmp/fake-worktree")
        git_root = Path("/tmp/fake-root")

        _spawn_research_watcher(wt_path, git_root)

        # The script is passed as ["setsid", "sh", "-c", <script>]
        call_args = mock_popen.call_args[0][0]
        script = call_args[3]
        self.assertIn("docker", script)


if __name__ == "__main__":
    unittest.main()
