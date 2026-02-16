#!/usr/bin/env python3
"""Tests for config generation (gitignore, pre-commit, editorconfig, language tools)."""

import json
import unittest
from pathlib import Path
from unittest import mock

try:
    import jolo
except ImportError:
    jolo = None


class TestGitignoreTemplate(unittest.TestCase):
    """Test universal .gitignore template."""

    def setUp(self):
        self.template_path = (
            Path(__file__).parent.parent / "templates" / ".gitignore"
        )

    def test_gitignore_template_exists(self):
        """templates/.gitignore should exist."""
        self.assertTrue(
            self.template_path.exists(), f"Missing {self.template_path}"
        )

    def test_gitignore_contains_python_patterns(self):
        """Should contain Python ignore patterns."""
        content = self.template_path.read_text()
        self.assertIn("__pycache__", content)
        self.assertIn(".venv", content)
        self.assertIn("*.pyc", content)

    def test_gitignore_contains_node_patterns(self):
        """Should contain Node.js ignore patterns."""
        content = self.template_path.read_text()
        self.assertIn("node_modules/", content)
        self.assertIn("dist/", content)

    def test_gitignore_contains_rust_patterns(self):
        """Should contain Rust ignore patterns."""
        content = self.template_path.read_text()
        self.assertIn("target/", content)

    def test_gitignore_contains_general_patterns(self):
        """Should contain general ignore patterns."""
        content = self.template_path.read_text()
        self.assertIn(".env", content)
        self.assertIn(".DS_Store", content)
        self.assertIn("*.log", content)


class TestPreCommitTemplate(unittest.TestCase):
    """Test pre-commit template configuration."""

    def test_pre_commit_template_exists(self):
        """templates/.pre-commit-config.yaml should exist."""
        template_path = (
            Path(__file__).parent.parent
            / "templates"
            / ".pre-commit-config.yaml"
        )
        self.assertTrue(
            template_path.exists(), f"Template not found at {template_path}"
        )

    def test_pre_commit_template_contains_gitleaks_hook(self):
        """Template should contain gitleaks hook."""
        template_path = (
            Path(__file__).parent.parent
            / "templates"
            / ".pre-commit-config.yaml"
        )
        content = template_path.read_text()

        # Check that gitleaks hook is configured
        self.assertIn("id: gitleaks", content, "Should have gitleaks hook id")

    def test_pre_commit_template_gitleaks_repo_url(self):
        """Gitleaks repo URL should be correct."""
        template_path = (
            Path(__file__).parent.parent
            / "templates"
            / ".pre-commit-config.yaml"
        )
        content = template_path.read_text()

        self.assertIn(
            "repo: https://github.com/gitleaks/gitleaks",
            content,
            "Gitleaks repo URL should be https://github.com/gitleaks/gitleaks",
        )


class TestEditorConfigTemplate(unittest.TestCase):
    """Test templates/.editorconfig file."""

    @classmethod
    def setUpClass(cls):
        """Read the editorconfig file once for all tests."""
        cls.template_path = (
            Path(__file__).parent.parent / "templates" / ".editorconfig"
        )
        if cls.template_path.exists():
            cls.content = cls.template_path.read_text()
            cls.lines = cls.content.strip().split("\n")
        else:
            cls.content = None
            cls.lines = []

    def test_editorconfig_exists(self):
        """templates/.editorconfig should exist."""
        self.assertTrue(
            self.template_path.exists(),
            f"Expected {self.template_path} to exist",
        )

    def test_root_true(self):
        """Should have root = true."""
        self.assertIn("root = true", self.content)

    def test_default_indent_4_spaces(self):
        """Default indent should be 4 spaces."""
        # Find the [*] section and check indent settings
        self.assertIn("indent_style = space", self.content)
        self.assertIn("indent_size = 4", self.content)

    def test_go_files_use_tabs(self):
        """Go files (*.go) should use tabs."""
        # Find the [*.go] section
        self.assertIn("[*.go]", self.content)
        # Check that indent_style = tab appears after [*.go]
        go_section_start = self.content.index("[*.go]")
        go_section = self.content[go_section_start:]
        # Check for tab indent in Go section (before next section or end)
        next_section = go_section.find("\n[", 1)
        if next_section != -1:
            go_section = go_section[:next_section]
        self.assertIn("indent_style = tab", go_section)

    def test_makefile_uses_tabs(self):
        """Makefile should use tabs."""
        self.assertIn("[Makefile]", self.content)
        # Check that indent_style = tab appears after [Makefile]
        makefile_section_start = self.content.index("[Makefile]")
        makefile_section = self.content[makefile_section_start:]
        next_section = makefile_section.find("\n[", 1)
        if next_section != -1:
            makefile_section = makefile_section[:next_section]
        self.assertIn("indent_style = tab", makefile_section)

    def test_end_of_line_lf(self):
        """Should have end_of_line = lf."""
        self.assertIn("end_of_line = lf", self.content)

    def test_charset_utf8(self):
        """Should have charset = utf-8."""
        self.assertIn("charset = utf-8", self.content)


