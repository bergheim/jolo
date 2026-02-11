#!/usr/bin/env python3
"""Tests for CLI argument parsing, guards, git detection, naming, ports, mounts, copies, lang."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import jolo
except ImportError:
    jolo = None


class TestArgumentParsing(unittest.TestCase):
    """Test command-line argument parsing."""

    def test_no_args_returns_default_mode(self):
        """No arguments should result in default mode."""
        args = jolo.parse_args([])
        self.assertIsNone(args.command)
        self.assertFalse(args.new)

    def test_help_flag(self):
        """--help should exit with usage info."""
        with self.assertRaises(SystemExit) as cm:
            jolo.parse_args(["--help"])
        self.assertEqual(cm.exception.code, 0)

    def test_tree_with_name(self):
        """tree NAME should set name to NAME."""
        args = jolo.parse_args(["tree", "feature-x"])
        self.assertEqual(args.command, "tree")
        self.assertEqual(args.name, "feature-x")

    def test_tree_without_name(self):
        """tree without name should set name to empty string (generate random)."""
        args = jolo.parse_args(["tree"])
        self.assertEqual(args.command, "tree")
        self.assertEqual(args.name, "")

    def test_create_with_name(self):
        """create NAME should set name to NAME."""
        args = jolo.parse_args(["create", "myproject"])
        self.assertEqual(args.command, "create")
        self.assertEqual(args.name, "myproject")

    def test_create_requires_name(self):
        """create without NAME should fail."""
        with self.assertRaises(SystemExit):
            jolo.parse_args(["create"])

    def test_new_flag(self):
        """--new should set new to True."""
        args = jolo.parse_args(["up", "--new"])
        self.assertTrue(args.new)

    def test_new_with_tree(self):
        """--new can combine with tree."""
        args = jolo.parse_args(["tree", "test", "--new"])
        self.assertTrue(args.new)
        self.assertEqual(args.name, "test")

    def test_sync_flag(self):
        """--sync should set sync to True."""
        args = jolo.parse_args(["up", "--sync"])
        self.assertTrue(args.sync)

    def test_sync_with_tree(self):
        """--sync can combine with tree."""
        args = jolo.parse_args(["tree", "test", "--sync"])
        self.assertTrue(args.sync)
        self.assertEqual(args.name, "test")

    def test_sync_default_false(self):
        """No command should leave command as None."""
        args = jolo.parse_args([])
        self.assertIsNone(args.command)
        self.assertFalse(args.sync)


class TestGuards(unittest.TestCase):
    """Test guard conditions and validations."""

    def test_tmux_guard_raises_when_in_tmux(self):
        """Should error when TMUX env var is set."""
        with mock.patch.dict(
            os.environ, {"TMUX": "/tmp/tmux-1000/default,12345,0"}
        ):
            with self.assertRaises(SystemExit) as cm:
                jolo.check_tmux_guard()
            self.assertIn("tmux", str(cm.exception.code).lower())

    def test_tmux_guard_passes_when_not_in_tmux(self):
        """Should pass when TMUX env var is not set."""
        env = os.environ.copy()
        env.pop("TMUX", None)
        with mock.patch.dict(os.environ, env, clear=True):
            # Should not raise
            jolo.check_tmux_guard()


class TestGitDetection(unittest.TestCase):
    """Test git repository detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_find_git_root_at_root(self):
        """Should find git root when at repo root."""
        git_dir = Path(self.tmpdir) / ".git"
        git_dir.mkdir()
        os.chdir(self.tmpdir)

        result = jolo.find_git_root()
        self.assertEqual(result, Path(self.tmpdir))

    def test_find_git_root_in_subdirectory(self):
        """Should find git root when in subdirectory."""
        git_dir = Path(self.tmpdir) / ".git"
        git_dir.mkdir()
        subdir = Path(self.tmpdir) / "src" / "lib"
        subdir.mkdir(parents=True)
        os.chdir(subdir)

        result = jolo.find_git_root()
        self.assertEqual(result, Path(self.tmpdir))

    def test_find_git_root_returns_none_outside_repo(self):
        """Should return None when not in a git repo."""
        os.chdir(self.tmpdir)

        result = jolo.find_git_root()
        self.assertIsNone(result)


