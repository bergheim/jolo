#!/usr/bin/env python3
"""Tests for filesystem & credential setup."""

import argparse
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _jolo.setup as setup
import jolo
from _jolo.commands import GITIGNORE_MARKER
from tests.cwd import tracked_tmpdir


class TestTemplateSystem(unittest.TestCase):
    """Test .devcontainer template scaffolding."""

    def setUp(self):
        self.tmpdir = tracked_tmpdir(self)

    def test_scaffold_devcontainer_creates_directory(self):
        """Should create .devcontainer directory."""
        os.chdir(self.tmpdir)
        jolo.scaffold_devcontainer("testproject")

        devcontainer_dir = Path(self.tmpdir) / ".devcontainer"
        self.assertTrue(devcontainer_dir.exists())
        self.assertTrue(devcontainer_dir.is_dir())

    def test_scaffold_devcontainer_creates_json(self):
        """Should create devcontainer.json with project name."""
        os.chdir(self.tmpdir)
        jolo.scaffold_devcontainer("testproject")

        json_file = Path(self.tmpdir) / ".devcontainer" / "devcontainer.json"
        self.assertTrue(json_file.exists())
        content = json_file.read_text()
        self.assertIn('"name": "testproject"', content)

    def test_scaffold_devcontainer_sets_image(self):
        """Should set image in devcontainer.json with default base image."""
        os.chdir(self.tmpdir)
        jolo.scaffold_devcontainer("testproject")

        json_file = Path(self.tmpdir) / ".devcontainer" / "devcontainer.json"
        content = json_file.read_text()
        self.assertIn('"image": "localhost/jolo:latest"', content)

    def test_scaffold_devcontainer_uses_config_base_image(self):
        """Should use base_image from config in devcontainer.json."""
        os.chdir(self.tmpdir)
        config = {"base_image": "custom/myimage:v3"}
        jolo.scaffold_devcontainer("testproject", config=config)

        json_file = Path(self.tmpdir) / ".devcontainer" / "devcontainer.json"
        content = json_file.read_text()
        self.assertIn('"image": "custom/myimage:v3"', content)
        self.assertNotIn("localhost/jolo", content)

    def test_scaffold_warns_if_exists(self):
        """Should warn but not error if .devcontainer exists."""
        os.chdir(self.tmpdir)
        devcontainer_dir = Path(self.tmpdir) / ".devcontainer"
        devcontainer_dir.mkdir()
        (devcontainer_dir / "devcontainer.json").write_text("existing")

        # Should not raise, should return False (not created)
        result = jolo.scaffold_devcontainer("testproject")
        self.assertFalse(result)

        # Original file should be preserved
        content = (devcontainer_dir / "devcontainer.json").read_text()
        self.assertEqual(content, "existing")

    def test_copy_template_files_includes_stash_note_guidance(self):
        """Generated projects should get stash-note guidance in AGENTS.md."""
        project_dir = Path(self.tmpdir) / "project"
        project_dir.mkdir()

        setup.copy_template_files(project_dir)

        agents = (project_dir / "AGENTS.md").read_text()
        self.assertIn("/workspaces/stash/notes", agents)
        self.assertIn("Would I want this loaded at session start", agents)

    def test_copy_template_files_includes_agent_ops_doc(self):
        """Generated projects should get on-demand agent recipes."""
        project_dir = Path(self.tmpdir) / "project"
        project_dir.mkdir()

        setup.copy_template_files(project_dir)

        agent_ops = project_dir / "docs" / "agent-ops.md"
        self.assertTrue(agent_ops.exists())
        self.assertIn("Cross-Agent Reviews", agent_ops.read_text())
        self.assertIn("golangci-lint", agent_ops.read_text())

    def test_copy_template_files_hash_tracks_agent_ops_doc(self):
        """On-demand agent recipes must sync on later recreate."""
        project_dir = Path(self.tmpdir) / "project"
        project_dir.mkdir()

        setup.copy_template_files(project_dir)

        hashes = setup._load_template_hashes(project_dir)
        self.assertIn("docs/agent-ops.md", hashes)


class TestSecretsManagement(unittest.TestCase):
    """Test secrets fetching from pass and environment."""

    def test_get_secrets_from_env(self):
        """Should get secrets from environment when pass unavailable."""
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-test123",
            "OPENAI_API_KEY": "sk-openai-test456",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("shutil.which", return_value=None):
                secrets = jolo.get_secrets()

        self.assertEqual(secrets["ANTHROPIC_API_KEY"], "sk-ant-test123")
        self.assertEqual(secrets["OPENAI_API_KEY"], "sk-openai-test456")

    def test_get_secrets_from_pass(self):
        """Should get secrets from pass when available."""

        def mock_run(cmd, *args, **kwargs):
            result = mock.Mock()
            result.returncode = 0
            if "api/llm/anthropic" in cmd:
                result.stdout = "sk-ant-from-pass\n"
            elif "api/llm/openai" in cmd:
                result.stdout = "sk-openai-from-pass\n"
            return result

        with mock.patch("shutil.which", return_value="/usr/bin/pass"):
            with mock.patch("subprocess.run", side_effect=mock_run):
                secrets = jolo.get_secrets()

        self.assertEqual(secrets["ANTHROPIC_API_KEY"], "sk-ant-from-pass")
        self.assertEqual(secrets["OPENAI_API_KEY"], "sk-openai-from-pass")

    def test_default_config_has_litellm_settings(self):
        from _jolo.constants import DEFAULT_CONFIG

        cfg = DEFAULT_CONFIG
        self.assertEqual(
            cfg["pass_path_litellm_master"], "api/llm/litellm-master"
        )
        # Gateway address defaults empty; load_config folds in LITELLM_HOST.
        self.assertEqual(cfg["litellm_base_url"], "")

    def test_load_config_folds_litellm_host_env(self):
        import _jolo.commands as commands

        with mock.patch.dict(
            os.environ, {"LITELLM_HOST": "http://gw.example:8088/"}, clear=True
        ):
            cfg = commands.load_config(
                global_config_dir=Path("/nonexistent/jolo-global"),
                project_dir=Path("/nonexistent/jolo-project"),
            )
        # env wins and the trailing slash is trimmed
        self.assertEqual(cfg["litellm_base_url"], "http://gw.example:8088")

    def test_get_secrets_includes_litellm_master_from_pass(self):
        def mock_run(cmd, *args, **kwargs):
            result = mock.Mock()
            result.returncode = 0
            result.stdout = (
                "sk-litellm-master\n"
                if "api/llm/litellm-master" in cmd
                else "x\n"
            )
            return result

        with mock.patch("shutil.which", return_value="/usr/bin/pass"):
            with mock.patch("subprocess.run", side_effect=mock_run):
                secrets = jolo.get_secrets()

        self.assertEqual(secrets["LITELLM_MASTER_KEY"], "sk-litellm-master")

    def test_get_secrets_includes_crawl4ai_token_from_pass(self):
        def mock_run(cmd, *args, **kwargs):
            result = mock.Mock()
            result.returncode = 0
            result.stdout = (
                "crawl-token\n" if "api/crawl/crawl4ai-token" in cmd else "x\n"
            )
            return result

        with mock.patch("shutil.which", return_value="/usr/bin/pass"):
            with mock.patch("subprocess.run", side_effect=mock_run):
                secrets = jolo.get_secrets()

        self.assertEqual(secrets["CRAWL4AI_API_TOKEN"], "crawl-token")

    def test_get_secrets_crawl4ai_token_env_fallback(self):
        env = {"CRAWL4AI_API_TOKEN": "crawl-from-env"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("shutil.which", return_value=None):
                secrets = jolo.get_secrets()

        self.assertEqual(secrets["CRAWL4AI_API_TOKEN"], "crawl-from-env")


class TestAddUserMounts(unittest.TestCase):
    """Test add_user_mounts() function."""

    def setUp(self):
        self.tmpdir = tracked_tmpdir(self)

    def test_add_user_mounts_to_devcontainer_json(self):
        """Mount should be added to mounts array in JSON."""
        # Create devcontainer.json
        devcontainer_dir = Path(self.tmpdir) / ".devcontainer"
        devcontainer_dir.mkdir()
        json_file = devcontainer_dir / "devcontainer.json"
        json_file.write_text(json.dumps({"name": "test", "mounts": []}))

        # Add a mount
        mounts = [
            {
                "source": "/home/user/data",
                "target": "/workspaces/test/data",
                "readonly": False,
            }
        ]
        jolo.add_user_mounts(json_file, mounts)

        # Verify
        content = json.loads(json_file.read_text())
        self.assertEqual(len(content["mounts"]), 1)
        self.assertIn("source=/home/user/data", content["mounts"][0])
        self.assertIn("target=/workspaces/test/data", content["mounts"][0])
        self.assertIn("type=bind", content["mounts"][0])

    def test_mount_readonly_format(self):
        """Readonly mount should include ,readonly in mount string."""
        devcontainer_dir = Path(self.tmpdir) / ".devcontainer"
        devcontainer_dir.mkdir()
        json_file = devcontainer_dir / "devcontainer.json"
        json_file.write_text(json.dumps({"name": "test", "mounts": []}))

        mounts = [{"source": "/data", "target": "/mnt", "readonly": True}]
        jolo.add_user_mounts(json_file, mounts)

        content = json.loads(json_file.read_text())
        self.assertIn(",readonly", content["mounts"][0])

    def test_multiple_mounts_in_json(self):
        """Multiple mounts should all be added."""
        devcontainer_dir = Path(self.tmpdir) / ".devcontainer"
        devcontainer_dir.mkdir()
        json_file = devcontainer_dir / "devcontainer.json"
        json_file.write_text(
            json.dumps({"name": "test", "mounts": ["existing"]})
        )

        mounts = [
            {"source": "/a", "target": "/mnt/a", "readonly": False},
            {"source": "/b", "target": "/mnt/b", "readonly": True},
        ]
        jolo.add_user_mounts(json_file, mounts)

        content = json.loads(json_file.read_text())
        self.assertEqual(len(content["mounts"]), 3)  # existing + 2 new

    def test_add_user_mounts_creates_mounts_array(self):
        """Should create mounts array if not present."""
        devcontainer_dir = Path(self.tmpdir) / ".devcontainer"
        devcontainer_dir.mkdir()
        json_file = devcontainer_dir / "devcontainer.json"
        json_file.write_text(json.dumps({"name": "test"}))

        mounts = [{"source": "/data", "target": "/mnt", "readonly": False}]
        jolo.add_user_mounts(json_file, mounts)

        content = json.loads(json_file.read_text())
        self.assertIn("mounts", content)
        self.assertEqual(len(content["mounts"]), 1)

    def test_add_user_mounts_empty_list(self):
        """Empty mounts list should not modify file."""
        devcontainer_dir = Path(self.tmpdir) / ".devcontainer"
        devcontainer_dir.mkdir()
        json_file = devcontainer_dir / "devcontainer.json"
        original = {"name": "test"}
        json_file.write_text(json.dumps(original))

        jolo.add_user_mounts(json_file, [])

        content = json.loads(json_file.read_text())
        self.assertEqual(content, original)


class TestCopyUserFiles(unittest.TestCase):
    """Test copy_user_files() function."""

    def setUp(self):
        self.tmpdir = tracked_tmpdir(self)

    def test_file_copied_to_correct_location(self):
        """File should be copied to target location."""
        workspace = Path(self.tmpdir) / "workspace"
        workspace.mkdir()

        # Create source file
        source = Path(self.tmpdir) / "source.json"
        source.write_text('{"test": true}')

        copies = [
            {"source": str(source), "target": "/workspaces/myproj/config.json"}
        ]
        jolo.copy_user_files(copies, workspace)

        target = workspace / "config.json"
        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(), '{"test": true}')

    def test_parent_directories_created(self):
        """Parent directories should be created if needed."""
        workspace = Path(self.tmpdir) / "workspace"
        workspace.mkdir()

        source = Path(self.tmpdir) / "source.json"
        source.write_text("test")

        copies = [
            {
                "source": str(source),
                "target": "/workspaces/myproj/nested/deep/config.json",
            }
        ]
        jolo.copy_user_files(copies, workspace)

        target = workspace / "nested" / "deep" / "config.json"
        self.assertTrue(target.exists())

    def test_error_on_missing_source(self):
        """Should error if source file doesn't exist."""
        workspace = Path(self.tmpdir) / "workspace"
        workspace.mkdir()

        copies = [
            {
                "source": "/nonexistent/file.json",
                "target": "/workspaces/myproj/config.json",
            }
        ]

        with self.assertRaises(SystemExit) as cm:
            jolo.copy_user_files(copies, workspace)
        self.assertIn("does not exist", str(cm.exception.code))

    def test_multiple_copies(self):
        """Multiple files should all be copied."""
        workspace = Path(self.tmpdir) / "workspace"
        workspace.mkdir()

        source1 = Path(self.tmpdir) / "a.json"
        source1.write_text("a")
        source2 = Path(self.tmpdir) / "b.json"
        source2.write_text("b")

        copies = [
            {"source": str(source1), "target": "/workspaces/myproj/a.json"},
            {"source": str(source2), "target": "/workspaces/myproj/b.json"},
        ]
        jolo.copy_user_files(copies, workspace)

        self.assertTrue((workspace / "a.json").exists())
        self.assertTrue((workspace / "b.json").exists())