class TestGetProjectInitCommands(unittest.TestCase):
    """Test get_project_init_commands() function."""

    def test_function_exists(self):
        """get_project_init_commands should exist."""
        self.assertTrue(hasattr(jolo, "get_project_init_commands"))
        self.assertTrue(callable(jolo.get_project_init_commands))

    def test_python_creates_tests_dir(self):
        """Python should create tests directory."""
        commands = jolo.get_project_init_commands("python", "myproject")
        self.assertIn(["mkdir", "-p", "tests"], commands)

    def test_typescript_returns_bun_init(self):
        """TypeScript should return bun commands."""
        commands = jolo.get_project_init_commands("typescript", "myproject")
        self.assertIn(["bun", "init", "-y"], commands)
        self.assertIn(
            [
                "bun",
                "add",
                "elysia",
                "@elysiajs/html",
                "@elysiajs/static",
                "@kitajs/html",
                "htmx.org",
            ],
            commands,
        )
        self.assertIn(["just", "setup"], commands)

    def test_get_scaffold_files_exists(self):
        """get_scaffold_files should exist."""
        self.assertTrue(hasattr(jolo, "get_scaffold_files"))
        self.assertTrue(callable(jolo.get_scaffold_files))

    def test_typescript_returns_beth_scaffold_files(self):
        """TypeScript should return BETH scaffold files."""
        files = jolo.get_scaffold_files("typescript")
        rel_paths = [f[0] for f in files]
        self.assertIn("src/index.tsx", rel_paths)
        self.assertIn("src/styles.css", rel_paths)
        self.assertIn("src/pages/home.tsx", rel_paths)
        self.assertIn("src/components/layout.tsx", rel_paths)
        self.assertIn("public/.gitkeep", rel_paths)

    def test_python_returns_no_scaffold_files(self):
        """Python should return no additional scaffold files (for now)."""
        files = jolo.get_scaffold_files("python")
        self.assertEqual(files, [])

    def test_typescript_bare_returns_no_scaffold_files(self):
        """Bare TypeScript should skip BETH scaffold files."""
        files = jolo.get_scaffold_files("typescript", bare=True)
        self.assertEqual(files, [])

    def test_typescript_bare_init_commands_skip_elysia(self):
        """Bare TypeScript should not install BETH deps."""
        commands = jolo.get_project_init_commands(
            "typescript", "myproject", bare=True
        )
        flat = str(commands)
        self.assertNotIn("elysia", flat)
        self.assertIn(["bun", "init", "-y"], commands)

    def test_typescript_bare_justfile_uses_ts_not_tsx(self):
        """Bare TypeScript justfile should reference .ts files."""
        content = jolo.get_justfile_content(
            "typescript", "myproject", bare=True
        )
        self.assertIn("src/index.ts", content)
        self.assertNotIn(".tsx", content)

    def test_typescript_bare_test_has_no_elysia(self):
        """Bare TypeScript example test should not import elysia."""
        config = jolo.get_test_framework_config("typescript", bare=True)
        self.assertNotIn("elysia", config["example_test_content"])
        self.assertIn("bun:test", config["example_test_content"])

    def test_go_returns_go_mod_init(self):
        """Go should return go mod init with project name."""
        commands = jolo.get_project_init_commands("go", "myproject")
        self.assertIn(["go", "mod", "init", "myproject"], commands)

    def test_rust_returns_cargo_init(self):
        """Rust should return cargo init commands."""
        commands = jolo.get_project_init_commands("rust", "myproject")
        self.assertIn(["cargo", "init", "--name", "myproject"], commands)

    def test_shell_returns_src_mkdir(self):
        """Shell should create src directory."""
        commands = jolo.get_project_init_commands("shell", "myproject")
        self.assertIn(["mkdir", "-p", "src"], commands)

    def test_prose_returns_docs_or_src_mkdir(self):
        """Prose should create docs or src directory."""
        commands = jolo.get_project_init_commands("prose", "myproject")
        # Should have at least one directory creation
        has_docs = ["mkdir", "-p", "docs"] in commands
        has_src = ["mkdir", "-p", "src"] in commands
        self.assertTrue(
            has_docs or has_src, f"Expected docs or src mkdir, got: {commands}"
        )

    def test_other_returns_src_mkdir(self):
        """Other language should create src directory."""
        commands = jolo.get_project_init_commands("other", "myproject")
        self.assertIn(["mkdir", "-p", "src"], commands)

    def test_returns_list_of_lists(self):
        """Should return a list of command lists."""
        commands = jolo.get_project_init_commands("python", "myproject")
        self.assertIsInstance(commands, list)
        for cmd in commands:
            self.assertIsInstance(cmd, list)
            for part in cmd:
                self.assertIsInstance(part, str)

    def test_project_name_used_in_go_command(self):
        """Project name should be used in go mod init."""
        commands = jolo.get_project_init_commands("go", "my-awesome-app")
        go_mod_cmd = ["go", "mod", "init", "my-awesome-app"]
        self.assertIn(go_mod_cmd, commands)

    def test_project_name_used_in_rust_command(self):
        """Project name should be used in cargo init."""
        commands = jolo.get_project_init_commands("rust", "my-awesome-app")
        cargo_cmd = ["cargo", "init", "--name", "my-awesome-app"]
        self.assertIn(cargo_cmd, commands)

    def test_unknown_language_returns_src_mkdir(self):
        """Unknown language should fall back to src mkdir."""
        commands = jolo.get_project_init_commands("unknown_lang", "myproject")
        self.assertIn(["mkdir", "-p", "src"], commands)