class TestRandomNameGeneration(unittest.TestCase):
    """Test random name generation for worktrees."""

    def test_generate_random_name_format(self):
        """Should generate adjective-noun format."""
        name = jolo.generate_random_name()
        parts = name.split("-")
        self.assertEqual(len(parts), 2)

    def test_generate_random_name_uses_wordlists(self):
        """Generated name should use defined word lists."""
        name = jolo.generate_random_name()
        adj, noun = name.split("-")
        self.assertIn(adj, jolo.ADJECTIVES)
        self.assertIn(noun, jolo.NOUNS)

    def test_generate_random_name_is_random(self):
        """Should generate different names (probabilistically)."""
        names = {jolo.generate_random_name() for _ in range(20)}
        # With 10 adjectives and 10 nouns, getting same name 20 times is unlikely
        self.assertGreater(len(names), 1)


class TestContainerNaming(unittest.TestCase):
    """Test container name generation."""

    def test_container_name_from_project(self):
        """Should derive container name from project directory."""
        name = jolo.get_container_name("/home/user/myproject", None)
        self.assertEqual(name, "myproject")

    def test_container_name_with_worktree(self):
        """Should include worktree name in container name."""
        name = jolo.get_container_name("/home/user/myproject", "feature-x")
        self.assertEqual(name, "myproject-feature-x")

    def test_container_name_lowercase(self):
        """Should convert to lowercase."""
        name = jolo.get_container_name("/home/user/MyProject", None)
        self.assertEqual(name, "myproject")


class TestVerboseMode(unittest.TestCase):
    """Test --verbose functionality."""

    def test_verbose_flag(self):
        """--verbose should set verbose to True."""
        args = jolo.parse_args(["up", "--verbose"])
        self.assertTrue(args.verbose)

    def test_verbose_short_flag(self):
        """-v should set verbose to True."""
        args = jolo.parse_args(["up", "-v"])
        self.assertTrue(args.verbose)

    def test_verbose_default_false(self):
        """--verbose should default to False."""
        args = jolo.parse_args([])
        self.assertFalse(args.verbose)


class TestSpawnArgParsing(unittest.TestCase):
    """Test spawn argument parsing."""

    def test_spawn_flag(self):
        """spawn should accept integer."""
        args = jolo.parse_args(["spawn", "5"])
        self.assertEqual(args.count, 5)

    def test_spawn_default_none(self):
        """No command should leave command as None."""
        args = jolo.parse_args([])
        self.assertIsNone(args.command)

    def test_spawn_with_prefix(self):
        """spawn can be combined with --prefix."""
        args = jolo.parse_args(["spawn", "3", "--prefix", "feat"])
        self.assertEqual(args.count, 3)
        self.assertEqual(args.prefix, "feat")

    def test_spawn_with_prompt(self):
        """spawn can be combined with --prompt."""
        args = jolo.parse_args(["spawn", "5", "-p", "do stuff"])
        self.assertEqual(args.count, 5)
        self.assertEqual(args.prompt, "do stuff")

    def test_prefix_default_none(self):
        """--prefix should default to None."""
        args = jolo.parse_args([])
        self.assertIsNone(args.prefix)