class TestNotificationHooks(unittest.TestCase):
    """Test setup_notification_hooks() function."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def _workspace(self):
        """Create workspace with cache dirs mimicking post-credential-setup state."""
        ws = Path(self.tmpdir) / "project"
        (ws / ".devcontainer" / ".claude-cache").mkdir(parents=True)
        (ws / ".devcontainer" / ".gemini-cache").mkdir(parents=True)
        return ws

    def test_claude_session_end_hook_injected(self):
        """Should inject SessionEnd hook into Claude settings."""
        ws = self._workspace()
        claude_settings = (
            ws / ".devcontainer" / ".claude-cache" / "settings.json"
        )
        claude_settings.write_text("{}")

        jolo.setup_notification_hooks(ws)

        settings = json.loads(claude_settings.read_text())
        hooks = settings["hooks"]["SessionEnd"]
        self.assertEqual(len(hooks), 1)
        self.assertIn("notify", hooks[0]["hooks"][0]["command"])
        self.assertIn("AGENT=claude", hooks[0]["hooks"][0]["command"])

    def test_gemini_session_end_hook_injected(self):
        """Should inject SessionEnd hook into Gemini settings."""
        ws = self._workspace()
        gemini_settings = (
            ws / ".devcontainer" / ".gemini-cache" / "settings.json"
        )
        gemini_settings.write_text("{}")

        jolo.setup_notification_hooks(ws)

        settings = json.loads(gemini_settings.read_text())
        hooks = settings["hooks"]["SessionEnd"]
        self.assertEqual(len(hooks), 1)
        self.assertIn("notify", hooks[0]["hooks"][0]["command"])
        self.assertIn("AGENT=gemini", hooks[0]["hooks"][0]["command"])

    def test_merges_with_existing_hooks(self):
        """Should not clobber existing hooks in settings."""
        ws = self._workspace()
        claude_settings = (
            ws / ".devcontainer" / ".claude-cache" / "settings.json"
        )
        existing = {
            "hooks": {
                "SessionEnd": [
                    {"hooks": [{"type": "command", "command": "echo done"}]}
                ],
            },
            "other_key": "preserved",
        }
        claude_settings.write_text(json.dumps(existing))

        jolo.setup_notification_hooks(ws)

        settings = json.loads(claude_settings.read_text())
        self.assertEqual(settings["other_key"], "preserved")
        # Original hook + our new one
        self.assertEqual(len(settings["hooks"]["SessionEnd"]), 2)

    def test_idempotent_no_duplicates(self):
        """Running twice should not add duplicate hooks."""
        ws = self._workspace()
        claude_settings = (
            ws / ".devcontainer" / ".claude-cache" / "settings.json"
        )
        claude_settings.write_text("{}")

        jolo.setup_notification_hooks(ws)
        jolo.setup_notification_hooks(ws)

        settings = json.loads(claude_settings.read_text())
        self.assertEqual(len(settings["hooks"]["SessionEnd"]), 1)

    def test_creates_settings_if_missing(self):
        """Should create settings.json if it doesn't exist."""
        ws = self._workspace()
        claude_settings = (
            ws / ".devcontainer" / ".claude-cache" / "settings.json"
        )
        # Don't create the file — it shouldn't exist yet

        jolo.setup_notification_hooks(ws)

        self.assertTrue(claude_settings.exists())
        settings = json.loads(claude_settings.read_text())
        self.assertIn("hooks", settings)

    def test_creates_cache_dirs_if_missing(self):
        """Should create cache dirs if they don't exist."""
        ws = Path(self.tmpdir) / "project"
        ws.mkdir()
        # Don't create .devcontainer cache dirs

        jolo.setup_notification_hooks(ws)

        claude_settings = (
            ws / ".devcontainer" / ".claude-cache" / "settings.json"
        )
        gemini_settings = (
            ws / ".devcontainer" / ".gemini-cache" / "settings.json"
        )
        self.assertTrue(claude_settings.exists())
        self.assertTrue(gemini_settings.exists())

    def test_codex_notify_appended(self):
        """Should append notify to codex config.toml if it exists."""
        ws = self._workspace()
        codex_cache = ws / ".devcontainer" / ".codex-cache"
        codex_cache.mkdir(parents=True)
        codex_config = codex_cache / "config.toml"
        codex_config.write_text('model = "o3"\n')

        jolo.setup_notification_hooks(ws)

        config = codex_config.read_text()
        self.assertIn("notify", config)
        self.assertIn("AGENT=codex", config)

    def test_codex_notify_idempotent(self):
        """Should not duplicate codex notify on re-run."""
        ws = self._workspace()
        codex_cache = ws / ".devcontainer" / ".codex-cache"
        codex_cache.mkdir(parents=True)
        codex_config = codex_cache / "config.toml"
        codex_config.write_text('model = "o3"\n')

        jolo.setup_notification_hooks(ws)
        jolo.setup_notification_hooks(ws)

        config = codex_config.read_text()
        self.assertEqual(config.count("AGENT=codex notify"), 1)

    def test_codex_skipped_if_no_config(self):
        """Should not create codex config if it doesn't exist."""
        ws = self._workspace()
        codex_config = ws / ".devcontainer" / ".codex-cache" / "config.toml"

        jolo.setup_notification_hooks(ws)

        self.assertFalse(codex_config.exists())

    def test_corrupt_json_does_not_crash(self):
        """Should handle corrupt/empty settings.json gracefully."""
        ws = self._workspace()
        claude_settings = (
            ws / ".devcontainer" / ".claude-cache" / "settings.json"
        )
        claude_settings.write_text("not valid json{{{")

        # Should not raise
        jolo.setup_notification_hooks(ws)

        settings = json.loads(claude_settings.read_text())
        self.assertIn("hooks", settings)

    def test_codex_skipped_if_notify_key_exists(self):
        """Should not append duplicate notify key to codex config."""
        ws = self._workspace()
        codex_cache = ws / ".devcontainer" / ".codex-cache"
        codex_cache.mkdir(parents=True)
        codex_config = codex_cache / "config.toml"
        codex_config.write_text('notify = ["some-other-command"]\n')

        jolo.setup_notification_hooks(ws)

        config = codex_config.read_text()
        self.assertEqual(config.count("notify"), 1)
        self.assertNotIn("AGENT=codex notify", config)

    def test_threshold_default_is_60(self):
        """Default notify_threshold should be 60 seconds."""
        ws = self._workspace()
        claude_settings = (
            ws / ".devcontainer" / ".claude-cache" / "settings.json"
        )
        claude_settings.write_text("{}")

        jolo.setup_notification_hooks(ws)

        settings = json.loads(claude_settings.read_text())
        stop_hooks = settings["hooks"]["Stop"]
        cmd = stop_hooks[0]["hooks"][0]["command"]
        self.assertIn("--if-slow 60", cmd)

    def test_threshold_custom_value(self):
        """Custom notify_threshold should be used."""
        ws = self._workspace()
        claude_settings = (
            ws / ".devcontainer" / ".claude-cache" / "settings.json"
        )
        claude_settings.write_text("{}")

        jolo.setup_notification_hooks(ws, notify_threshold=120)

        settings = json.loads(claude_settings.read_text())
        stop_hooks = settings["hooks"]["Stop"]
        cmd = stop_hooks[0]["hooks"][0]["command"]
        self.assertIn("--if-slow 120", cmd)

    def test_threshold_update_replaces_existing(self):
        """Calling setup_notification_hooks again with different threshold should update the hook."""
        ws = self._workspace()
        claude_settings = (
            ws / ".devcontainer" / ".claude-cache" / "settings.json"
        )
        claude_settings.write_text("{}")

        jolo.setup_notification_hooks(ws, notify_threshold=60)
        jolo.setup_notification_hooks(ws, notify_threshold=20)

        settings = json.loads(claude_settings.read_text())
        stop_hooks = settings["hooks"]["Stop"]
        self.assertEqual(len(stop_hooks), 1)
        cmd = stop_hooks[0]["hooks"][0]["command"]
        self.assertIn("--if-slow 20", cmd)
        self.assertNotIn("--if-slow 60", cmd)

    def test_config_notify_threshold_in_defaults(self):
        """DEFAULT_CONFIG should include notify_threshold."""
        from _jolo.constants import DEFAULT_CONFIG

        self.assertIn("notify_threshold", DEFAULT_CONFIG)
        self.assertEqual(DEFAULT_CONFIG["notify_threshold"], 60)