class TestSelectLanguagesInteractive(unittest.TestCase):
    """Test select_languages_interactive() function."""

    def test_function_exists(self):
        """select_languages_interactive function should exist."""
        self.assertTrue(hasattr(jolo, "select_languages_interactive"))
        self.assertTrue(callable(jolo.select_languages_interactive))

    def test_all_languages_available(self):
        """All valid languages should be available as options."""
        self.assertTrue(hasattr(jolo, "LANGUAGE_OPTIONS"))
        options = jolo.LANGUAGE_OPTIONS
        expected = [
            "Python",
            "Go",
            "TypeScript",
            "Rust",
            "Shell",
            "Prose/Docs",
            "Other",
        ]
        self.assertEqual(options, expected)

    def test_fallback_parses_comma_separated_numbers(self):
        """Fallback should parse comma-separated numbers."""
        with mock.patch("shutil.which", return_value=None):
            with mock.patch("builtins.input", return_value="1,3"):
                result = jolo.select_languages_interactive()
        self.assertEqual(result, ["python", "typescript"])

    def test_fallback_handles_empty_input(self):
        """Fallback should return empty list on empty input."""
        with mock.patch("shutil.which", return_value=None):
            with mock.patch("builtins.input", return_value=""):
                result = jolo.select_languages_interactive()
        self.assertEqual(result, [])

    def test_fallback_handles_invalid_numbers(self):
        """Fallback should skip invalid numbers gracefully."""
        with mock.patch("shutil.which", return_value=None):
            with mock.patch("builtins.input", return_value="1,99,2"):
                result = jolo.select_languages_interactive()
        self.assertEqual(result, ["python", "go"])

    def test_fallback_single_selection(self):
        """Fallback should handle single selection."""
        with mock.patch("shutil.which", return_value=None):
            with mock.patch("builtins.input", return_value="6"):
                result = jolo.select_languages_interactive()
        self.assertEqual(result, ["prose"])

    def test_fallback_keyboard_interrupt_returns_empty(self):
        """Should return empty list on keyboard interrupt."""
        with mock.patch("shutil.which", return_value=None):
            with mock.patch("builtins.input", side_effect=KeyboardInterrupt):
                result = jolo.select_languages_interactive()
        self.assertEqual(result, [])


