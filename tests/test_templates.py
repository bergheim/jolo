#!/usr/bin/env python3
"""Tests for config generation (gitignore, pre-commit, editorconfig, language tools)."""

import json
import unittest
from pathlib import Path

import jolo


class TestGitignoreTemplate(unittest.TestCase):
    """Test universal .gitignore template."""

    def setUp(self):
        self.template_path = (
            Path(__file__).parent.parent / "templates" / ".gitignore"
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

    def test_pre_commit_template_gitleaks_is_local(self):
        """Gitleaks should use language: system (local hook)."""
        template_path = (
            Path(__file__).parent.parent
            / "templates"
            / ".pre-commit-config.yaml"
        )
        content = template_path.read_text()

        self.assertIn("id: gitleaks", content)
        self.assertIn("language: system", content)


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

    def test_python_bare_creates_tests_dir(self):
        """Python bare should create tests directory."""
        commands = jolo.get_project_init_commands("python", "myproject")
        self.assertIn(["mkdir", "-p", "tests"], commands)

    def test_typescript_web_returns_bun_init(self):
        """TypeScript web should return bun commands with BETH deps."""
        commands = jolo.get_project_init_commands(
            "typescript-web", "myproject"
        )
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

    def test_typescript_web_returns_beth_scaffold_files(self):
        """TypeScript web should return BETH scaffold files."""
        files = jolo.get_scaffold_files("typescript-web")
        rel_paths = [f[0] for f in files]
        self.assertIn("src/index.tsx", rel_paths)
        self.assertIn("src/styles.css", rel_paths)
        self.assertIn("src/pages/home.tsx", rel_paths)
        self.assertIn("src/components/layout.tsx", rel_paths)
        self.assertIn("public/.gitkeep", rel_paths)

    def test_go_web_returns_air_toml_scaffold_file(self):
        """Go web should include .air.toml scaffold."""
        files = jolo.get_scaffold_files("go-web")
        rel_paths = [f[0] for f in files]
        self.assertIn(".air.toml", rel_paths)

    def test_rust_web_returns_scaffold_files(self):
        """Rust web should return bacon.toml, styles, templates, and static."""
        files = jolo.get_scaffold_files("rust-web")
        rel_paths = [f[0] for f in files]
        self.assertIn("bacon.toml", rel_paths)
        self.assertIn("src/styles.css", rel_paths)
        self.assertIn("templates/base.html", rel_paths)
        self.assertIn("templates/index.html", rel_paths)
        self.assertIn("static/.gitkeep", rel_paths)

    def test_python_bare_returns_no_scaffold_files(self):
        """Python bare should return no additional scaffold files."""
        files = jolo.get_scaffold_files("python")
        self.assertEqual(files, [])

    def test_typescript_bare_returns_no_scaffold_files(self):
        """Bare TypeScript should skip BETH scaffold files."""
        files = jolo.get_scaffold_files("typescript")
        self.assertEqual(files, [])

    def test_typescript_bare_init_commands_skip_elysia(self):
        """Bare TypeScript should not install BETH deps."""
        commands = jolo.get_project_init_commands("typescript", "myproject")
        flat = str(commands)
        self.assertNotIn("elysia", flat)
        self.assertIn(["bun", "init", "-y"], commands)

    def test_typescript_bare_justfile_uses_ts_not_tsx(self):
        """Bare TypeScript justfile should reference .ts files."""
        content = jolo.get_justfile_content("typescript", "myproject")
        self.assertIn("src/index.ts", content)
        self.assertNotIn(".tsx", content)

    def test_typescript_bare_test_has_no_elysia(self):
        """Bare TypeScript example test should not import elysia."""
        config = jolo.get_test_framework_config("typescript")
        self.assertNotIn("elysia", config["example_test_content"])
        self.assertIn("bun:test", config["example_test_content"])

    def test_go_bare_has_no_init_commands(self):
        """Go bare ships go.mod via scaffold, so no in-container init needed."""
        commands = jolo.get_project_init_commands("go", "myproject")
        self.assertEqual(commands, [])

    def test_go_scaffold_includes_go_mod(self):
        """Go bare scaffold must include go.mod so the project is a valid module."""
        files = dict(jolo.get_scaffold_files("go"))
        self.assertIn("go.mod", files)
        self.assertIn("module {{PROJECT_NAME}}", files["go.mod"])

    def test_go_web_returns_templ_commands(self):
        """Go web should return templ generate (go.mod ships in scaffold)."""
        commands = jolo.get_project_init_commands("go-web", "myproject")
        self.assertNotIn(["go", "mod", "init", "myproject"], commands)
        self.assertIn(["go", "get", "github.com/a-h/templ"], commands)
        self.assertIn(["templ", "generate"], commands)

    def test_go_web_scaffold_includes_go_mod(self):
        """Go web scaffold must include go.mod alongside templ files."""
        files = dict(jolo.get_scaffold_files("go-web"))
        self.assertIn("go.mod", files)
        self.assertIn("module {{PROJECT_NAME}}", files["go.mod"])

    def test_python_web_returns_fastapi_deps(self):
        """Python web should install FastAPI deps."""
        commands = jolo.get_project_init_commands("python-web", "myproject")
        self.assertIn(["mkdir", "-p", "tests"], commands)
        self.assertIn(
            [
                "uv",
                "add",
                "fastapi",
                "uvicorn[standard]",
                "jinja2",
                "pyinstrument",
            ],
            commands,
        )

    def test_rust_returns_cargo_init(self):
        """Rust should return cargo init commands."""
        commands = jolo.get_project_init_commands("rust", "myproject")
        self.assertIn(["cargo", "init", "--name", "myproject"], commands)

    def test_rust_web_returns_cargo_add_and_setup(self):
        """Rust web should return cargo init, cargo add deps, and just setup."""
        commands = jolo.get_project_init_commands("rust-web", "myproject")
        self.assertIn(["cargo", "init", "--name", "myproject"], commands)
        self.assertIn(
            ["cargo", "add", "axum", "axum-htmx", "tower-livereload"],
            commands,
        )
        self.assertIn(
            ["cargo", "add", "minijinja", "-F", "builtins,loader"],
            commands,
        )
        self.assertIn(
            ["cargo", "add", "pprof", "-F", "flamegraph"],
            commands,
        )
        self.assertIn(["just", "setup"], commands)


class TestEnvrcTemplate(unittest.TestCase):
    """Web flavors get a generated .envrc with profiling enabled."""

    def test_web_flavors_enable_app_profile(self):
        for flavor in [
            "python-web",
            "typescript-web",
            "go-web",
            "rust-web",
            "elixir-web",
        ]:
            self.assertIn(
                "export APP_PROFILE=1", jolo.get_envrc_content(flavor)
            )

    def test_non_web_flavors_skip_envrc(self):
        self.assertEqual(jolo.get_envrc_content("python"), "")
        self.assertEqual(jolo.get_envrc_content("go"), "")

    def test_typescript_web_dev_uses_inspector_when_profile_enabled(self):
        content = jolo.get_justfile_content("typescript-web", "myproject")
        self.assertIn("--inspect=0.0.0.0:$(($PORT + 1000))", content)
        self.assertIn('if [ "${APP_PROFILE:-1}" != "0" ]', content)

    def test_rust_web_scaffold_includes_pprof_route(self):
        config = jolo.get_test_framework_config("rust-web")
        self.assertIn('"/debug/pprof/profile"', config["example_test_content"])
        self.assertIn("ProfilerGuard", config["example_test_content"])

    def test_shell_returns_src_mkdir(self):
        """Shell should create src directory."""
        commands = jolo.get_project_init_commands("shell", "myproject")
        self.assertIn(["mkdir", "-p", "src"], commands)

    def test_prose_returns_docs_or_src_mkdir(self):
        """Prose should create docs or src directory."""
        commands = jolo.get_project_init_commands("prose", "myproject")
        has_docs = ["mkdir", "-p", "docs"] in commands
        has_src = ["mkdir", "-p", "src"] in commands
        self.assertTrue(
            has_docs or has_src, f"Expected docs or src mkdir, got: {commands}"
        )

    def test_other_returns_src_mkdir(self):
        """Other flavor should create src directory."""
        commands = jolo.get_project_init_commands("other", "myproject")
        self.assertIn(["mkdir", "-p", "src"], commands)

    def test_unknown_flavor_returns_src_mkdir(self):
        """Unknown flavor should fall back to src mkdir."""
        commands = jolo.get_project_init_commands(
            "unknown_flavor", "myproject"
        )
        self.assertIn(["mkdir", "-p", "src"], commands)


class TestGetTestFrameworkConfig(unittest.TestCase):
    """Test get_test_framework_config() function."""

    def test_python_bare_config_file(self):
        """Python bare should use pyproject.toml for config."""
        result = jolo.get_test_framework_config("python")
        self.assertEqual(result["config_file"], "pyproject.toml")

    def test_python_bare_config_content_pytest(self):
        """Python bare config should include pytest configuration."""
        result = jolo.get_test_framework_config("python")
        self.assertIn("[tool.pytest.ini_options]", result["config_content"])

    def test_python_bare_example_test_file(self):
        """Python bare should create tests/test_main.py."""
        result = jolo.get_test_framework_config("python")
        self.assertEqual(result["example_test_file"], "tests/test_main.py")

    def test_python_bare_example_test_content(self):
        """Python bare example test should use pytest."""
        result = jolo.get_test_framework_config("python")
        content = result["example_test_content"]
        self.assertIn("def test_", content)
        self.assertIn("assert", content)

    def test_typescript_bare_config_file(self):
        """TypeScript bare has no config file (bun built-in testing)."""
        result = jolo.get_test_framework_config("typescript")
        self.assertTrue(
            result["config_file"] is None or result["config_file"] == "",
            f"Expected None or empty, got: {result['config_file']}",
        )

    def test_typescript_bare_config_content_bun(self):
        """TypeScript bare config should mention bun built-in testing."""
        result = jolo.get_test_framework_config("typescript")
        content = result["config_content"]
        self.assertIn("bun", content.lower())

    def test_typescript_bare_example_test_file(self):
        """TypeScript bare should create src/example.test.ts."""
        result = jolo.get_test_framework_config("typescript")
        self.assertEqual(result["example_test_file"], "src/example.test.ts")

    def test_typescript_bare_example_test_content(self):
        """TypeScript bare example test should use bun:test syntax."""
        result = jolo.get_test_framework_config("typescript")
        content = result["example_test_content"]
        self.assertIn("bun:test", content)
        self.assertIn("describe", content)
        self.assertIn("it(", content)
        self.assertIn("expect", content)

    def test_go_bare_config_file_none(self):
        """Go bare has no extra config file (built-in testing)."""
        result = jolo.get_test_framework_config("go")
        self.assertTrue(
            result["config_file"] is None or result["config_file"] == "",
            f"Expected None or empty, got: {result['config_file']}",
        )

    def test_go_bare_config_content_empty_or_comment(self):
        """Go bare config content should be empty or a comment."""
        result = jolo.get_test_framework_config("go")
        self.assertTrue(
            result["config_content"] == ""
            or "built-in" in result["config_content"].lower(),
            f"Expected empty or built-in info, got: {result['config_content']}",
        )

    def test_go_bare_example_test_file(self):
        """Go bare should create example_test.go."""
        result = jolo.get_test_framework_config("go")
        self.assertTrue(result["example_test_file"].endswith("_test.go"))

    def test_go_bare_example_test_content(self):
        """Go bare example test should use testing package."""
        result = jolo.get_test_framework_config("go")
        content = result["example_test_content"]
        self.assertIn("testing", content)
        self.assertIn("func Test", content)

    def test_rust_config_file_none(self):
        """Rust has no extra config file (built-in testing)."""
        result = jolo.get_test_framework_config("rust")
        self.assertTrue(
            result["config_file"] is None or result["config_file"] == "",
            f"Expected None or empty, got: {result['config_file']}",
        )

    def test_rust_config_content_empty_or_comment(self):
        """Rust config content should be empty or a comment."""
        result = jolo.get_test_framework_config("rust")
        self.assertTrue(
            result["config_content"] == ""
            or "built-in" in result["config_content"].lower(),
            f"Expected empty or built-in info, got: {result['config_content']}",
        )

    def test_rust_example_test_file(self):
        """Rust example test location."""
        result = jolo.get_test_framework_config("rust")
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

    def test_rust_web_uses_web_main_rs(self):
        """Rust web should use the web-specific main.rs with axum."""
        result = jolo.get_test_framework_config("rust-web")
        content = result["example_test_content"]
        self.assertIn("axum", content)
        self.assertIn("minijinja", content)
        self.assertIn("#[tokio::test]", content)

    def test_unknown_flavor_returns_empty_config(self):
        """Unknown flavor should return empty/None values."""
        result = jolo.get_test_framework_config("unknown")
        self.assertIsInstance(result, dict)
        self.assertIn("config_file", result)
        self.assertIn("example_test_file", result)


class TestGetCoverageConfig(unittest.TestCase):
    """Test get_coverage_config() function for flavor-specific coverage setup."""

    def test_python_config_addition(self):
        """Python should return pytest-cov config for pyproject.toml."""
        result = jolo.get_coverage_config("python")
        config = result["config_addition"]
        self.assertIsNotNone(config)
        self.assertIn("[tool.pytest.ini_options]", config)
        self.assertIn("--cov", config)

    def test_python_run_command(self):
        """Python should return pytest --cov command."""
        result = jolo.get_coverage_config("python-web")
        cmd = result["run_command"]
        self.assertEqual(cmd, "pytest --cov=src --cov-report=term-missing")

    def test_typescript_config_addition(self):
        """TypeScript should return None for config_addition."""
        result = jolo.get_coverage_config("typescript")
        config = result["config_addition"]
        self.assertIsNone(config)

    def test_typescript_run_command(self):
        """TypeScript should return bun test --coverage command."""
        result = jolo.get_coverage_config("typescript-web")
        cmd = result["run_command"]
        self.assertEqual(cmd, "bun test --coverage")

    def test_go_config_addition_is_none(self):
        """Go should return None for config_addition."""
        result = jolo.get_coverage_config("go")
        self.assertIsNone(result["config_addition"])

    def test_go_run_command(self):
        """Go should return go test -cover command."""
        result = jolo.get_coverage_config("go-web")
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

    def test_unknown_flavor_returns_none_values(self):
        """Unknown flavors should return None for both keys."""
        result = jolo.get_coverage_config("unknown")
        self.assertIsNone(result["config_addition"])
        self.assertIsNone(result["run_command"])

    def test_shell_returns_none_values(self):
        """Shell should return None (no standard coverage tool)."""
        result = jolo.get_coverage_config("shell")
        self.assertIsNone(result["config_addition"])
        self.assertIsNone(result["run_command"])

    def test_prose_returns_none_values(self):
        """Prose should return None (no coverage for docs)."""
        result = jolo.get_coverage_config("prose")
        self.assertIsNone(result["config_addition"])
        self.assertIsNone(result["run_command"])

    def test_other_returns_none_values(self):
        """Other should return None."""
        result = jolo.get_coverage_config("other")
        self.assertIsNone(result["config_addition"])
        self.assertIsNone(result["run_command"])


class TestGetTypeCheckerConfig(unittest.TestCase):
    """Test get_type_checker_config() function."""

    def test_python_returns_ty_config(self):
        """Python should return ty configuration."""
        result = jolo.get_type_checker_config("python")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertIn("config_file", result)
        self.assertIn("config_content", result)
        self.assertEqual(result["config_file"], "pyproject.toml")
        self.assertIn("[tool.ty]", result["config_content"])

    def test_typescript_bare_returns_tsconfig(self):
        """TypeScript bare should return tsconfig.json with strict mode."""
        result = jolo.get_type_checker_config("typescript")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["config_file"], "tsconfig.json")
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
        """Other should return None."""
        result = jolo.get_type_checker_config("other")
        self.assertIsNone(result)

    def test_unknown_flavor_returns_none(self):
        """Unknown flavor should return None."""
        result = jolo.get_type_checker_config("unknown_flavor")
        self.assertIsNone(result)

    def test_typescript_web_tsconfig_has_jsx_options(self):
        """TypeScript web config should have JSX compiler options."""
        result = jolo.get_type_checker_config("typescript-web")
        config = json.loads(result["config_content"])
        options = config["compilerOptions"]
        self.assertTrue(options.get("strict"))
        self.assertTrue(options.get("noEmit"))
        self.assertEqual(options.get("jsx"), "react-jsx")
        self.assertEqual(options.get("jsxImportSource"), "@kitajs/html")

    def test_typescript_bare_tsconfig_no_jsx(self):
        """TypeScript bare config should not have JSX options."""
        result = jolo.get_type_checker_config("typescript")
        config = json.loads(result["config_content"])
        options = config["compilerOptions"]
        self.assertTrue(options.get("strict"))
        self.assertNotIn("jsx", options)

    def test_python_ty_config_content(self):
        """Python ty config should have reasonable defaults."""
        result = jolo.get_type_checker_config("python-web")
        content = result["config_content"]
        self.assertIn("[tool.ty]", content)