class TestCredentialMountStrategy(unittest.TestCase):
    """Test that Claude credentials use selective mounts, not directory copy."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_credentials_not_copied_to_cache(self):
        """setup_credential_cache() should NOT copy .credentials.json (mounted from host)."""
        ws = Path(self.tmpdir) / "project"
        ws.mkdir()

        home = Path(self.tmpdir) / "home"
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / ".credentials.json").write_text('{"token": "test"}')
        (claude_dir / "settings.json").write_text("{}")

        with mock.patch("pathlib.Path.home", return_value=home):
            jolo.setup_credential_cache(ws)

        cache = ws / ".devcontainer" / ".claude-cache"
        self.assertFalse((cache / ".credentials.json").exists())

    def test_settings_still_copied_to_cache(self):
        """setup_credential_cache() should still copy settings.json for hook injection."""
        ws = Path(self.tmpdir) / "project"
        ws.mkdir()

        home = Path(self.tmpdir) / "home"
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / "settings.json").write_text('{"theme": "dark"}')

        with mock.patch("pathlib.Path.home", return_value=home):
            jolo.setup_credential_cache(ws)

        cache = ws / ".devcontainer" / ".claude-cache"
        self.assertTrue((cache / "settings.json").exists())
        self.assertIn("dark", (cache / "settings.json").read_text())

    def test_codex_reasoning_effort_default_injected(self):
        """setup_credential_cache() should inject model_reasoning_effort when missing."""
        ws = Path(self.tmpdir) / "project"
        ws.mkdir()

        home = Path(self.tmpdir) / "home"
        codex_dir = home / ".codex"
        codex_dir.mkdir(parents=True)
        (codex_dir / "config.toml").write_text(
            'model = "gpt-5.3-codex"\n\n[tooling.browser]\ncommand = "playwright-cli"\n'
        )

        with mock.patch("pathlib.Path.home", return_value=home):
            jolo.setup_credential_cache(ws)

        codex_config = ws / ".devcontainer" / ".codex-cache" / "config.toml"
        content = codex_config.read_text()
        self.assertIn('model_reasoning_effort = "high"', content)
        self.assertLess(
            content.find('model_reasoning_effort = "high"'),
            content.find("[tooling.browser]"),
        )

    def test_codex_reasoning_effort_not_overwritten(self):
        """setup_credential_cache() should preserve existing model_reasoning_effort."""
        ws = Path(self.tmpdir) / "project"
        ws.mkdir()

        home = Path(self.tmpdir) / "home"
        codex_dir = home / ".codex"
        codex_dir.mkdir(parents=True)
        (codex_dir / "config.toml").write_text(
            'model = "gpt-5.3-codex"\nmodel_reasoning_effort = "xhigh"\n'
        )

        with mock.patch("pathlib.Path.home", return_value=home):
            jolo.setup_credential_cache(ws)

        codex_config = ws / ".devcontainer" / ".codex-cache" / "config.toml"
        content = codex_config.read_text()
        self.assertIn('model_reasoning_effort = "xhigh"', content)
        self.assertEqual(content.count("model_reasoning_effort"), 1)

    def test_base_mounts_has_selective_claude_mounts(self):
        """BASE_MOUNTS should have individual file mounts, not a directory mount."""
        from _jolo.constants import BASE_MOUNTS

        claude_mounts = [
            m
            for m in BASE_MOUNTS
            if ".claude" in m and ".claude.json" not in m
        ]

        # Should have credentials (RW from host), settings (from cache), statsig (RO from host)
        cred_mounts = [m for m in claude_mounts if ".credentials.json" in m]
        settings_mounts = [m for m in claude_mounts if "settings.json" in m]
        statsig_mounts = [m for m in claude_mounts if "statsig" in m]

        self.assertEqual(len(cred_mounts), 1)
        self.assertNotIn("readonly", cred_mounts[0])

        self.assertEqual(len(settings_mounts), 1)
        self.assertIn(".claude-cache/settings.json", settings_mounts[0])

        self.assertEqual(len(statsig_mounts), 1)
        self.assertIn("readonly", statsig_mounts[0])

        # Should NOT have the old directory mount
        dir_mounts = [
            m
            for m in claude_mounts
            if m.endswith("type=bind") and ".claude,target" in m
        ]
        self.assertEqual(len(dir_mounts), 0)


class TestPersistentCredentialStore(unittest.TestCase):
    """OAuth tokens (agy, gemini) round-trip through ~/.config/jolo so they
    survive .gemini-cache rebuilds across containers."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = Path(self.tmpdir) / "home"
        self.home.mkdir(parents=True)
        self.ws = Path(self.tmpdir) / "project"
        self.ws.mkdir()
        self.store = self.home / ".config" / "jolo"
        self.cache = self.ws / ".devcontainer" / ".gemini-cache"

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def _run(self):
        with mock.patch("pathlib.Path.home", return_value=self.home):
            jolo.setup_credential_cache(self.ws)

    @staticmethod
    def _stamp(path: Path, mtime: float):
        os.utime(path, (mtime, mtime))

    def test_seeds_fresh_cache_from_store(self):
        """A new container's cache is seeded from the shared store."""
        self.store.mkdir(parents=True)
        (self.store / "antigravity-oauth-token").write_text('{"token": "agy"}')
        (self.store / "gemini-credentials.json").write_text("gemini-blob")

        self._run()

        agy = self.cache / "antigravity-cli" / "antigravity-oauth-token"
        gem = self.cache / "gemini-credentials.json"
        self.assertTrue(agy.exists())
        self.assertEqual(agy.read_text(), '{"token": "agy"}')
        self.assertEqual(gem.read_text(), "gemini-blob")

    def test_writes_back_refreshed_token_before_clear(self):
        """A token refreshed inside a container is copied up before the cache
        is wiped, and survives into the rebuilt cache."""
        self.store.mkdir(parents=True)
        old = self.store / "antigravity-oauth-token"
        old.write_text('{"token": "old"}')
        self._stamp(old, 1000)

        agy_cache = self.cache / "antigravity-cli"
        agy_cache.mkdir(parents=True)
        fresh = agy_cache / "antigravity-oauth-token"
        fresh.write_text('{"token": "fresh"}')
        self._stamp(fresh, 2000)

        self._run()

        self.assertEqual(old.read_text(), '{"token": "fresh"}')
        seeded = self.cache / "antigravity-cli" / "antigravity-oauth-token"
        self.assertEqual(seeded.read_text(), '{"token": "fresh"}')

    def test_does_not_clobber_newer_store(self):
        """An older cache token must not overwrite a newer shared store."""
        self.store.mkdir(parents=True)
        store_tok = self.store / "antigravity-oauth-token"
        store_tok.write_text('{"token": "store-new"}')
        self._stamp(store_tok, 2000)

        agy_cache = self.cache / "antigravity-cli"
        agy_cache.mkdir(parents=True)
        stale = agy_cache / "antigravity-oauth-token"
        stale.write_text('{"token": "cache-old"}')
        self._stamp(stale, 1000)

        self._run()

        self.assertEqual(store_tok.read_text(), '{"token": "store-new"}')

    def test_bakes_agy_settings_defaults(self):
        """Fresh cache gets agy defaults (light theme, telemetry off) so a new
        container doesn't prompt on first launch."""
        self._run()

        agy_settings = self.cache / "antigravity-cli" / "settings.json"
        self.assertTrue(agy_settings.exists())
        data = json.loads(agy_settings.read_text())
        self.assertEqual(data["colorScheme"], "light")
        self.assertEqual(data["enableTelemetry"], False)

    def test_trusts_workspace_and_stash(self):
        """agy ignores gemini's trustedFolders.json — its own
        trustedWorkspaces must cover the project and stash so no container
        start hits the folder-trust prompt."""
        self._run()

        agy_settings = self.cache / "antigravity-cli" / "settings.json"
        data = json.loads(agy_settings.read_text())
        self.assertEqual(
            data["trustedWorkspaces"],
            [f"/workspaces/{self.ws.name}", "/workspaces/stash"],
        )

    def test_marks_agy_onboarding_complete(self):
        """agy gates its first-run theme/telemetry prompts on
        cache/onboarding.json, not settings.json — so we must mark it done."""
        self._run()

        onboarding = (
            self.cache / "antigravity-cli" / "cache" / "onboarding.json"
        )
        self.assertTrue(onboarding.exists())
        data = json.loads(onboarding.read_text())
        self.assertTrue(data["onboardingComplete"])
        self.assertTrue(data["consumerOnboardingComplete"])

    def test_agy_defaults_reset_on_rebuild(self):
        """The cache is wiped each rebuild, so agy prefs are re-baked to the
        defaults (no stale dark/telemetry-on survives)."""
        agy_dir = self.cache / "antigravity-cli"
        agy_dir.mkdir(parents=True)
        (agy_dir / "settings.json").write_text(
            '{"colorScheme": "dark", "enableTelemetry": true}'
        )

        self._run()

        data = json.loads((agy_dir / "settings.json").read_text())
        self.assertEqual(data["enableTelemetry"], False)
        self.assertEqual(data["colorScheme"], "light")

    def test_copies_gemini_credentials_from_host(self):
        """Host gemini-credentials.json (renamed from oauth_creds.json) is
        copied into the cache."""
        gemini_dir = self.home / ".gemini"
        gemini_dir.mkdir(parents=True)
        (gemini_dir / "gemini-credentials.json").write_text("host-gemini")

        self._run()

        gem = self.cache / "gemini-credentials.json"
        self.assertTrue(gem.exists())
        self.assertEqual(gem.read_text(), "host-gemini")