class TestGetTestFrameworkConfig(unittest.TestCase):
    """Test get_test_framework_config() function."""

    def test_function_exists(self):
        """get_test_framework_config should exist."""
        self.assertTrue(hasattr(jolo, "get_test_framework_config"))
        self.assertTrue(callable(jolo.get_test_framework_config))

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = jolo.get_test_framework_config("python")
        self.assertIsInstance(result, dict)

    def test_dict_has_required_keys(self):
        """Return dict should have config_file, config_content, example_test_file, example_test_content."""
        result = jolo.get_test_framework_config("python")
        required_keys = [
            "config_file",
            "config_content",
            "example_test_file",
            "example_test_content",
        ]
        for key in required_keys:
            self.assertIn(key, result, f"Missing key: {key}")

    # Python (pytest) tests
    def test_python_config_file(self):
        """Python should use pyproject.toml for config."""
        result = jolo.get_test_framework_config("python")
        self.assertEqual(result["config_file"], "pyproject.toml")

    def test_python_config_content_pytest(self):
        """Python config should include pytest configuration."""
        result = jolo.get_test_framework_config("python")
        self.assertIn("[tool.pytest.ini_options]", result["config_content"])

    def test_python_example_test_file(self):
        """Python should create tests/test_main.py."""
        result = jolo.get_test_framework_config("python")
        self.assertEqual(result["example_test_file"], "tests/test_main.py")

    def test_python_example_test_content(self):
        """Python example test should use pytest."""
        result = jolo.get_test_framework_config("python")
        content = result["example_test_content"]
        self.assertIn("def test_", content)
        self.assertIn("assert", content)

    # TypeScript (bun test) tests
    def test_typescript_config_file(self):
        """TypeScript has no config file needed (bun has built-in testing)."""
        result = jolo.get_test_framework_config("typescript")
        self.assertTrue(
            result["config_file"] is None or result["config_file"] == "",
            f"Expected None or empty, got: {result['config_file']}",
        )

    def test_typescript_config_content_bun(self):
        """TypeScript config should mention bun built-in testing."""
        result = jolo.get_test_framework_config("typescript")
        content = result["config_content"]
        self.assertIn("bun", content.lower())

    def test_typescript_example_test_file(self):
        """TypeScript should create src/example.test.ts."""
        result = jolo.get_test_framework_config("typescript")
        self.assertEqual(result["example_test_file"], "src/example.test.ts")

    def test_typescript_example_test_content(self):
        """TypeScript example test should use bun:test syntax."""
        result = jolo.get_test_framework_config("typescript")
        content = result["example_test_content"]
        self.assertIn("bun:test", content)
        self.assertIn("describe", content)
        self.assertIn("it(", content)
        self.assertIn("expect", content)

    # Go (built-in testing) tests
    def test_go_config_file_none(self):
        """Go has no extra config file needed (built-in testing)."""
        result = jolo.get_test_framework_config("go")
        # Config file can be None or empty string for built-in testing
        self.assertTrue(
            result["config_file"] is None or result["config_file"] == "",
            f"Expected None or empty, got: {result['config_file']}",
        )

    def test_go_config_content_empty_or_comment(self):
        """Go config content should be empty or just a comment."""
        result = jolo.get_test_framework_config("go")
        # Config content can be empty or just explain that no config is needed
        self.assertTrue(
            result["config_content"] == ""
            or "built-in" in result["config_content"].lower(),
            f"Expected empty or built-in info, got: {result['config_content']}",
        )

    def test_go_example_test_file(self):
        """Go should create example_test.go."""
        result = jolo.get_test_framework_config("go")
        self.assertTrue(result["example_test_file"].endswith("_test.go"))

    def test_go_example_test_content(self):
        """Go example test should use testing package."""
        result = jolo.get_test_framework_config("go")
        content = result["example_test_content"]
        self.assertIn("testing", content)
        self.assertIn("func Test", content)

    # Rust (built-in testing) tests
    def test_rust_config_file_none(self):
        """Rust has no extra config file needed (built-in testing)."""
        result = jolo.get_test_framework_config("rust")
        # Config file can be None or empty string for built-in testing
        self.assertTrue(
            result["config_file"] is None or result["config_file"] == "",
            f"Expected None or empty, got: {result['config_file']}",
        )

    def test_rust_config_content_empty_or_comment(self):
        """Rust config content should be empty or just a comment."""
        result = jolo.get_test_framework_config("rust")
        # Config content can be empty or just explain that no config is needed
        self.assertTrue(
            result["config_content"] == ""
            or "built-in" in result["config_content"].lower(),
            f"Expected empty or built-in info, got: {result['config_content']}",
        )

    def test_rust_example_test_file(self):
        """Rust example test location (src/lib.rs or separate file)."""
        result = jolo.get_test_framework_config("rust")
        # Rust tests can be in lib.rs, main.rs, or a tests/ directory
        self.assertTrue(
            "src/" in result["example_test_file"]
            or "tests/" in result["example_test_file"],
            f"Expected src/ or tests/ path, got: {result['example_test_file']}",
        )

    def test_rust_example_test_content(self):
        """Rust example test should use #[test] attribute."""
        result = jolo.get_test_framework_config("rust")
        content = result["example_test_content"]
        self.assertIn("#[test]", content)
        self.assertIn("fn test_", content)
        self.assertIn("assert", content)

    # Unknown language handling
    def test_unknown_language_returns_empty_config(self):
        """Unknown language should return empty/None values."""
        result = jolo.get_test_framework_config("unknown")
        self.assertIsInstance(result, dict)
        # Should still have the keys but with empty/None values
        self.assertIn("config_file", result)
        self.assertIn("example_test_file", result)


