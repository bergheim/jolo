#!/usr/bin/env python3
"""Tests for filesystem & credential setup."""

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


class TestTemplateSystem(unittest.TestCase):
    """Test .devcontainer template scaffolding."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.tmpdir)

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
        self.assertIn('"image": "localhost/emacs-gui:latest"', content)

    def test_scaffold_devcontainer_uses_config_base_image(self):
        """Should use base_image from config in devcontainer.json."""
        os.chdir(self.tmpdir)
        config = {"base_image": "custom/myimage:v3"}
        jolo.scaffold_devcontainer("testproject", config=config)

        json_file = Path(self.tmpdir) / ".devcontainer" / "devcontainer.json"
        content = json_file.read_text()
        self.assertIn('"image": "custom/myimage:v3"', content)
        self.assertNotIn("localhost/emacs-gui", content)

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


class TestAddUserMounts(unittest.TestCase):
    """Test add_user_mounts() function."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.tmpdir)

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
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.tmpdir)

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
        self.assertIn("notify-done", hooks[0]["hooks"][0]["command"])
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
        self.assertIn("notify-done", hooks[0]["hooks"][0]["command"])
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
        self.assertIn("notify-done", config)
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
        self.assertEqual(config.count("notify-done"), 1)

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
        self.assertNotIn("notify-done", config)


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


if __name__ == "__main__":
    unittest.main()