class TestPiWriteContract(unittest.TestCase):
    """Test Pi project settings and the ~/.pi/agent write contract.

    llama/gateway/codex provider config and default-model seeding were
    deleted (host owns ~/.pi entirely now); only project-scoped settings
    and the write-nothing-under-agent contract remain to test.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_npm_command_goes_to_project_settings(self):
        """npmCommand is an image fact: pnpm in the container, not on the host."""
        ws = Path(self.tmpdir) / "project"
        ws.mkdir()
        home = Path(self.tmpdir) / "home"
        (home / ".pi" / "agent").mkdir(parents=True)

        with mock.patch("pathlib.Path.home", return_value=home):
            setup.setup_credential_cache(ws)

        project_settings = json.loads(
            (ws / ".pi" / "settings.json").read_text()
        )
        self.assertEqual(project_settings["npmCommand"], ["pnpm"])

    def test_project_settings_preserves_existing_keys(self):
        """Merge into .pi/settings.json; never clobber what the project set."""
        ws = Path(self.tmpdir) / "project"
        (ws / ".pi").mkdir(parents=True)
        (ws / ".pi" / "settings.json").write_text(
            json.dumps({"theme": "gruvbox-light"})
        )
        home = Path(self.tmpdir) / "home"
        (home / ".pi" / "agent").mkdir(parents=True)

        with mock.patch("pathlib.Path.home", return_value=home):
            setup.setup_credential_cache(ws)

        project_settings = json.loads(
            (ws / ".pi" / "settings.json").read_text()
        )
        self.assertEqual(project_settings["theme"], "gruvbox-light")
        self.assertEqual(project_settings["npmCommand"], ["pnpm"])

    def test_setup_does_not_write_pi_delegation(self):
        """delegation.md is a host preference; jolo must not write it."""
        ws = Path(self.tmpdir) / "project"
        ws.mkdir()
        home = Path(self.tmpdir) / "home"
        (home / ".pi" / "agent").mkdir(parents=True)

        with mock.patch("pathlib.Path.home", return_value=home):
            setup.setup_credential_cache(ws)

        self.assertFalse((home / ".pi" / "agent" / "delegation.md").exists())

    def test_setup_does_not_write_pi_subagent_extension(self):
        """The subagent shim is a host preference; jolo must not write it."""
        ws = Path(self.tmpdir) / "project"
        ws.mkdir()
        home = Path(self.tmpdir) / "home"
        (home / ".pi" / "agent").mkdir(parents=True)

        with mock.patch("pathlib.Path.home", return_value=home):
            setup.setup_credential_cache(ws)

        extensions = home / ".pi" / "agent" / "extensions"
        self.assertFalse((extensions / "pi-official-subagent.ts").exists())

    def test_jolo_writes_nothing_under_pi_agent(self):
        """The ownership contract: pi config is the host's, and ~/.pi is
        already mounted. jolo's only pi write is npmCommand, and that goes to
        the workspace's .pi/settings.json — never into the shared mount.
        """
        ws = Path(self.tmpdir) / "project"
        ws.mkdir()
        home = Path(self.tmpdir) / "home"
        agent_dir = home / ".pi" / "agent"
        agent_dir.mkdir(parents=True)

        with mock.patch("pathlib.Path.home", return_value=home):
            setup.setup_credential_cache(ws)

        written = {
            str(p.relative_to(agent_dir))
            for p in agent_dir.rglob("*")
            if p.is_file()
        }
        self.assertEqual(written, set())


class TestPatchJsonWithJq(unittest.TestCase):
    """Test jq-based JSON patch helper."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_patch_json_with_jq_writes_output(self):
        """Should write jq output and invoke jq with expected args."""
        target = Path(self.tmpdir) / "trustedFolders.json"
        jq_args = [
            "--arg",
            "path",
            "/workspaces/project",
            "--arg",
            "value",
            "TRUST_FOLDER",
        ]
        jq_filter = ".[$path] = $value"

        mock_result = mock.Mock(stdout='{"ok":true}\n')
        with mock.patch("subprocess.run", return_value=mock_result) as run:
            setup._patch_json_with_jq(target, jq_args, jq_filter)

        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(), '{"ok":true}\n')

        expected_cmd = ["jq", "-n", *jq_args, jq_filter]
        run.assert_called_once_with(
            expected_cmd, check=True, capture_output=True, text=True
        )


class TestEnsureTopLevelTomlKey(unittest.TestCase):
    """Test TOML key insertion helper."""

    def test_inserts_key_before_first_table(self):
        """Should insert key before the first [table] header."""
        content = 'model = "gpt-5"\n\n[mcp_servers.foo]\ncommand = "bar"\n'
        result = setup._ensure_top_level_toml_key(
            content, "model_reasoning_effort", "high"
        )
        self.assertIn('model_reasoning_effort = "high"', result)
        # Key should appear before the table
        self.assertLess(
            result.find("model_reasoning_effort"),
            result.find("[mcp_servers.foo]"),
        )

    def test_appends_key_when_no_tables(self):
        """Should append key at end when no [table] headers exist."""
        content = 'model = "gpt-5"\n'
        result = setup._ensure_top_level_toml_key(
            content, "model_reasoning_effort", "high"
        )
        self.assertIn('model_reasoning_effort = "high"', result)
        self.assertTrue(result.endswith("\n"))

    def test_preserves_existing_key(self):
        """Should not overwrite when key already exists."""
        content = 'model_reasoning_effort = "low"\nmodel = "gpt-5"\n'
        result = setup._ensure_top_level_toml_key(
            content, "model_reasoning_effort", "high"
        )
        self.assertIn('"low"', result)
        self.assertNotIn('"high"', result)
        self.assertEqual(result, content)

    def test_handles_empty_content(self):
        """Should work with empty string."""
        result = setup._ensure_top_level_toml_key(
            "", "model_reasoning_effort", "high"
        )
        self.assertIn('model_reasoning_effort = "high"', result)

    def test_adds_newline_before_table_if_missing(self):
        """Should ensure newline separation before table."""
        content = 'model = "gpt-5"\n[servers]'
        result = setup._ensure_top_level_toml_key(content, "effort", "high")
        self.assertIn('effort = "high"\n\n[servers]', result)


class TestSyncOneJolonew(unittest.TestCase):
    """_sync_one_file semantics: written / updated / jolonew / unchanged."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.target = Path(self.tmpdir)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_written_when_absent(self):
        hashes: dict = {}
        result = setup._sync_one_file(
            self.target, "file.txt", b"hello\n", hashes
        )
        self.assertEqual(result, "written")
        self.assertEqual((self.target / "file.txt").read_text(), "hello\n")
        self.assertIn("file.txt", hashes)
        # No .jolonew created for fresh install.
        self.assertFalse((self.target / "file.txt.jolonew").exists())

    def test_unchanged_when_content_matches(self):
        (self.target / "file.txt").write_text("hello\n")
        hashes = {"file.txt": setup._file_hash(self.target / "file.txt")}
        result = setup._sync_one_file(
            self.target, "file.txt", b"hello\n", hashes
        )
        self.assertEqual(result, "unchanged")

    def test_updated_when_clean_and_template_moved(self):
        # User hasn't edited: current == stored hash.
        (self.target / "file.txt").write_text("old\n")
        hashes = {"file.txt": setup._file_hash(self.target / "file.txt")}
        result = setup._sync_one_file(
            self.target, "file.txt", b"new\n", hashes
        )
        self.assertEqual(result, "updated")
        self.assertEqual((self.target / "file.txt").read_text(), "new\n")
        self.assertFalse((self.target / "file.txt.jolonew").exists())

    def test_jolonew_when_user_edited(self):
        (self.target / "file.txt").write_text("my edits\n")
        # Stored hash is of the ORIGINAL template; current file is user-edited.
        hashes = {
            "file.txt": setup.hashlib.sha256(b"original\n").hexdigest(),
        }
        result = setup._sync_one_file(
            self.target, "file.txt", b"new template\n", hashes
        )
        self.assertEqual(result, "jolonew")
        # User edits preserved.
        self.assertEqual((self.target / "file.txt").read_text(), "my edits\n")
        # New version parked alongside.
        self.assertTrue((self.target / "file.txt.jolonew").exists())
        self.assertEqual(
            (self.target / "file.txt.jolonew").read_text(), "new template\n"
        )

    def test_jolonew_always_overwritten(self):
        # Second template bump should rewrite .jolonew with latest content.
        (self.target / "file.txt").write_text("my edits\n")
        (self.target / "file.txt.jolonew").write_text("stale template\n")
        hashes = {
            "file.txt": setup.hashlib.sha256(b"original\n").hexdigest(),
        }
        setup._sync_one_file(
            self.target, "file.txt", b"newest template\n", hashes
        )
        self.assertEqual(
            (self.target / "file.txt.jolonew").read_text(),
            "newest template\n",
        )

    def test_untracked_when_file_exists_without_hash_record(self):
        # The meta-repo's own justfile, or any project that predates
        # hash tracking: file exists, but jolo never wrote it. Don't
        # touch it, don't drop a .jolonew alongside.
        (self.target / "file.txt").write_text("hand-curated content\n")
        hashes: dict = {}
        result = setup._sync_one_file(
            self.target, "file.txt", b"template output\n", hashes
        )
        self.assertEqual(result, "untracked")
        self.assertEqual(
            (self.target / "file.txt").read_text(), "hand-curated content\n"
        )
        self.assertFalse((self.target / "file.txt.jolonew").exists())
        self.assertNotIn("file.txt", hashes)

    def test_force_overwrites_untracked_file(self):
        # --force is the "give me the latest template, period" escape
        # hatch: silently skipping fresh template bumps for an untracked
        # file is the failure mode users cannot detect (whereas losing
        # local edits is recoverable from git). So --force overwrites,
        # no .jolonew dance.
        (self.target / "file.txt").write_text("hand-curated content\n")
        hashes: dict = {}
        result = setup._sync_one_file(
            self.target,
            "file.txt",
            b"template output\n",
            hashes,
            force=True,
        )
        self.assertEqual(result, "updated")
        self.assertEqual(
            (self.target / "file.txt").read_text(), "template output\n"
        )
        self.assertFalse((self.target / "file.txt.jolonew").exists())
        self.assertEqual(
            hashes["file.txt"], setup._file_hash(self.target / "file.txt")
        )

    def test_force_skips_write_when_content_matches(self):
        # --force must not touch a file whose content already matches
        # the template — otherwise mtime churn shows up as a spurious
        # git diff and pre-commit blocks commits with "config unstaged".
        path = self.target / "file.txt"
        path.write_text("identical\n")
        original_mtime = path.stat().st_mtime_ns
        hashes: dict = {}
        result = setup._sync_one_file(
            self.target,
            "file.txt",
            b"identical\n",
            hashes,
            force=True,
        )
        self.assertEqual(result, "unchanged")
        self.assertEqual(path.stat().st_mtime_ns, original_mtime)

    def test_force_overwrites_user_edited_file(self):
        # User-edited file under --force: overwrite. Git is the safety
        # net for the user's edits.
        (self.target / "file.txt").write_text("my edits\n")
        hashes = {
            "file.txt": setup.hashlib.sha256(b"original\n").hexdigest(),
        }
        result = setup._sync_one_file(
            self.target,
            "file.txt",
            b"newest template\n",
            hashes,
            force=True,
        )
        self.assertEqual(result, "updated")
        self.assertEqual(
            (self.target / "file.txt").read_text(), "newest template\n"
        )
        self.assertFalse((self.target / "file.txt.jolonew").exists())


class TestPrecommitConfigSync(unittest.TestCase):
    """``.pre-commit-config.yaml`` is jolo-owned. Without ``--force``, an
    edited config is left alone (with a ``.jolonew`` sibling for review
    when the recorded hash is known). Under ``--force``, the file is
    overwritten — git tracks the user's customizations.

    The post-commit ``perf-run`` hook used to live in this file. It was
    moved out to ``.git/hooks/post-commit`` (managed-injection block) so
    the perf-testing wiring no longer requires jolo to own this file.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project = Path(self.tmpdir) / "demo"
        self.project.mkdir()
        (self.project / "pyproject.toml").write_text(
            "[project]\nname = 'demo'\n"
        )

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_sync_creates_precommit_config_when_missing(self):
        self.assertFalse((self.project / ".pre-commit-config.yaml").exists())
        setup.sync_template_files(self.project)
        content = (self.project / ".pre-commit-config.yaml").read_text()
        # Standard hooks present, but the post-commit perf hook is no
        # longer baked into the pre-commit config — it's a direct git hook.
        self.assertIn("trailing-whitespace", content)
        self.assertNotIn("perf-run", content)

    def test_sync_force_overwrites_user_edited_precommit(self):
        # --force is the "latest template, period" escape hatch: the
        # silent-skip mode is a worse failure (user runs stale hooks
        # without knowing) than the recoverable one (custom hooks
        # need to be re-added from git history).
        custom = "# user-curated hooks\nrepos: []\n"
        (self.project / ".pre-commit-config.yaml").write_text(custom)
        setup.sync_template_files(self.project, force=True)
        content = (self.project / ".pre-commit-config.yaml").read_text()
        self.assertIn("trailing-whitespace", content)
        self.assertNotIn("user-curated hooks", content)
        self.assertFalse(
            (self.project / ".pre-commit-config.yaml.jolonew").exists()
        )

    def test_sync_default_leaves_user_precommit_alone(self):
        # Without --force, an untracked user-curated config is left
        # entirely alone — no .jolonew, no overwrite.
        custom = "# my hooks\nrepos: []\n"
        (self.project / ".pre-commit-config.yaml").write_text(custom)
        setup.sync_template_files(self.project)
        self.assertEqual(
            (self.project / ".pre-commit-config.yaml").read_text(), custom
        )
        self.assertFalse(
            (self.project / ".pre-commit-config.yaml.jolonew").exists()
        )