class TestAgentHelpers(unittest.TestCase):
    """Test agent configuration helpers."""

    def test_get_agent_command_default(self):
        """Should return first agent's command by default."""
        config = {
            "agents": ["claude", "gemini"],
            "agent_commands": {
                "claude": "claude --dangerously-skip-permissions",
                "gemini": "gemini",
            },
        }
        result = jolo.get_agent_command(config)
        self.assertEqual(result, "claude --dangerously-skip-permissions")

    def test_get_agent_command_specific(self):
        """Should return specific agent's command."""
        config = {
            "agents": ["claude", "gemini"],
            "agent_commands": {
                "claude": "claude --dangerously-skip-permissions",
                "gemini": "gemini",
            },
        }
        result = jolo.get_agent_command(config, agent_name="gemini")
        self.assertEqual(result, "gemini")

    def test_get_agent_command_round_robin(self):
        """Should round-robin through agents by index."""
        config = {
            "agents": ["claude", "gemini", "codex"],
            "agent_commands": {
                "claude": "claude-cmd",
                "gemini": "gemini-cmd",
                "codex": "codex-cmd",
            },
        }
        self.assertEqual(jolo.get_agent_command(config, index=0), "claude-cmd")
        self.assertEqual(jolo.get_agent_command(config, index=1), "gemini-cmd")
        self.assertEqual(jolo.get_agent_command(config, index=2), "codex-cmd")
        self.assertEqual(
            jolo.get_agent_command(config, index=3), "claude-cmd"
        )  # wraps

    def test_get_agent_name_round_robin(self):
        """Should return agent name by index."""
        config = {"agents": ["claude", "gemini", "codex"]}
        self.assertEqual(jolo.get_agent_name(config, index=0), "claude")
        self.assertEqual(jolo.get_agent_name(config, index=1), "gemini")
        self.assertEqual(
            jolo.get_agent_name(config, index=4), "gemini"
        )  # 4 % 3 = 1

    def test_get_agent_command_fallback(self):
        """Should fall back to agent name if no command configured."""
        config = {"agents": ["unknown"], "agent_commands": {}}
        result = jolo.get_agent_command(config, agent_name="unknown")
        self.assertEqual(result, "unknown")


class TestPortAllocation(unittest.TestCase):
    """Test PORT environment variable in devcontainer.json."""

    def test_default_port_in_json(self):
        """Default port should be in the valid range."""
        import json

        result = jolo.build_devcontainer_json("test")
        config = json.loads(result)
        port = int(config["containerEnv"]["PORT"])
        self.assertGreaterEqual(port, jolo.PORT_MIN)
        self.assertLessEqual(port, jolo.PORT_MAX)

    def test_custom_port_in_json(self):
        """Custom port should be set."""
        import json

        result = jolo.build_devcontainer_json("test", port=4005)
        config = json.loads(result)
        self.assertEqual(config["containerEnv"]["PORT"], "4005")


class TestMountArgParsing(unittest.TestCase):
    """Test --mount argument parsing."""

    def test_mount_flag_single(self):
        """--mount should accept source:target."""
        args = jolo.parse_args(["up", "--mount", "~/data:data"])
        self.assertEqual(args.mount, ["~/data:data"])

    def test_mount_flag_multiple(self):
        """--mount can be specified multiple times."""
        args = jolo.parse_args(["up", "--mount", "~/a:a", "--mount", "~/b:b"])
        self.assertEqual(args.mount, ["~/a:a", "~/b:b"])

    def test_mount_default_empty(self):
        """--mount should default to empty list."""
        args = jolo.parse_args([])
        self.assertEqual(args.mount, [])

    def test_mount_readonly(self):
        """--mount should accept :ro suffix."""
        args = jolo.parse_args(["up", "--mount", "~/data:data:ro"])
        self.assertEqual(args.mount, ["~/data:data:ro"])


class TestCopyArgParsing(unittest.TestCase):
    """Test --copy argument parsing."""

    def test_copy_flag_single(self):
        """--copy should accept source:target."""
        args = jolo.parse_args(["up", "--copy", "~/config.json:config.json"])
        self.assertEqual(args.copy, ["~/config.json:config.json"])

    def test_copy_flag_multiple(self):
        """--copy can be specified multiple times."""
        args = jolo.parse_args(
            ["up", "--copy", "~/a.json", "--copy", "~/b.json:b.json"]
        )
        self.assertEqual(args.copy, ["~/a.json", "~/b.json:b.json"])

    def test_copy_default_empty(self):
        """--copy should default to empty list."""
        args = jolo.parse_args([])
        self.assertEqual(args.copy, [])

    def test_copy_without_target(self):
        """--copy should accept source without target."""
        args = jolo.parse_args(["up", "--copy", "~/config.json"])
        self.assertEqual(args.copy, ["~/config.json"])


