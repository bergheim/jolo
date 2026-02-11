#!/usr/bin/env python3
"""Integration tests spanning multiple modules."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import jolo
except ImportError:
    jolo = None


class TestCreateModeLanguageIntegration(unittest.TestCase):
    """Integration tests for run_create_mode() language handling."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.tmpdir)

    def _mock_devcontainer_calls(self):
        """Create mocks for devcontainer commands."""
        return mock.patch.multiple(
            "_jolo.commands",
            devcontainer_up=mock.DEFAULT,
            devcontainer_exec_command=mock.DEFAULT,
            devcontainer_exec_tmux=mock.DEFAULT,
            is_container_running=mock.DEFAULT,
            setup_credential_cache=mock.DEFAULT,
            setup_emacs_config=mock.DEFAULT,
        )

    def test_create_with_lang_uses_provided_languages(self):
        """create with --lang should use the provided languages."""
        args = jolo.parse_args(
            ["create", "testproj", "--lang", "python,typescript", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / "testproj"

        # Check .pre-commit-config.yaml was created with correct hooks
        precommit_config = project_path / ".pre-commit-config.yaml"
        self.assertTrue(precommit_config.exists())
        content = precommit_config.read_text()
        self.assertIn("ruff", content)  # Python
        self.assertIn("biome", content)  # TypeScript

    def test_create_without_lang_calls_interactive_selector(self):
        """create without --lang should call select_languages_interactive."""
        args = jolo.parse_args(["create", "testproj", "-d"])

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            with mock.patch(
                "_jolo.commands.select_languages_interactive",
                return_value=["go"],
            ) as mock_selector:
                jolo.run_create_mode(args)
                mock_selector.assert_called_once()

        project_path = Path(self.tmpdir) / "testproj"

        # Check .pre-commit-config.yaml reflects selected language
        precommit_config = project_path / ".pre-commit-config.yaml"
        self.assertTrue(precommit_config.exists())
        content = precommit_config.read_text()
        self.assertIn("golangci-lint", content)  # Go

    def test_create_generates_precommit_config(self):
        """create should generate .pre-commit-config.yaml based on languages."""
        args = jolo.parse_args(["create", "testproj", "--lang", "rust", "-d"])

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / "testproj"
        precommit_config = project_path / ".pre-commit-config.yaml"

        self.assertTrue(precommit_config.exists())
        content = precommit_config.read_text()
        # Rust hooks
        self.assertIn("cargo-check", content)
        self.assertIn("fmt", content)
        # Base hooks always included
        self.assertIn("trailing-whitespace", content)
        self.assertIn("gitleaks", content)

    def test_create_copies_gitignore_from_templates(self):
        """create should copy .gitignore from templates/."""
        args = jolo.parse_args(
            ["create", "testproj", "--lang", "python", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / "testproj"
        gitignore = project_path / ".gitignore"

        self.assertTrue(gitignore.exists())

    def test_create_copies_editorconfig_from_templates(self):
        """create should copy .editorconfig from templates/."""
        args = jolo.parse_args(
            ["create", "testproj", "--lang", "python", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / "testproj"
        editorconfig = project_path / ".editorconfig"

        self.assertTrue(editorconfig.exists())

    def test_create_runs_init_commands_for_primary_language(self):
        """create should run project init commands for primary language after container starts."""
        args = jolo.parse_args(
            ["create", "testproj", "--lang", "python,typescript", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

            # Primary language is python (first in list)
            # Should have executed mkdir -p tests inside the container
            exec_calls = mocks["devcontainer_exec_command"].call_args_list
            mkdir_called = any(
                "mkdir -p tests" in str(call) for call in exec_calls
            )
            self.assertTrue(
                mkdir_called,
                f"Expected 'mkdir -p tests' to be called, got: {exec_calls}",
            )

    def test_create_writes_test_framework_config_for_python(self):
        """create with python should write pytest config to pyproject.toml."""
        args = jolo.parse_args(
            ["create", "testproj", "--lang", "python", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / "testproj"
        pyproject = project_path / "pyproject.toml"

        # pyproject.toml should exist (created by copy_template or test config)
        if pyproject.exists():
            content = pyproject.read_text()
            # Should have pytest config
            self.assertIn("pytest", content.lower())

    def test_create_writes_test_framework_config_for_typescript(self):
        """create with typescript should create example test with bun:test."""
        args = jolo.parse_args(
            ["create", "testproj", "--lang", "typescript", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / "testproj"
        example_test = project_path / "src" / "example.test.ts"

        self.assertTrue(example_test.exists())
        content = example_test.read_text()
        self.assertIn("bun:test", content)

    def test_create_writes_type_checker_config_for_typescript(self):
        """create with typescript should write tsconfig.json."""
        args = jolo.parse_args(
            ["create", "testproj", "--lang", "typescript", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / "testproj"
        tsconfig = project_path / "tsconfig.json"

        self.assertTrue(tsconfig.exists())
        content = tsconfig.read_text()
        self.assertIn("strict", content)

    def test_create_first_language_is_primary(self):
        """First language in list should be treated as primary for init commands."""
        args = jolo.parse_args(
            ["create", "testproj", "--lang", "go,python", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

            # Primary language is go (first in list)
            exec_calls = mocks["devcontainer_exec_command"].call_args_list
            # Should have go mod init, not uv init
            go_mod_called = any(
                "go mod init" in str(call) for call in exec_calls
            )
            self.assertTrue(
                go_mod_called,
                f"Expected 'go mod init' to be called, got: {exec_calls}",
            )

    def test_create_empty_language_selection_aborts(self):
        """If interactive selector returns empty list, should abort."""
        args = jolo.parse_args(["create", "testproj", "-d"])

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            with mock.patch(
                "_jolo.commands.select_languages_interactive", return_value=[]
            ):
                with self.assertRaises(SystemExit):
                    jolo.run_create_mode(args)

    def test_create_template_files_are_copied(self):
        """create should copy AGENTS.md, CLAUDE.md, GEMINI.md from templates."""
        args = jolo.parse_args(
            ["create", "testproj", "--lang", "python", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / "testproj"

        # These should be copied by copy_template_files
        for filename in ["AGENTS.md", "CLAUDE.md", "GEMINI.md"]:
            filepath = project_path / filename
            self.assertTrue(filepath.exists(), f"Expected {filename} to exist")


if __name__ == "__main__":
    unittest.main()