class TestJoloPostCommitInjection(unittest.TestCase):
    """Managed-injection block for ``.git/hooks/post-commit``.

    jolo owns the perf-run wiring, but does NOT own the user's git hook
    file. Idempotent injection between sentinel markers means jolo can
    co-exist with any other tool (pre-commit framework, husky, custom
    user scripts) that wants to write into the same hook.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project = Path(self.tmpdir) / "proj"
        self.project.mkdir()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def _block(self) -> str:
        # Tests treat the block as opaque content the helper installs;
        # we only assert observable behavior (markers + the perf line).
        return setup._JOLO_POST_COMMIT_BLOCK

    def test_creates_block_when_text_empty(self):
        new = setup._replace_or_append_jolo_block("", self._block())
        self.assertIn("# >>> jolo-perf-start <<<", new)
        self.assertIn("# >>> jolo-perf-end <<<", new)
        self.assertIn("just perf", new)
        # Empty input gets a shebang so the file is a valid hook script.
        self.assertTrue(new.startswith("#!/bin/sh\n"))

    def test_appends_block_when_no_markers(self):
        existing = "#!/bin/sh\nset -e\necho hi\n"
        new = setup._replace_or_append_jolo_block(existing, self._block())
        self.assertTrue(new.startswith("#!/bin/sh\nset -e\necho hi\n"))
        self.assertIn("# >>> jolo-perf-start <<<", new)
        self.assertIn("echo hi", new)

    def test_replaces_existing_block_keeps_user_content(self):
        existing = (
            "#!/bin/sh\n"
            "set -e\n"
            "# >>> jolo-perf-start <<<\n"
            "stale-content-from-old-jolo\n"
            "# >>> jolo-perf-end <<<\n"
            "echo trailing user line\n"
        )
        new = setup._replace_or_append_jolo_block(existing, self._block())
        self.assertNotIn("stale-content-from-old-jolo", new)
        self.assertIn("just perf", new)
        # User content outside the managed block is preserved.
        self.assertIn("set -e", new)
        self.assertIn("echo trailing user line", new)
        # Exactly one managed block in the result.
        self.assertEqual(new.count("# >>> jolo-perf-start <<<"), 1)

    def test_collapses_duplicate_blocks_from_old_bug(self):
        # If a previous bug ever appended twice, the helper must
        # converge to a single block on the next refresh.
        existing = (
            "#!/bin/sh\n"
            "# >>> jolo-perf-start <<<\nfirst-stale\n# >>> jolo-perf-end <<<\n"
            "# >>> jolo-perf-start <<<\nsecond-stale\n# >>> jolo-perf-end <<<\n"
        )
        new = setup._replace_or_append_jolo_block(existing, self._block())
        self.assertEqual(new.count("# >>> jolo-perf-start <<<"), 1)
        self.assertNotIn("first-stale", new)
        self.assertNotIn("second-stale", new)

    def test_does_not_match_marker_substring_in_user_content(self):
        # A stray sentinel-looking string in user content (e.g. an echo
        # or a heredoc) must NOT be matched. Only line-anchored markers
        # are recognized.
        existing = (
            "#!/bin/sh\n"
            'echo "fake # >>> jolo-perf-start <<< inline"\n'
            'echo "fake # >>> jolo-perf-end <<< inline"\n'
        )
        new = setup._replace_or_append_jolo_block(existing, self._block())
        # User echo lines are still there in full.
        self.assertIn('echo "fake # >>> jolo-perf-start <<< inline"', new)
        self.assertIn('echo "fake # >>> jolo-perf-end <<< inline"', new)
        # And the real managed block was appended at the end.
        self.assertTrue(new.rstrip().endswith("# >>> jolo-perf-end <<<"))

    def test_block_only_input_recovers_shebang(self):
        # Pathological recovery: file contains ONLY a managed block (no
        # shebang, no user content). After strip, buffer is empty. The
        # helper must still produce a valid hook script with a shebang
        # so git executes it.
        existing = (
            "# >>> jolo-perf-start <<<\nstale\n# >>> jolo-perf-end <<<\n"
        )
        new = setup._replace_or_append_jolo_block(existing, self._block())
        self.assertTrue(new.startswith("#!/bin/sh\n"))
        self.assertIn("just perf", new)
        self.assertNotIn("stale", new)

    def test_existing_user_hook_without_shebang_gets_one(self):
        # Defensive: if a user file lacks a shebang, prepend one rather
        # than leave a hook git can't execute reliably.
        existing = "echo bare-user-line\n"
        new = setup._replace_or_append_jolo_block(existing, self._block())
        self.assertTrue(new.startswith("#!/bin/sh\n"))
        self.assertIn("echo bare-user-line", new)

    def test_handles_crlf_line_endings(self):
        existing = (
            "#!/bin/sh\r\n"
            "# >>> jolo-perf-start <<<\r\nstale\r\n"
            "# >>> jolo-perf-end <<<\r\n"
            "echo after\r\n"
        )
        new = setup._replace_or_append_jolo_block(existing, self._block())
        self.assertNotIn("stale", new)
        self.assertIn("echo after", new)
        self.assertEqual(new.count("# >>> jolo-perf-start <<<"), 1)

    def test_idempotent_across_two_calls(self):
        existing = "#!/bin/sh\necho user-pre\n"
        first = setup._replace_or_append_jolo_block(existing, self._block())
        second = setup._replace_or_append_jolo_block(first, self._block())
        self.assertEqual(first, second)

    def test_install_writes_executable_hook_in_real_repo(self):
        import subprocess

        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        setup.install_jolo_post_commit_hook(self.project)
        hook = self.project / ".git" / "hooks" / "post-commit"
        self.assertTrue(hook.exists())
        text = hook.read_text()
        self.assertIn("# >>> jolo-perf-start <<<", text)
        self.assertIn("just perf", text)
        # Executable bit set so git actually runs it.
        self.assertTrue(os.access(hook, os.X_OK))

    def test_install_preserves_existing_user_hook_content(self):
        import subprocess

        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        hook = self.project / ".git" / "hooks" / "post-commit"
        hook.write_text("#!/bin/sh\necho user did this\n")
        hook.chmod(0o755)
        setup.install_jolo_post_commit_hook(self.project)
        text = hook.read_text()
        self.assertIn("echo user did this", text)
        self.assertIn("# >>> jolo-perf-start <<<", text)

    def test_install_skips_write_when_unchanged(self):
        # Repeated --recreate must not bump mtime — make-style watchers
        # care, and the hook is shared across worktrees so a no-op
        # recreate in worktree A shouldn't disturb worktree B's view.
        import subprocess

        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        setup.install_jolo_post_commit_hook(self.project)
        hook = self.project / ".git" / "hooks" / "post-commit"
        first_mtime = hook.stat().st_mtime_ns
        setup.install_jolo_post_commit_hook(self.project)
        self.assertEqual(hook.stat().st_mtime_ns, first_mtime)

    def test_install_concurrent_writers_converge_to_one_block(self):
        # `jolo spawn N` creates N worktrees that share `.git/hooks/`.
        # Concurrent installs must not tear the file or leave duplicate
        # blocks behind.
        import subprocess
        import threading

        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        hook = self.project / ".git" / "hooks" / "post-commit"
        hook.write_text("#!/bin/sh\necho user-baseline\n")

        errors: list[BaseException] = []

        def worker():
            try:
                setup.install_jolo_post_commit_hook(self.project)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        text = hook.read_text()
        self.assertIn("echo user-baseline", text)
        self.assertEqual(text.count("# >>> jolo-perf-start <<<"), 1)
        self.assertEqual(text.count("# >>> jolo-perf-end <<<"), 1)


class TestPerfRigSync(unittest.TestCase):
    """perf-rig.toml participates in the tool-owned sync path; --force
    overwrites it, default leaves user edits alone (git catches drift)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project = Path(self.tmpdir) / "demokrate"
        self.project.mkdir()
        (self.project / "pyproject.toml").write_text(
            "[project]\nname = 'demokrate'\n"
        )

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_sync_regenerates_stale_rig_without_force(self):
        """Edited rigs get a .jolonew; original stays put."""
        (self.project / "perf-rig.toml").write_text(
            "schema_version = 1\n"
            '[project]\nname = "{{PROJECT_NAME}}"\n'
            'language = "{{PROJECT_LANGUAGE}}"\n'
        )
        setup.sync_template_files(self.project)
        # Untracked file with no hash history hits the "untracked" path,
        # so the stale rig is NOT overwritten without --force. Sibling
        # jolonew should NOT appear either (safety default for untracked).
        content = (self.project / "perf-rig.toml").read_text()
        self.assertIn("{{PROJECT_NAME}}", content)

    def test_sync_force_overwrites_rig(self):
        """--force writes a fresh, filled rig even over a user-edited one."""
        (self.project / "perf-rig.toml").write_text("# totally custom\n")
        setup.sync_template_files(self.project, force=True)
        content = (self.project / "perf-rig.toml").read_text()
        self.assertNotIn("totally custom", content)
        self.assertIn('name = "demokrate"', content)
        self.assertIn('language = "python"', content)

    def test_sync_creates_rig_when_missing(self):
        """Fresh project with no perf-rig.toml gets one written filled."""
        self.assertFalse((self.project / "perf-rig.toml").exists())
        setup.sync_template_files(self.project)
        content = (self.project / "perf-rig.toml").read_text()
        self.assertIn('name = "demokrate"', content)
        self.assertIn('language = "python"', content)
        self.assertNotIn("{{PROJECT_NAME}}", content)