class TestGeneratePrecommitConfig(unittest.TestCase):
    """Test generate_precommit_config() function."""

    def test_returns_valid_yaml(self):
        """Should return valid YAML structure."""
        result = jolo.generate_precommit_config(["python"])
        self.assertTrue(result.startswith("repos:"))
        self.assertIn("  - repo:", result)
        self.assertIn("    rev:", result)
        self.assertIn("    hooks:", result)
        try:
            import yaml

            parsed = yaml.safe_load(result)
            self.assertIsInstance(parsed, dict)
            self.assertIn("repos", parsed)
        except ImportError:
            pass

    def test_does_not_inject_perf_hook_into_user_owned_config(self):
        """The post-commit perf-run wiring must NOT live in the
        user-owned `.pre-commit-config.yaml`. It's installed directly
        into `.git/hooks/post-commit` via a managed-injection block
        (see _jolo.setup.install_jolo_post_commit_hook). Putting it
        here forced jolo to choose between stomping user customizations
        on `--force` or going stale on `--recreate`; neither is OK."""
        result = jolo.generate_precommit_config([])
        self.assertNotIn("perf-run", result)
        self.assertNotIn("PERF_RAW", result)
        self.assertNotIn("post-commit", result)

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
        self.assertIn("id: gitleaks", result)

    def test_python_adds_ruff_hooks(self):
        """Python flavor should add ruff system hooks."""
        result = jolo.generate_precommit_config(["python"])

        self.assertIn("id: ruff", result)
        self.assertIn("id: ruff-format", result)
        self.assertIn("language: system", result)

    def test_go_adds_golangci_lint(self):
        """Go flavor should add golangci-lint system hook."""
        result = jolo.generate_precommit_config(["go-web"])

        self.assertIn("id: golangci-lint", result)
        self.assertIn("language: system", result)

    def test_typescript_adds_biome(self):
        """TypeScript flavor should add biome hooks."""
        result = jolo.generate_precommit_config(["typescript-web"])

        self.assertIn("id: biome-check", result)
        self.assertIn("repo: local", result)
        self.assertIn(r"exclude: ^templates/.*\.html$", result)

    def test_rust_adds_rustfmt_and_cargo_check(self):
        """Rust flavor should add rustfmt and cargo-check system hooks."""
        result = jolo.generate_precommit_config(["rust"])

        self.assertIn("id: rustfmt", result)
        self.assertIn("id: cargo-check", result)
        self.assertIn("language: system", result)

    def test_shell_adds_shellcheck(self):
        """Shell flavor should add shellcheck system hook."""
        result = jolo.generate_precommit_config(["shell"])

        self.assertIn("id: shellcheck", result)
        self.assertIn("language: system", result)

    def test_prose_adds_markdownlint_and_codespell(self):
        """Prose flavor should add markdownlint (system) and codespell (remote)."""
        result = jolo.generate_precommit_config(["prose"])

        self.assertIn("id: markdownlint", result)
        self.assertIn("https://github.com/codespell-project/codespell", result)
        self.assertIn("id: codespell", result)

    def test_multiple_flavors_combine_correctly(self):
        """Multiple flavors should combine all their hooks."""
        result = jolo.generate_precommit_config(["python-web", "typescript"])

        self.assertIn("trailing-whitespace", result)
        self.assertIn("gitleaks", result)
        self.assertIn("id: ruff", result)
        self.assertIn("id: biome-check", result)
        self.assertIn(r"exclude: ^templates/.*\.html$", result)

    def test_all_flavors_combined(self):
        """Should handle all supported flavors together."""
        result = jolo.generate_precommit_config(
            [
                "python-web",
                "go",
                "typescript-web",
                "rust",
                "shell",
                "prose",
            ]
        )

        self.assertIn("ruff", result)
        self.assertIn("golangci-lint", result)
        self.assertIn("biome-check", result)
        self.assertIn("cargo-check", result)
        self.assertIn("shellcheck", result)
        self.assertIn("markdownlint", result)
        self.assertIn("codespell", result)

    def test_unknown_flavor_ignored(self):
        """Unknown flavor should be ignored without error."""
        result = jolo.generate_precommit_config(["other"])

        self.assertIn("trailing-whitespace", result)
        self.assertIn("gitleaks", result)

        repo_count = result.count("  - repo:")
        self.assertEqual(repo_count, 2)

    def test_empty_flavors_returns_base_config(self):
        """Empty flavor list should return only base hooks."""
        result = jolo.generate_precommit_config([])

        repo_count = result.count("  - repo:")
        self.assertEqual(repo_count, 2)

        self.assertIn("https://github.com/pre-commit/pre-commit-hooks", result)
        self.assertIn("id: gitleaks", result)
        self.assertIn("repo: local", result)

    def test_no_duplicate_hooks_same_base_language(self):
        """Web and bare of same language should not duplicate hooks."""
        result = jolo.generate_precommit_config(["python-web", "python"])

        count = result.count("id: ruff\n")
        self.assertEqual(count, 1)

    def test_prose_with_python(self):
        """Prose and Python together should have all hooks."""
        result = jolo.generate_precommit_config(["prose", "python"])

        self.assertIn("ruff", result)
        self.assertIn("markdownlint", result)
        self.assertIn("codespell", result)