class TestGetCoverageConfig(unittest.TestCase):
    """Test get_coverage_config() function for language-specific coverage setup."""

    def test_function_exists(self):
        """get_coverage_config should exist and be callable."""
        self.assertTrue(hasattr(jolo, "get_coverage_config"))
        self.assertTrue(callable(jolo.get_coverage_config))

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = jolo.get_coverage_config("python")
        self.assertIsInstance(result, dict)

    def test_dict_has_required_keys(self):
        """Result should have 'config_addition' and 'run_command' keys."""
        result = jolo.get_coverage_config("python")
        self.assertIn("config_addition", result)
        self.assertIn("run_command", result)

    def test_python_config_addition(self):
        """Python should return pytest-cov config for pyproject.toml."""
        result = jolo.get_coverage_config("python")
        config = result["config_addition"]
        self.assertIsNotNone(config)
        # Should contain pyproject.toml configuration hints
        self.assertIn("[tool.pytest.ini_options]", config)
        self.assertIn("--cov", config)

    def test_python_run_command(self):
        """Python should return pytest --cov command."""
        result = jolo.get_coverage_config("python")
        cmd = result["run_command"]
        self.assertEqual(cmd, "pytest --cov=src --cov-report=term-missing")

    def test_typescript_config_addition(self):
        """TypeScript should return None for config_addition (bun built-in coverage)."""
        result = jolo.get_coverage_config("typescript")
        config = result["config_addition"]
        self.assertIsNone(config)

    def test_typescript_run_command(self):
        """TypeScript should return bun test --coverage command."""
        result = jolo.get_coverage_config("typescript")
        cmd = result["run_command"]
        self.assertEqual(cmd, "bun test --coverage")

    def test_go_config_addition_is_none(self):
        """Go should return None for config_addition (built-in coverage)."""
        result = jolo.get_coverage_config("go")
        self.assertIsNone(result["config_addition"])

    def test_go_run_command(self):
        """Go should return go test -cover command."""
        result = jolo.get_coverage_config("go")
        cmd = result["run_command"]
        self.assertEqual(cmd, "go test -cover ./...")

    def test_rust_config_addition_is_none(self):
        """Rust should return None for config_addition."""
        result = jolo.get_coverage_config("rust")
        self.assertIsNone(result["config_addition"])

    def test_rust_run_command(self):
        """Rust should return cargo llvm-cov command."""
        result = jolo.get_coverage_config("rust")
        cmd = result["run_command"]
        self.assertEqual(cmd, "cargo llvm-cov")

    def test_unknown_language_returns_none_values(self):
        """Unknown languages should return None for both keys."""
        result = jolo.get_coverage_config("unknown")
        self.assertIsNone(result["config_addition"])
        self.assertIsNone(result["run_command"])

    def test_shell_returns_none_values(self):
        """Shell language should return None (no standard coverage tool)."""
        result = jolo.get_coverage_config("shell")
        self.assertIsNone(result["config_addition"])
        self.assertIsNone(result["run_command"])

    def test_prose_returns_none_values(self):
        """Prose language should return None (no coverage for docs)."""
        result = jolo.get_coverage_config("prose")
        self.assertIsNone(result["config_addition"])
        self.assertIsNone(result["run_command"])

    def test_other_returns_none_values(self):
        """Other language should return None."""
        result = jolo.get_coverage_config("other")
        self.assertIsNone(result["config_addition"])
        self.assertIsNone(result["run_command"])