class TestEnvrcSync(unittest.TestCase):
    """Web projects get a generated .envrc for profiling defaults."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project = Path(self.tmpdir) / "demokrate"
        self.project.mkdir()
        (self.project / "pyproject.toml").write_text(
            "[project]\nname = 'demokrate'\ndependencies = ['fastapi']\n"
        )

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_sync_creates_envrc_when_missing(self):
        self.assertFalse((self.project / ".envrc").exists())
        setup.sync_template_files(self.project)
        self.assertEqual(
            (self.project / ".envrc").read_text(), "export APP_PROFILE=1\n"
        )

    def test_sync_force_overwrites_envrc(self):
        (self.project / ".envrc").write_text("export APP_PROFILE=0\n")
        setup.sync_template_files(self.project, force=True)
        self.assertEqual(
            (self.project / ".envrc").read_text(), "export APP_PROFILE=1\n"
        )


class TestSyncJustfileCommon(unittest.TestCase):
    """Post-split sync: justfile.common is tool-owned; justfile is user-owned.

    The user's ``justfile`` is never touched by sync. Only
    ``justfile.common`` is regenerated, and --force on it genuinely
    overwrites (no .jolonew dance) because nothing tool-owned carries
    user edits by contract.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.target = Path(self.tmpdir) / "myproj"
        self.target.mkdir()
        (self.target / "pyproject.toml").write_text(
            "[project]\nname = 'myproj'\n"
        )

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_fresh_project_gets_common(self):
        self.assertFalse((self.target / "justfile.common").exists())
        setup.sync_template_files(self.target)
        self.assertTrue((self.target / "justfile.common").exists())
        self.assertIn("perf:", (self.target / "justfile.common").read_text())

    def test_user_justfile_untouched(self):
        # User owns `justfile`. Sync must not read or write it after split.
        (self.target / "justfile").write_text(
            "# user's custom pipeline\n\nhello:\n    echo hi\n"
        )
        setup.sync_template_files(self.target)
        self.assertEqual(
            (self.target / "justfile").read_text(),
            "# user's custom pipeline\n\nhello:\n    echo hi\n",
        )
        # No .jolonew should appear for the user's justfile.
        self.assertFalse((self.target / "justfile.jolonew").exists())

    def test_force_overwrites_common_even_when_edited(self):
        # User committed a hand-edit to justfile.common (shouldn't have,
        # but might). --force is the "nuke template file" escape hatch.
        (self.target / "justfile.common").write_text("# bogus user edit\n")
        setup.sync_template_files(self.target, force=True)
        content = (self.target / "justfile.common").read_text()
        self.assertIn("perf:", content)
        self.assertNotIn("bogus user edit", content)

    def test_no_force_leaves_edited_common_intact(self):
        """Without --force, a hand-edited justfile.common is preserved
        (the "untracked" path — no hash history yet)."""
        (self.target / "justfile.common").write_text("# bogus user edit\n")
        setup.sync_template_files(self.target, force=False)
        self.assertEqual(
            (self.target / "justfile.common").read_text(),
            "# bogus user edit\n",
        )