class TestMountAndCopyTogether(unittest.TestCase):
    """Test --mount and --copy used together."""

    def test_mount_and_copy_combined(self):
        """--mount and --copy can be used together."""
        args = jolo.parse_args(
            [
                "up",
                "--mount",
                "~/data:data",
                "--copy",
                "~/config.json",
                "--mount",
                "~/other:other:ro",
                "--copy",
                "~/secrets.json:secrets/keys.json",
            ]
        )
        self.assertEqual(len(args.mount), 2)
        self.assertEqual(len(args.copy), 2)
        self.assertEqual(args.mount, ["~/data:data", "~/other:other:ro"])
        self.assertEqual(
            args.copy, ["~/config.json", "~/secrets.json:secrets/keys.json"]
        )


class TestMountParsing(unittest.TestCase):
    """Test parse_mount() function."""

    def test_parse_mount_relative_target(self):
        """Relative target should resolve to workspace."""
        result = jolo.parse_mount("~/data:foo", "myproj")
        self.assertEqual(result["target"], "/workspaces/myproj/foo")
        self.assertFalse(result["readonly"])

    def test_parse_mount_absolute_target(self):
        """Absolute target should be used as-is."""
        result = jolo.parse_mount("~/data:/mnt/data", "myproj")
        self.assertEqual(result["target"], "/mnt/data")

    def test_parse_mount_readonly(self):
        """:ro suffix should set readonly."""
        result = jolo.parse_mount("~/data:foo:ro", "myproj")
        self.assertTrue(result["readonly"])
        self.assertEqual(result["target"], "/workspaces/myproj/foo")

    def test_parse_mount_absolute_readonly(self):
        """Absolute target with :ro suffix."""
        result = jolo.parse_mount("~/data:/mnt/data:ro", "myproj")
        self.assertTrue(result["readonly"])
        self.assertEqual(result["target"], "/mnt/data")

    def test_parse_mount_expands_tilde(self):
        """Should expand ~ in source path."""
        result = jolo.parse_mount("~/data:foo", "myproj")
        self.assertNotIn("~", result["source"])
        self.assertTrue(result["source"].startswith("/"))

    def test_parse_mount_default_readwrite(self):
        """Default should be read-write."""
        result = jolo.parse_mount("~/data:foo", "myproj")
        self.assertFalse(result["readonly"])

    def test_parse_mount_nested_target(self):
        """Nested relative target should work."""
        result = jolo.parse_mount("~/data:some/nested/path", "myproj")
        self.assertEqual(
            result["target"], "/workspaces/myproj/some/nested/path"
        )


class TestCopyParsing(unittest.TestCase):
    """Test parse_copy() function."""

    def test_parse_copy_with_target(self):
        """Copy with target should resolve correctly."""
        result = jolo.parse_copy("~/config.json:app/config.json", "myproj")
        self.assertEqual(
            result["target"], "/workspaces/myproj/app/config.json"
        )

    def test_parse_copy_basename_only(self):
        """Copy without target should use basename."""
        result = jolo.parse_copy("~/config.json", "myproj")
        self.assertEqual(result["target"], "/workspaces/myproj/config.json")

    def test_parse_copy_absolute_target(self):
        """Copy with absolute target should use as-is."""
        result = jolo.parse_copy("~/config.json:/tmp/config.json", "myproj")
        self.assertEqual(result["target"], "/tmp/config.json")

    def test_parse_copy_expands_tilde(self):
        """Should expand ~ in source path."""
        result = jolo.parse_copy("~/config.json", "myproj")
        self.assertNotIn("~", result["source"])
        self.assertTrue(result["source"].startswith("/"))

    def test_parse_copy_nested_source(self):
        """Nested source path should work."""
        result = jolo.parse_copy("~/some/nested/config.json", "myproj")
        self.assertEqual(result["target"], "/workspaces/myproj/config.json")
        self.assertTrue(result["source"].endswith("some/nested/config.json"))