class TestGetTypeCheckerConfig(unittest.TestCase):
    """Test get_type_checker_config() function."""

    def test_function_exists(self):
        """get_type_checker_config should exist."""
        self.assertTrue(hasattr(jolo, "get_type_checker_config"))
        self.assertTrue(callable(jolo.get_type_checker_config))

    def test_python_returns_ty_config(self):
        """Python should return ty configuration."""
        result = jolo.get_type_checker_config("python")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertIn("config_file", result)
        self.assertIn("config_content", result)
        self.assertEqual(result["config_file"], "pyproject.toml")
        # Should contain [tool.ty] section
        self.assertIn("[tool.ty]", result["config_content"])

    def test_typescript_returns_tsconfig(self):
        """TypeScript should return tsconfig.json with strict mode."""
        result = jolo.get_type_checker_config("typescript")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["config_file"], "tsconfig.json")
        # Content should be valid JSON with strict mode
        config = json.loads(result["config_content"])
        self.assertIn("compilerOptions", config)
        self.assertTrue(config["compilerOptions"].get("strict"))
        self.assertTrue(config["compilerOptions"].get("noEmit"))

    def test_go_returns_none(self):
        """Go should return None (type checking built into compiler)."""
        result = jolo.get_type_checker_config("go")
        self.assertIsNone(result)

    def test_rust_returns_none(self):
        """Rust should return None (type checking built into compiler)."""
        result = jolo.get_type_checker_config("rust")
        self.assertIsNone(result)

    def test_shell_returns_none(self):
        """Shell should return None (no type checking)."""
        result = jolo.get_type_checker_config("shell")
        self.assertIsNone(result)

    def test_prose_returns_none(self):
        """Prose should return None (no type checking)."""
        result = jolo.get_type_checker_config("prose")
        self.assertIsNone(result)

    def test_other_returns_none(self):
        """Other language should return None."""
        result = jolo.get_type_checker_config("other")
        self.assertIsNone(result)

    def test_unknown_language_returns_none(self):
        """Unknown language should return None."""
        result = jolo.get_type_checker_config("unknown_lang")
        self.assertIsNone(result)

    def test_return_dict_structure(self):
        """Returned dict should have 'config_file' and 'config_content' keys."""
        # Test with Python (known to return a dict)
        result = jolo.get_type_checker_config("python")
        self.assertIn("config_file", result)
        self.assertIn("config_content", result)
        self.assertIsInstance(result["config_file"], str)
        self.assertIsInstance(result["config_content"], str)

    def test_typescript_tsconfig_has_essential_options(self):
        """TypeScript config should have essential compiler options."""
        result = jolo.get_type_checker_config("typescript")
        config = json.loads(result["config_content"])
        options = config["compilerOptions"]
        # Essential strict options
        self.assertTrue(options.get("strict"))
        self.assertTrue(options.get("noEmit"))
        # JSX options
        self.assertEqual(options.get("jsx"), "react-jsx")
        self.assertEqual(options.get("jsxImportSource"), "@kitajs/html")

    def test_python_ty_config_content(self):
        """Python ty config should have reasonable defaults."""
        result = jolo.get_type_checker_config("python")
        content = result["config_content"]
        # Should be TOML format with [tool.ty] section
        self.assertIn("[tool.ty]", content)