class TestGetPrecommitInstallCommand(unittest.TestCase):
    """Test get_precommit_install_command() function."""

    def test_returns_precommit_install_command(self):
        """Returns pre-commit install for pre-commit + pre-push only.

        post-commit is intentionally NOT installed via pre-commit:
        pre-commit's shim ends with `exec ... pre-commit ...` which
        replaces the shell process, making any subsequent content
        (i.e. our managed-injection block) unreachable. The post-commit
        perf-run is wired up by `install_jolo_post_commit_hook` writing
        directly to .git/hooks/post-commit instead.
        """
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
        self.assertNotIn("post-commit", result)


class TestSanitizeForTestbed(unittest.TestCase):
    """Project-name to testbed-slug normalization.

    The perf-host testbed regex is ^[a-z0-9][a-z0-9_-]*$; templated
    scaffolds must always produce a valid value.
    """

    def test_lowercases(self):
        self.assertEqual(jolo.sanitize_for_testbed("MyApp"), "myapp")

    def test_replaces_non_alnum_with_dash(self):
        self.assertEqual(
            jolo.sanitize_for_testbed("foo bar/baz.qux"),
            "foo-bar-baz-qux",
        )

    def test_collapses_runs_of_dashes(self):
        self.assertEqual(jolo.sanitize_for_testbed("a   b"), "a-b")

    def test_preserves_existing_underscores(self):
        self.assertEqual(jolo.sanitize_for_testbed("snake_case"), "snake_case")

    def test_strips_leading_non_alnum(self):
        self.assertEqual(jolo.sanitize_for_testbed("--foo"), "foo")

    def test_strips_trailing_dash(self):
        self.assertEqual(jolo.sanitize_for_testbed("foo--"), "foo")

    def test_strips_leading_underscore(self):
        # Leading `_` violates the hub regex's first-character rule.
        self.assertEqual(jolo.sanitize_for_testbed("_foo"), "foo")
        self.assertEqual(jolo.sanitize_for_testbed("_foo_bar"), "foo_bar")

    def test_underscores_only_raises(self):
        with self.assertRaises(ValueError):
            jolo.sanitize_for_testbed("__")

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            jolo.sanitize_for_testbed("")

    def test_only_punctuation_raises(self):
        with self.assertRaises(ValueError):
            jolo.sanitize_for_testbed("!!!")

    def test_output_always_matches_hub_regex(self):
        import re as _re

        hub_re = _re.compile(r"^[a-z0-9][a-z0-9_-]*$")
        for raw in [
            "a",
            "abc",
            "My Cool App!",
            "---foo---",
            "_leading_underscore",
            "snake_case",
            "kebab-case",
            "UPPERCASE",
            "a_b-c d",
        ]:
            self.assertRegex(jolo.sanitize_for_testbed(raw), hub_re)