class TestSyncForceAlwaysOverwrites(unittest.TestCase):
    """`--force` is the "reset to template baseline" escape hatch. It must
    overwrite the user's `justfile` even when flavor detection finds no
    indicator files (no pyproject.toml / package.json / go.mod / etc.).
    Otherwise users with a justfile that drifted into a duplicate-recipe
    state silently get nothing — and the only fix advice ("run --force")
    is a no-op."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.target = Path(self.tmpdir) / "myproj"
        self.target.mkdir()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_force_overwrites_when_flavor_undetectable(self):
        # No flavor signal — but the user's justfile is broken (duplicate
        # `a11y` recipes). --force must still reset it to the generic
        # baseline so the duplicate goes away.
        (self.target / "justfile").write_text(
            "import 'justfile.common'\n\n"
            "a11y *routes:\n    pa11y {{routes}}\n\n"
            "a11y *args:\n    pa11y {{args}}\n"
        )
        setup.sync_template_files(self.target, force=True)
        content = (self.target / "justfile").read_text()
        # The "other" fallback template has run/test stubs.
        self.assertIn("run:", content)
        self.assertNotIn("a11y *routes:", content)
        # Common file gets written too — its single a11y is the only one left.
        self.assertTrue((self.target / "justfile.common").exists())

    def test_no_force_skips_when_flavor_undetectable(self):
        # Without --force, an unflavored project is left alone.
        (self.target / "justfile").write_text("# user content\n")
        setup.sync_template_files(self.target, force=False)
        self.assertEqual(
            (self.target / "justfile").read_text(), "# user content\n"
        )
        self.assertFalse((self.target / "justfile.common").exists())


class TestSyncForceAutoStage(unittest.TestCase):
    """`--force` rewrites template files. Pre-commit will refuse the
    user's next commit ("Your pre-commit configuration is unstaged")
    if `.pre-commit-config.yaml` was rewritten and left unstaged. Stage
    the touched files automatically so the overwrite is visible in
    `git status` and doesn't block commits."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project = Path(self.tmpdir) / "demo"
        self.project.mkdir()
        (self.project / "pyproject.toml").write_text(
            "[project]\nname = 'demo'\n"
        )
        import subprocess as sp

        sp.run(
            ["git", "init", "-q"],
            cwd=str(self.project),
            check=True,
            capture_output=True,
        )
        sp.run(
            ["git", "config", "user.email", "t@example.com"],
            cwd=str(self.project),
            check=True,
            capture_output=True,
        )
        sp.run(
            ["git", "config", "user.name", "t"],
            cwd=str(self.project),
            check=True,
            capture_output=True,
        )

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_force_stages_overwritten_precommit(self):
        # Simulate pre-existing project: write a stale .pre-commit-config.yaml
        # and commit it. Then user --force overwrites it; jolo must stage
        # the rewrite.
        import subprocess as sp

        precommit = self.project / ".pre-commit-config.yaml"
        precommit.write_text("# stale user config\nrepos: []\n")
        sp.run(
            ["git", "add", "."],
            cwd=str(self.project),
            check=True,
            capture_output=True,
        )
        sp.run(
            ["git", "commit", "-q", "-m", "initial"],
            cwd=str(self.project),
            check=True,
            capture_output=True,
            env={
                **os.environ,
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@example.com",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@example.com",
            },
        )
        setup.sync_template_files(self.project, force=True)
        # File was overwritten with the fresh template.
        content = precommit.read_text()
        self.assertIn("trailing-whitespace", content)
        # And the change is staged — porcelain shows "M " (staged) not " M".
        status = sp.run(
            ["git", "status", "--porcelain", ".pre-commit-config.yaml"],
            cwd=str(self.project),
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertTrue(
            status.startswith("M  ") or status.startswith("A  "),
            f"expected staged, got: {status!r}",
        )


class TestSyncMetaFlavor(unittest.TestCase):
    """The jolo meta-repo (`jolo.py` + `_jolo/__init__.py`) is detected as
    the `meta` flavor. `--recreate --force` must regenerate its `justfile`
    to a working shape, and must NOT write `justfile.common` or
    `perf-rig.toml` (those carry user-project recipes the meta-repo has
    no use for)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.target = Path(self.tmpdir) / "jolo"
        self.target.mkdir()
        (self.target / "pyproject.toml").write_text(
            "[project]\nname = 'jolo'\n"
        )
        (self.target / "jolo.py").write_text("# stub\n")
        (self.target / "_jolo").mkdir()
        (self.target / "_jolo" / "__init__.py").write_text("")
        # `templates/` would trip the python-web heuristic; meta detection
        # must short-circuit before then.
        (self.target / "templates").mkdir()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_force_regenerates_justfile_without_shared_import(self):
        # Pre-existing user justfile drifts; --force should reclaim it
        # to the meta template — which has no `import 'justfile.common'`.
        (self.target / "justfile").write_text("# stale\nbogus:\n    false\n")
        setup.sync_template_files(self.target, force=True)
        content = (self.target / "justfile").read_text()
        self.assertIn("ruff check _jolo/ jolo.py", content)
        self.assertNotIn("import 'justfile.common'", content)

    def test_force_does_not_write_justfile_common(self):
        setup.sync_template_files(self.target, force=True)
        self.assertFalse((self.target / "justfile.common").exists())

    def test_force_does_not_write_perf_rig(self):
        setup.sync_template_files(self.target, force=True)
        self.assertFalse((self.target / "perf-rig.toml").exists())


class TestElixirFlavorSync(unittest.TestCase):
    """Elixir web projects must keep their Phoenix templates on recreate."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project = Path(self.tmpdir) / "demo"
        self.project.mkdir()
        (self.project / "mix.exs").write_text(
            "defmodule Demo.MixProject do\nend\n"
        )
        (self.project / "config").mkdir()
        (self.project / "config" / "dev.exs").write_text("import Config\n")
        (self.project / "lib").mkdir()
        (self.project / "lib" / "demo_web").mkdir()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_force_regenerates_elixir_justfile(self):
        (self.project / "justfile").write_text("# stale\n")
        setup.sync_template_files(self.project, force=True)
        content = (self.project / "justfile").read_text()
        self.assertIn("mix phx.server", content)
        self.assertNotIn("No run command configured", content)


class TestMetaSyncSkipsRootTemplates(unittest.TestCase):
    """Meta-project sync must leave root template-owned files alone."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.target = Path(self.tmpdir) / "jolo"
        self.target.mkdir()
        (self.target / "pyproject.toml").write_text(
            "[project]\nname = 'jolo'\n"
        )
        (self.target / "jolo.py").write_text("# stub\n")
        (self.target / "_jolo").mkdir()
        (self.target / "_jolo" / "__init__.py").write_text("")
        (self.target / "templates").mkdir()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_no_force_does_not_overwrite_meta_owned_root_files(self):
        agents = self.target / "AGENTS.md"
        precommit = self.target / ".pre-commit-config.yaml"
        agents.write_text("meta instructions\n")
        precommit.write_text("meta hooks\n")
        setup._save_template_hashes(
            self.target,
            ["AGENTS.md", ".pre-commit-config.yaml"],
            {
                "AGENTS.md": setup._file_hash(agents),
                ".pre-commit-config.yaml": setup._file_hash(precommit),
            },
        )

        setup.sync_template_files(self.target)

        self.assertEqual(agents.read_text(), "meta instructions\n")
        self.assertEqual(precommit.read_text(), "meta hooks\n")
        self.assertFalse((self.target / "AGENTS.md.jolonew").exists())
        self.assertFalse(
            (self.target / ".pre-commit-config.yaml.jolonew").exists()
        )

    def test_force_does_not_overwrite_meta_owned_root_files(self):
        agents = self.target / "AGENTS.md"
        precommit = self.target / ".pre-commit-config.yaml"
        agents.write_text("meta instructions\n")
        precommit.write_text("meta hooks\n")

        setup.sync_template_files(self.target, force=True)

        self.assertEqual(agents.read_text(), "meta instructions\n")
        self.assertEqual(precommit.read_text(), "meta hooks\n")


class TestEnsureLighthouseRunScript(unittest.TestCase):
    """`scripts/lighthouse-run` ships only for web-flavor projects."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.target = Path(self.tmpdir)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_web_flavor_copies_script(self):
        setup.ensure_lighthouse_run_script(self.target, "typescript-web")
        dst = self.target / "scripts" / "lighthouse-run"
        self.assertTrue(dst.exists())
        self.assertTrue(os.access(dst, os.X_OK))

    def test_non_web_flavor_skips(self):
        setup.ensure_lighthouse_run_script(self.target, "python")
        self.assertFalse((self.target / "scripts" / "lighthouse-run").exists())
        self.assertFalse((self.target / "scripts").exists())

    def test_existing_script_not_overwritten(self):
        scripts = self.target / "scripts"
        scripts.mkdir()
        dst = scripts / "lighthouse-run"
        dst.write_text("# user-edited\n")
        setup.ensure_lighthouse_run_script(self.target, "go-web")
        self.assertEqual(dst.read_text(), "# user-edited\n")

    def test_copy_template_files_does_not_leak_lighthouse_run(self):
        """`copy_template_files()` (jolo create's bulk copy) must NOT ship
        `scripts/lighthouse-run` — the per-script ensure helpers handle that
        with flavor gating."""
        setup.copy_template_files(self.target)
        self.assertFalse((self.target / "scripts" / "lighthouse-run").exists())


class TestLighthouseRunIntegration(unittest.TestCase):
    """End-to-end: `_ensure_project_template_files` ships the recipe and
    script together for web flavors and neither for non-web."""

    def setUp(self):
        self.tmpdir = tracked_tmpdir(self)
        self.project = Path(self.tmpdir)

    def test_typescript_web_gets_script_and_recipe(self):
        (self.project / "package.json").write_text('{"name":"x"}')
        (self.project / "tsconfig.json").write_text("{}")
        (self.project / "src" / "components").mkdir(parents=True)

        from _jolo.commands import _ensure_project_template_files

        _ensure_project_template_files(self.project, "demo")

        self.assertTrue((self.project / "scripts" / "lighthouse-run").exists())
        self.assertIn("\nlighthouse ", (self.project / "justfile").read_text())

    def test_non_web_typescript_gets_neither(self):
        (self.project / "package.json").write_text('{"name":"x"}')
        (self.project / "tsconfig.json").write_text("{}")

        from _jolo.commands import _ensure_project_template_files

        _ensure_project_template_files(self.project, "demo")

        self.assertFalse(
            (self.project / "scripts" / "lighthouse-run").exists()
        )
        self.assertNotIn(
            "\nlighthouse ", (self.project / "justfile").read_text()
        )


class TestEnsureGitignore(unittest.TestCase):
    """`_ensure_gitignore` concats the template once, marker-guarded."""

    JOLO_LINE = ".devcontainer/.claude-cache/"

    def setUp(self):
        self.tmpdir = tracked_tmpdir(self)
        self.project = Path(self.tmpdir)
        (self.project / "package.json").write_text('{"name":"x"}')
        (self.project / "tsconfig.json").write_text("{}")

    def _run(self):
        from _jolo.commands import _ensure_project_template_files

        _ensure_project_template_files(self.project, "demo")

    def test_no_gitignore_writes_template(self):
        self._run()
        text = (self.project / ".gitignore").read_text()
        self.assertIn(GITIGNORE_MARKER, text)
        self.assertIn(self.JOLO_LINE, text)

    def test_existing_gitignore_gets_template_appended(self):
        gi = self.project / ".gitignore"
        gi.write_text("# project's own\n*.log\nbuild/\n")
        self._run()
        text = gi.read_text()
        self.assertIn("# project's own", text)
        self.assertIn("build/", text)
        self.assertIn(self.JOLO_LINE, text)

    def test_append_is_idempotent(self):
        gi = self.project / ".gitignore"
        gi.write_text("build/\n")
        self._run()
        self._run()
        text = gi.read_text()
        self.assertEqual(text.count(GITIGNORE_MARKER), 1)
        self.assertEqual(text.count(self.JOLO_LINE), 1)

    def test_existing_gitignore_with_marker_untouched(self):
        gi = self.project / ".gitignore"
        original = f"build/\n{GITIGNORE_MARKER}\n.devcontainer/.pgdata/\n"
        gi.write_text(original)
        self._run()
        self.assertEqual(gi.read_text(), original)


class TestRunUpGatesProjectMutation(unittest.TestCase):
    """Project-tree backfill is gated behind `--recreate`."""

    def setUp(self):
        self.tmpdir = tracked_tmpdir(self)
        self.project = Path(self.tmpdir)
        (self.project / ".git").mkdir()
        for patch in (
            mock.patch(
                "_jolo.commands.find_git_root", return_value=self.project
            ),
            mock.patch(
                "_jolo.commands.load_config",
                return_value={"base_image": "jolo"},
            ),
            mock.patch("_jolo.commands.is_podman_allowed", return_value=False),
            mock.patch("_jolo.commands._sync_config"),
            mock.patch("_jolo.commands._setup_container_env"),
            mock.patch(
                "_jolo.commands.is_container_running", return_value=False
            ),
            mock.patch("_jolo.commands.devcontainer_up", return_value=True),
            mock.patch("_jolo.commands._setup_test_hooks"),
            mock.patch("_jolo.commands.registry.record"),
            mock.patch("_jolo.commands._copy_url_to_clipboard"),
        ):
            self.enterContext(patch)
        self.backfill = self.enterContext(
            mock.patch("_jolo.commands._ensure_project_template_files")
        )
        self.test_gate = self.enterContext(
            mock.patch("_jolo.commands.ensure_test_gate_script")
        )

    def _args(self, *, recreate):
        return argparse.Namespace(
            recreate=recreate,
            force=False,
            mount=[],
            copy=[],
            prompt=None,
            detach=True,
            shell=False,
            run=None,
            agent="claude",
        )

    def _mark_initialized(self):
        from _jolo.setup import TEMPLATE_HASHES_FILE

        marker = self.project / TEMPLATE_HASHES_FILE
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("{}")

    def test_plain_up_errors_when_not_initialized(self):
        from _jolo.commands import run_up_mode

        with self.assertRaises(SystemExit):
            run_up_mode(self._args(recreate=False))
        self.backfill.assert_not_called()
        self.test_gate.assert_not_called()

    def test_plain_up_skips_backfill_when_initialized(self):
        from _jolo.commands import run_up_mode

        self._mark_initialized()
        run_up_mode(self._args(recreate=False))
        self.backfill.assert_not_called()
        self.test_gate.assert_not_called()

    def test_recreate_runs_backfill(self):
        from _jolo.commands import run_up_mode

        run_up_mode(self._args(recreate=True))
        self.backfill.assert_called_once()
        self.test_gate.assert_called_once()


class TestLitellmKeys(unittest.TestCase):
    """Per-project LiteLLM virtual key minting + caching."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = Path(self.tmpdir) / "home"
        (self.home / ".config" / "jolo").mkdir(parents=True)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def _urlopen_returning(self, key):
        class FakeResp:
            def __enter__(self_):
                return self_

            def __exit__(self_, *a):
                return False

            def read(self_):
                return json.dumps({"key": key}).encode()

        return lambda req, timeout=0: FakeResp()

    def test_mints_and_caches_key(self):
        with mock.patch("pathlib.Path.home", return_value=self.home):
            with mock.patch.dict(
                os.environ, {"LITELLM_MASTER_KEY": "sk-master"}, clear=True
            ):
                with mock.patch(
                    "urllib.request.urlopen",
                    self._urlopen_returning("sk-proj-abc"),
                ):
                    key = setup.ensure_litellm_project_key(
                        "myproj", {"litellm_base_url": "http://gw:8088"}
                    )
        self.assertEqual(key, "sk-proj-abc")
        store = json.loads(
            (self.home / ".config" / "jolo" / "litellm-keys.json").read_text()
        )
        self.assertEqual(store["myproj"], "sk-proj-abc")

    def test_reuses_cached_key_without_minting(self):
        store_path = self.home / ".config" / "jolo" / "litellm-keys.json"
        store_path.write_text(json.dumps({"myproj": "sk-cached"}))

        def boom(*a, **k):
            raise AssertionError("should not mint when cached")

        with mock.patch("pathlib.Path.home", return_value=self.home):
            with mock.patch.dict(
                os.environ, {"LITELLM_MASTER_KEY": "sk-master"}, clear=True
            ):
                with mock.patch("urllib.request.urlopen", boom):
                    key = setup.ensure_litellm_project_key(
                        "myproj", {"litellm_base_url": "http://gw:8088"}
                    )
        self.assertEqual(key, "sk-cached")

    def test_returns_none_without_master_key(self):
        # gateway configured, but no master key in env -> graceful None
        with mock.patch("pathlib.Path.home", return_value=self.home):
            with mock.patch.dict(os.environ, {}, clear=True):
                key = setup.ensure_litellm_project_key(
                    "myproj", {"litellm_base_url": "http://gw:8088"}
                )
        self.assertIsNone(key)

    def test_returns_none_without_gateway_url(self):
        # master key present, but gateway address unset -> graceful None
        with mock.patch("pathlib.Path.home", return_value=self.home):
            with mock.patch.dict(
                os.environ, {"LITELLM_MASTER_KEY": "sk-master"}, clear=True
            ):
                key = setup.ensure_litellm_project_key(
                    "myproj", {"litellm_base_url": ""}
                )
        self.assertIsNone(key)

    def test_mint_failure_returns_none(self):
        def raise_urlerror(*a, **k):
            raise OSError("connection refused")

        with mock.patch("pathlib.Path.home", return_value=self.home):
            with mock.patch.dict(
                os.environ, {"LITELLM_MASTER_KEY": "sk-master"}, clear=True
            ):
                with mock.patch("urllib.request.urlopen", raise_urlerror):
                    key = setup.ensure_litellm_project_key(
                        "myproj", {"litellm_base_url": "http://gw:8088"}
                    )
        self.assertIsNone(key)

    def test_key_store_is_owner_only(self):
        with mock.patch("pathlib.Path.home", return_value=self.home):
            with mock.patch.dict(
                os.environ, {"LITELLM_MASTER_KEY": "sk-master"}, clear=True
            ):
                with mock.patch(
                    "urllib.request.urlopen",
                    self._urlopen_returning("sk-proj"),
                ):
                    setup.ensure_litellm_project_key(
                        "modeproj", {"litellm_base_url": "http://gw:8088"}
                    )
        path = self.home / ".config" / "jolo" / "litellm-keys.json"
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_setup_container_env_exports_virtual_key(self):
        import _jolo.commands as commands
        from _jolo.constants import DEFAULT_CONFIG

        ws = Path(self.tmpdir) / "envproj"
        (ws / ".devcontainer").mkdir(parents=True)
        with mock.patch("pathlib.Path.home", return_value=self.home):
            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch.object(
                    commands,
                    "get_secrets",
                    return_value={"LITELLM_MASTER_KEY": "sk-master"},
                ):
                    with mock.patch.object(
                        commands,
                        "ensure_litellm_project_key",
                        return_value="sk-proj",
                    ):
                        with mock.patch.object(
                            commands, "setup_credential_cache"
                        ):
                            with mock.patch.object(
                                commands, "setup_notification_hooks"
                            ):
                                with mock.patch.object(
                                    commands, "setup_emacs_config"
                                ):
                                    with mock.patch.object(
                                        commands, "setup_stash"
                                    ):
                                        commands._setup_container_env(
                                            ws,
                                            DEFAULT_CONFIG,
                                        )
                        self.assertEqual(
                            os.environ.get("LITELLM_VIRTUAL_KEY"), "sk-proj"
                        )


class TestContainerEnvKeys(unittest.TestCase):
    """containerEnv must not leak raw provider keys; routes via gateway."""

    def _env(self):
        import _jolo.container as container

        cfg = json.loads(container.build_devcontainer_json("proj", port=4000))
        return cfg["containerEnv"]

    def test_no_raw_provider_keys(self):
        env = self._env()
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertNotIn("GEMINI_API_KEY", env)
        # OPENAI_API_KEY is present but points at the virtual key, not a real key.
        self.assertEqual(
            env["OPENAI_API_KEY"], "${localEnv:LITELLM_VIRTUAL_KEY}"
        )

    def test_gateway_env_present(self):
        env = self._env()
        # Gateway address comes from the host env LITELLM_HOST (like LLAMA_HOST).
        self.assertEqual(env["LITELLM_HOST"], "${localEnv:LITELLM_HOST}")
        self.assertEqual(env["OPENAI_BASE_URL"], "${localEnv:LITELLM_HOST}/v1")
        self.assertEqual(
            env["LITELLM_VIRTUAL_KEY"], "${localEnv:LITELLM_VIRTUAL_KEY}"
        )

    def test_crawl4ai_env_present(self):
        env = self._env()
        self.assertEqual(env["CRAWL4AI_URL"], "${localEnv:CRAWL4AI_URL}")
        self.assertEqual(
            env["CRAWL4AI_API_TOKEN"],
            "${localEnv:CRAWL4AI_API_TOKEN}",
        )

    def test_nanobanana_exception_retained(self):
        env = self._env()
        self.assertEqual(
            env["NANOBANANA_GEMINI_API_KEY"], "${localEnv:GEMINI_API_KEY}"
        )


class TestPiSharedConfig(unittest.TestCase):
    """pi's config is the host's, shared live by every container."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir)

    def _run(self, ws_name, home, env=None):
        ws = Path(self.tmpdir) / ws_name
        ws.mkdir()
        with mock.patch("pathlib.Path.home", return_value=home):
            with mock.patch.dict(os.environ, env or {}, clear=True):
                jolo.setup_credential_cache(ws)
        return ws

    def test_does_not_wipe_existing_pi_config(self):
        """A login or `pi install` done inside a container must survive."""
        home = Path(self.tmpdir) / "home"
        agent = home / ".pi" / "agent"
        agent.mkdir(parents=True)
        (agent / "auth.json").write_text('{"openai-codex": {"type": "oauth"}}')
        (agent / "npm").mkdir()
        (agent / "npm" / "marker").write_text("installed-in-container")
        settings_content = '{"customSetting": "user-set-value"}'
        (agent / "settings.json").write_text(settings_content)

        self._run("project", home)

        self.assertIn("openai-codex", (agent / "auth.json").read_text())
        self.assertEqual(
            (agent / "npm" / "marker").read_text(), "installed-in-container"
        )
        self.assertEqual(
            (agent / "settings.json").read_text(), settings_content
        )

    def test_creates_per_project_sessions_mount_source(self):
        """podman statfs-aborts the whole run if a mount source is missing."""
        home = Path(self.tmpdir) / "home"
        (home / ".pi" / "agent").mkdir(parents=True)

        ws = self._run("project", home)

        self.assertTrue((ws / ".devcontainer" / ".pi-sessions").is_dir())

    def test_creates_grok_nested_mount_endpoints(self):
        """Both ends of grok's nested mounts must exist, host side included."""
        home = Path(self.tmpdir) / "home"
        (home / ".pi" / "agent").mkdir(parents=True)

        ws = self._run("project", home)

        for nested in ("sessions", "worktrees"):
            self.assertTrue((home / ".grok" / nested).is_dir())
            self.assertTrue(
                (ws / ".devcontainer" / f".grok-{nested}").is_dir()
            )

    def test_disables_grok_native_worktree_hints(self):
        """/fork and /new must not spawn ~/.grok clones; just wt owns worktrees."""
        home = Path(self.tmpdir) / "home"
        (home / ".pi" / "agent").mkdir(parents=True)
        grok_config = home / ".grok" / "config.toml"
        grok_config.parent.mkdir(parents=True)
        grok_config.write_text(
            '[ui]\nyolo = true\n\n[hints]\nfork_worktree_mode = "ask"\n'
        )

        self._run("project", home)

        text = grok_config.read_text()
        self.assertIn('fork_worktree_mode = "never"', text)
        self.assertIn('new_session_worktree_mode = "never"', text)
        self.assertIn("yolo = true", text)
        self.assertNotIn('fork_worktree_mode = "ask"', text)


class TestLitellmGatewayReachable(unittest.TestCase):
    """litellm_gateway_reachable degrades gracefully on any network error."""

    def test_gateway_reachable_true_on_2xx(self):
        class FakeResp:
            status = 200

            def __enter__(self_):
                return self_

            def __exit__(self_, *a):
                return False

            def read(self_):
                return b"I'm alive!"

        with mock.patch("urllib.request.urlopen", lambda *a, **k: FakeResp()):
            self.assertTrue(setup.litellm_gateway_reachable("http://gw:8088"))

    def test_gateway_reachable_false_on_error(self):
        def boom(*a, **k):
            raise OSError("refused")

        with mock.patch("urllib.request.urlopen", boom):
            self.assertFalse(setup.litellm_gateway_reachable("http://gw:8088"))


if __name__ == "__main__":
    unittest.main()