class TestLangArgParsing(unittest.TestCase):
    """Test --lang argument parsing."""

    def test_lang_flag_single(self):
        """--lang should accept a single language."""
        args = jolo.parse_args(["create", "test", "--lang", "python"])
        self.assertEqual(args.lang, ["python"])

    def test_lang_flag_comma_separated(self):
        """--lang should accept comma-separated values."""
        args = jolo.parse_args(
            ["create", "test", "--lang", "python,typescript"]
        )
        self.assertEqual(args.lang, ["python", "typescript"])

    def test_lang_flag_multiple_values(self):
        """--lang should handle multiple comma-separated values."""
        args = jolo.parse_args(["create", "test", "--lang", "python,go,rust"])
        self.assertEqual(args.lang, ["python", "go", "rust"])

    def test_lang_default_none(self):
        """--lang should default to None."""
        args = jolo.parse_args([])
        self.assertIsNone(args.lang)

    def test_lang_valid_values(self):
        """--lang should accept all valid language values."""
        valid_langs = [
            "python",
            "go",
            "typescript",
            "rust",
            "shell",
            "prose",
            "other",
        ]
        for lang in valid_langs:
            args = jolo.parse_args(["create", "test", "--lang", lang])
            self.assertEqual(args.lang, [lang])

    def test_lang_invalid_value_raises_error(self):
        """--lang should reject invalid language values."""
        with self.assertRaises(SystemExit):
            jolo.parse_args(["create", "test", "--lang", "invalid_language"])

    def test_lang_mixed_valid_invalid_raises_error(self):
        """--lang should reject if any value is invalid."""
        with self.assertRaises(SystemExit):
            jolo.parse_args(["create", "test", "--lang", "python,invalid"])

    def test_lang_with_create(self):
        """--lang can combine with create."""
        args = jolo.parse_args(
            ["create", "myproject", "--lang", "python,typescript"]
        )
        self.assertEqual(args.name, "myproject")
        self.assertEqual(args.lang, ["python", "typescript"])

    def test_lang_is_optional(self):
        """--lang is not required for any command."""
        # Should not raise
        args = jolo.parse_args(["create", "myproject"])
        self.assertIsNone(args.lang)

    def test_lang_whitespace_handling(self):
        """--lang should handle values with whitespace around commas."""
        args = jolo.parse_args(
            ["create", "test", "--lang", "python, typescript, go"]
        )
        self.assertEqual(args.lang, ["python", "typescript", "go"])


class TestLanguageCodeMapping(unittest.TestCase):
    """Test the language display name to code mapping."""

    def test_mapping_exists(self):
        """LANGUAGE_CODE_MAP should exist."""
        self.assertTrue(hasattr(jolo, "LANGUAGE_CODE_MAP"))

    def test_all_options_have_mapping(self):
        """Every LANGUAGE_OPTIONS entry should have a code mapping."""
        for option in jolo.LANGUAGE_OPTIONS:
            self.assertIn(
                option, jolo.LANGUAGE_CODE_MAP, f"Missing mapping for {option}"
            )

    def test_mapping_values_are_valid(self):
        """All mapped codes should be in VALID_LANGUAGES."""
        for option, code in jolo.LANGUAGE_CODE_MAP.items():
            self.assertIn(
                code,
                jolo.VALID_LANGUAGES,
                f"Code '{code}' for '{option}' not in VALID_LANGUAGES",
            )


if __name__ == "__main__":
    unittest.main()