class TestPerfRigTemplate(unittest.TestCase):
    """templates/perf-rig.toml placeholder."""

    def setUp(self):
        self.template_path = (
            Path(__file__).parent.parent / "templates" / "perf-rig.toml"
        )

    def test_not_in_hash_syncable_files(self):
        """Rig uses the strictly_owned regenerated-bytes path, not the
        hash-based SYNCABLE_TEMPLATE_FILES loop."""
        from _jolo.setup import SYNCABLE_TEMPLATE_FILES

        self.assertNotIn("perf-rig.toml", SYNCABLE_TEMPLATE_FILES)

    def test_exists(self):
        self.assertTrue(self.template_path.exists())

    def test_parses_as_toml(self):
        import tomllib

        data = tomllib.loads(self.template_path.read_text())
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["target"]["mode"], "external_url")
        self.assertIn("url", data["target"])
        self.assertGreaterEqual(len(data["routes"]), 1)

    def test_url_is_envsubst_form(self):
        # target.url stays symbolic in the committed template. `just perf`
        # resolves ${DEV_HOST} and ${PORT} at POST time — no hostname
        # ever lands on disk.
        content = self.template_path.read_text()
        self.assertIn("${DEV_HOST}", content)
        self.assertIn("${PORT}", content)

    def test_project_placeholders_survive_for_create_substitution(self):
        content = self.template_path.read_text()
        self.assertIn("{{PROJECT_NAME}}", content)
        self.assertIn("{{PROJECT_LANGUAGE}}", content)

    def test_dev_realistic_regression_default(self):
        # Prod-tight defaults (p99=500) blow up on dev-container baselines.
        # Keep defaults dev-realistic; users tighten when they move to a
        # hub-bare testbed.
        import tomllib

        data = tomllib.loads(self.template_path.read_text())
        self.assertGreaterEqual(data["regression"]["landing"]["p99_ms"], 1000)