class TestGeneratePrecommitConfig(unittest.TestCase):
    """Test generate_precommit_config() function."""

    def test_function_exists(self):
        """generate_precommit_config should exist."""
        self.assertTrue(hasattr(jolo, "generate_precommit_config"))

    def test_returns_string(self):
        """Should return a string."""
        result = jolo.generate_precommit_config([])
        self.assertIsInstance(result, str)

    def test_returns_valid_yaml(self):
        """Should return valid YAML structure."""
        result = jolo.generate_precommit_config(["python"])
        # Verify basic YAML structure without requiring pyyaml
        self.assertTrue(result.startswith("repos:"))
        self.assertIn("  - repo:", result)
        self.assertIn("    rev:", result)
        self.assertIn("    hooks:", result)
        # Try parsing with yaml if available
        try:
            import yaml

            parsed = yaml.safe_load(result)
            self.assertIsInstance(parsed, dict)
            self.assertIn("repos", parsed)
        except ImportError:
            pass  # Skip yaml parsing if pyyaml not installed

    def test_always_includes_base_hooks(self):
        """Should always include trailing-whitespace, end-of-file-fixer, check-added-large-files."""
        result = jolo.generate_precommit_config([])

        self.assertIn("trailing-whitespace", result)
        self.assertIn("end-of-file-fixer", result)
        self.assertIn("check-added-large-files", result)

    def test_always_includes_gitleaks(self):
        """Should always include gitleaks hook."""
        result = jolo.generate_precommit_config([])

        self.assertIn("gitleaks", result)
        self.assertIn("https://github.com/gitleaks/gitleaks", result)

    def test_python_adds_ruff_hooks(self):
        """Python language should add ruff hooks."""
        result = jolo.generate_precommit_config(["python"])

        self.assertIn("https://github.com/astral-sh/ruff-pre-commit", result)
        self.assertIn("id: ruff", result)
        self.assertIn("id: ruff-format", result)
        self.assertIn("v0.8.6", result)

    def test_go_adds_golangci_lint(self):
        """Go language should add golangci-lint hook."""
        result = jolo.generate_precommit_config(["go"])

        self.assertIn("https://github.com/golangci/golangci-lint", result)
        self.assertIn("id: golangci-lint", result)
        self.assertIn("v1.62.0", result)

    def test_typescript_adds_biome(self):
        """TypeScript language should add biome hooks."""
        result = jolo.generate_precommit_config(["typescript"])

        self.assertIn("https://github.com/biomejs/pre-commit", result)
        self.assertIn("id: biome-check", result)
        self.assertIn("v0.6.0", result)

    def test_rust_adds_clippy_and_rustfmt(self):
        """Rust language should add clippy and rustfmt hooks via doublify/pre-commit-rust."""
        result = jolo.generate_precommit_config(["rust"])

        self.assertIn("https://github.com/doublify/pre-commit-rust", result)
        self.assertIn("id: fmt", result)
        self.assertIn("id: cargo-check", result)
        self.assertIn("v1.0", result)

    def test_shell_adds_shellcheck(self):
        """Shell language should add shellcheck hook."""
        result = jolo.generate_precommit_config(["shell"])

        self.assertIn("https://github.com/shellcheck-py/shellcheck-py", result)
        self.assertIn("id: shellcheck", result)
        self.assertIn("v0.10.0.1", result)

    def test_prose_adds_markdownlint_and_codespell(self):
        """Prose language should add markdownlint and codespell hooks."""
        result = jolo.generate_precommit_config(["prose"])

        self.assertIn(
            "https://github.com/igorshubovych/markdownlint-cli", result
        )
        self.assertIn("id: markdownlint", result)
        self.assertIn("v0.43.0", result)

        self.assertIn("https://github.com/codespell-project/codespell", result)
        self.assertIn("id: codespell", result)
        self.assertIn("v2.3.0", result)

    def test_multiple_languages_combine_correctly(self):
        """Multiple languages should combine all their hooks."""
        result = jolo.generate_precommit_config(["python", "typescript"])

        # Base hooks
        self.assertIn("trailing-whitespace", result)
        self.assertIn("gitleaks", result)

        # Python hooks
        self.assertIn("https://github.com/astral-sh/ruff-pre-commit", result)
        self.assertIn("id: ruff", result)

        # TypeScript hooks
        self.assertIn("https://github.com/biomejs/pre-commit", result)
        self.assertIn("id: biome-check", result)

    def test_all_languages_combined(self):
        """Should handle all supported languages together."""
        result = jolo.generate_precommit_config(
            ["python", "go", "typescript", "rust", "shell", "prose"]
        )

        # Verify all language-specific hooks are present
        self.assertIn("ruff", result)
        self.assertIn("golangci-lint", result)
        self.assertIn("biome-check", result)
        self.assertIn("cargo-check", result)
        self.assertIn("shellcheck", result)
        self.assertIn("markdownlint", result)
        self.assertIn("codespell", result)

    def test_unknown_language_ignored(self):
        """Unknown language should be ignored without error."""
        # 'other' is a valid language but has no specific hooks
        result = jolo.generate_precommit_config(["other"])

        # Should still have base hooks
        self.assertIn("trailing-whitespace", result)
        self.assertIn("gitleaks", result)

        # Count repos by counting '  - repo:' lines (base + local hooks)
        repo_count = result.count("  - repo:")
        self.assertEqual(repo_count, 3)

    def test_empty_languages_returns_base_config(self):
        """Empty language list should return only base hooks."""
        result = jolo.generate_precommit_config([])

        # Count repos by counting '  - repo:' lines (base + local hooks)
        repo_count = result.count("  - repo:")
        self.assertEqual(repo_count, 3)

        # Verify they are the expected repos
        self.assertIn("https://github.com/pre-commit/pre-commit-hooks", result)
        self.assertIn("https://github.com/gitleaks/gitleaks", result)
        self.assertIn("repo: local", result)

    def test_no_duplicate_repos(self):
        """Same language specified twice should not duplicate repos."""
        result = jolo.generate_precommit_config(["python", "python"])

        # Count occurrences of ruff repo
        count = result.count("https://github.com/astral-sh/ruff-pre-commit")
        self.assertEqual(count, 1)

    def test_prose_with_python(self):
        """Prose and Python together should have all hooks."""
        result = jolo.generate_precommit_config(["prose", "python"])

        self.assertIn("ruff", result)
        self.assertIn("markdownlint", result)
        self.assertIn("codespell", result)


class TestGetPrecommitInstallCommand(unittest.TestCase):
    """Test get_precommit_install_command() function."""

    def test_function_exists(self):
        """get_precommit_install_command should exist and be callable."""
        self.assertTrue(hasattr(jolo, "get_precommit_install_command"))
        self.assertTrue(callable(jolo.get_precommit_install_command))

    def test_returns_list(self):
        """Should return a list."""
        result = jolo.get_precommit_install_command()
        self.assertIsInstance(result, list)

    def test_returns_precommit_install_command(self):
        """Should return pre-commit install command with hook types."""
        result = jolo.get_precommit_install_command()
        self.assertEqual(
            result,
            [
                "pre-commit",
                "install",
                "--hook-type",
                "pre-commit",
                "--hook-type",
                "pre-push",
            ],
        )

    def test_returns_list_of_strings(self):
        """Should return a list of strings."""
        result = jolo.get_precommit_install_command()
        for item in result:
            self.assertIsInstance(item, str)

    def test_list_has_two_elements(self):
        """Should return a list with expected elements."""
        result = jolo.get_precommit_install_command()
        self.assertEqual(len(result), 6)


if __name__ == "__main__":
    unittest.main()