class TestJustfilePerfRecipe(unittest.TestCase):
    """The `perf` recipe appears with the project-specific testbed."""

    def test_perf_recipe_emitted(self):
        content = jolo.get_justfile_common_content("demokrato")
        self.assertIn("\nperf:", content)

    def test_testbed_substituted(self):
        content = jolo.get_justfile_common_content("demokrato")
        self.assertIn("PERF_TESTBED:=dev-container-demokrato", content)

    def test_testbed_sanitized_for_weird_name(self):
        content = jolo.get_justfile_common_content("My Cool App!")
        self.assertIn("PERF_TESTBED:=dev-container-my-cool-app", content)

    def test_hub_env_required(self):
        # No hostname baked into the generated justfile — operators set
        # PERF_HOST in their host .zshrc (mounted into the container).
        content = jolo.get_justfile_common_content("demokrato")
        self.assertIn("PERF_HOST", content)
        self.assertNotIn("berghome.ts.glvortex.net", content)

    def test_port_preflight(self):
        content = jolo.get_justfile_common_content("demokrato")
        self.assertIn("PORT not set", content)

    def test_envsubst_then_jq_for_rig(self):
        # jq -R -s reads the substituted rig from stdin safely, no quoting
        # landmines and no intermediate temp file.
        content = jolo.get_justfile_common_content("demokrato")
        self.assertIn("envsubst '$DEV_HOST $PORT'", content)
        self.assertIn("jq -R -s", content)

    def test_guards_against_no_initial_commit(self):
        content = jolo.get_justfile_common_content("demokrato")
        self.assertIn("git rev-parse --verify HEAD", content)

    def test_derives_dev_host_from_perf_host(self):
        content = jolo.get_justfile_common_content("demokrato")
        self.assertIn("DEV_HOST", content)
        # Derivation pulls hostname out of the hub URL as a fallback.
        self.assertIn("PERF_HOST", content)

    def test_uses_envsubst_for_rig_substitution(self):
        content = jolo.get_justfile_common_content("demokrato")
        self.assertIn("envsubst", content)

    def test_refuses_loopback_targets(self):
        # Loopback check is on DEV_HOST itself (the variable), not the
        # substituted rig content. All loopback forms must be listed.
        content = jolo.get_justfile_common_content("demokrato")
        for needle in ("localhost", "127.*", "0.0.0.0", "::1"):
            self.assertIn(needle, content)

    def test_parses_validity_status_from_response(self):
        """Recipe pulls validity_status out of the hub response."""
        content = jolo.get_justfile_common_content("demokrato")
        self.assertIn("validity_status", content)

    def test_summary_prints_grafana_url(self):
        """Human-readable summary exposes the Grafana link."""
        content = jolo.get_justfile_common_content("demokrato")
        self.assertIn("grafana_url", content)

    def test_perf_raw_opts_out_of_pretty_summary(self):
        """PERF_RAW=1 dumps the raw hub JSON for scripts / hooks."""
        content = jolo.get_justfile_common_content("demokrato")
        self.assertIn("PERF_RAW", content)

    def test_exit_codes_distinguish_infra_from_validity(self):
        """Exit 1 for infra (curl/jq), exit 2 for run-completed-but-invalid."""
        content = jolo.get_justfile_common_content("demokrato")
        self.assertIn("exit 2", content)


class TestAppProfileDefault(unittest.TestCase):
    """justfile.common exports APP_PROFILE=1 by default."""

    def test_app_profile_exported(self):
        content = jolo.get_justfile_common_content("demokrato")
        self.assertIn("APP_PROFILE", content)

    def test_app_profile_has_default_value_1(self):
        content = jolo.get_justfile_common_content("demokrato")
        self.assertIn('"APP_PROFILE", "1"', content)

    def test_app_profile_is_exported(self):
        """`export` directive so the var reaches child processes."""
        content = jolo.get_justfile_common_content("demokrato")
        self.assertIn("export APP_PROFILE", content)


if __name__ == "__main__":
    unittest.main()
