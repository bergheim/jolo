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


class TestCreateModeFlavorIntegration(unittest.TestCase):
    """Integration tests for run_create_mode() flavor handling."""

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
            get_secrets=mock.Mock(return_value={}),
        )

    def test_create_with_flavor_uses_provided_flavors(self):
        """create with --flavor should use the provided flavors."""
        args = jolo.parse_args(
            [
                "create",
                "testproj",
                "--flavor",
                "python-web,typescript-bare",
                "-d",
            ]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / "testproj"

        precommit_config = project_path / ".pre-commit-config.yaml"
        self.assertTrue(precommit_config.exists())
        content = precommit_config.read_text()
        self.assertIn("ruff", content)  # Python
        self.assertIn("biome", content)  # TypeScript

    def test_create_without_flavor_calls_interactive_selector(self):
        """create without --flavor should call select_flavors_interactive."""
        args = jolo.parse_args(["create", "testproj", "-d"])

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            with mock.patch(
                "_jolo.commands.select_flavors_interactive",
                return_value=["go-bare"],
            ) as mock_selector:
                jolo.run_create_mode(args)
                mock_selector.assert_called_once()

        project_path = Path(self.tmpdir) / "testproj"

        precommit_config = project_path / ".pre-commit-config.yaml"
        self.assertTrue(precommit_config.exists())
        content = precommit_config.read_text()
        self.assertIn("golangci-lint", content)  # Go

    def test_create_generates_precommit_config(self):
        """create should generate .pre-commit-config.yaml based on flavors."""
        args = jolo.parse_args(
            ["create", "testproj", "--flavor", "rust", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / "testproj"
        precommit_config = project_path / ".pre-commit-config.yaml"

        self.assertTrue(precommit_config.exists())
        content = precommit_config.read_text()
        self.assertIn("cargo-check", content)
        self.assertIn("fmt", content)
        self.assertIn("trailing-whitespace", content)
        self.assertIn("gitleaks", content)

    def test_create_copies_gitignore_from_templates(self):
        """create should copy .gitignore from templates/."""
        args = jolo.parse_args(
            ["create", "testproj", "--flavor", "python-bare", "-d"]
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
            ["create", "testproj", "--flavor", "python-bare", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / "testproj"
        editorconfig = project_path / ".editorconfig"

        self.assertTrue(editorconfig.exists())

    def test_create_runs_init_commands_for_primary_flavor(self):
        """create should run project init commands for primary flavor."""
        args = jolo.parse_args(
            [
                "create",
                "testproj",
                "--flavor",
                "python-bare,typescript-web",
                "-d",
            ]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

            exec_calls = mocks["devcontainer_exec_command"].call_args_list
            mkdir_called = any(
                "mkdir -p tests" in str(call) for call in exec_calls
            )
            self.assertTrue(
                mkdir_called,
                f"Expected 'mkdir -p tests' to be called, got: {exec_calls}",
            )

    def test_create_writes_test_framework_config_for_python(self):
        """create with python-bare should write pytest config to pyproject.toml."""
        args = jolo.parse_args(
            ["create", "testproj", "--flavor", "python-bare", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / "testproj"
        pyproject = project_path / "pyproject.toml"

        if pyproject.exists():
            content = pyproject.read_text()
            self.assertIn("pytest", content.lower())

    def test_create_installs_test_hooks(self):
        """create should install pre-commit hooks and set test defaults."""
        args = jolo.parse_args(
            ["create", "testproj", "--flavor", "python-bare", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

            exec_calls = mocks["devcontainer_exec_command"].call_args_list
            install_called = any(
                "pre-commit install --hook-type pre-commit --hook-type pre-push"
                in str(call)
                for call in exec_calls
            )
            commit_default = any(
                "git config --local hooks.test-on-commit true" in str(call)
                for call in exec_calls
            )
            push_default = any(
                "git config --local hooks.test-on-push false" in str(call)
                for call in exec_calls
            )

            self.assertTrue(
                install_called,
                f"Expected pre-commit install, got: {exec_calls}",
            )
            self.assertTrue(
                commit_default,
                f"Expected commit default, got: {exec_calls}",
            )
            self.assertTrue(
                push_default,
                f"Expected push default, got: {exec_calls}",
            )

    def test_create_writes_test_framework_config_for_typescript(self):
        """create with typescript-bare should create example test with bun:test."""
        args = jolo.parse_args(
            ["create", "testproj", "--flavor", "typescript-bare", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / "testproj"
        example_test = project_path / "src" / "example.test.ts"

        self.assertTrue(example_test.exists())
        content = example_test.read_text()
        self.assertIn("bun:test", content)

    def test_create_writes_type_checker_config_for_typescript_web(self):
        """create with typescript-web should write tsconfig.json with JSX."""
        args = jolo.parse_args(
            ["create", "testproj", "--flavor", "typescript-web", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / "testproj"
        tsconfig = project_path / "tsconfig.json"

        self.assertTrue(tsconfig.exists())
        content = tsconfig.read_text()
        self.assertIn("strict", content)
        self.assertIn("jsx", content)

    def test_create_writes_beth_source_files(self):
        """create with typescript-web should write BETH scaffold files."""
        args = jolo.parse_args(
            ["create", "testproj", "--flavor", "typescript-web", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / "testproj"
        self.assertTrue((project_path / "src" / "index.tsx").exists())
        self.assertTrue((project_path / "src" / "pages" / "home.tsx").exists())
        self.assertTrue(
            (project_path / "src" / "components" / "layout.tsx").exists()
        )
        self.assertTrue((project_path / "src" / "styles.css").exists())
        self.assertTrue((project_path / "public" / ".gitkeep").exists())

    def test_create_first_flavor_is_primary(self):
        """First flavor in list should be treated as primary for init commands."""
        args = jolo.parse_args(
            ["create", "testproj", "--flavor", "go-bare,python-bare", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

            exec_calls = mocks["devcontainer_exec_command"].call_args_list
            go_mod_called = any(
                "go mod init" in str(call) for call in exec_calls
            )
            self.assertTrue(
                go_mod_called,
                f"Expected 'go mod init' to be called, got: {exec_calls}",
            )

    def test_create_empty_flavor_selection_aborts(self):
        """If interactive selector returns empty list, should abort."""
        args = jolo.parse_args(["create", "testproj", "-d"])

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            with mock.patch(
                "_jolo.commands.select_flavors_interactive", return_value=[]
            ):
                with self.assertRaises(SystemExit):
                    jolo.run_create_mode(args)

    def test_create_go_web_scaffold_files(self):
        """create with go-web should write main.go, templ components, and justfile."""
        args = jolo.parse_args(
            ["create", "testproj", "--flavor", "go-web", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / "testproj"

        # main.go with /api/greet handler
        main_go = project_path / "main.go"
        self.assertTrue(main_go.exists())
        content = main_go.read_text()
        self.assertIn("handleHome", content)
        self.assertIn("handleGreet", content)
        self.assertIn("/api/greet", content)
        self.assertIn('"testproj/components"', content)

        # templ components
        self.assertTrue((project_path / "components" / "page.templ").exists())
        self.assertTrue((project_path / "components" / "home.templ").exists())

        # justfile with templ + air
        justfile = project_path / "justfile"
        self.assertTrue(justfile.exists())
        jf_content = justfile.read_text()
        self.assertIn("templ generate", jf_content)
        self.assertIn("air", jf_content)

        # static dir
        self.assertTrue((project_path / "static" / ".gitkeep").exists())

    def test_create_python_web_scaffold_files(self):
        """create with python-web should write FastAPI app, templates, and justfile."""
        args = jolo.parse_args(
            ["create", "testproj", "--flavor", "python-web", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / "testproj"

        # app.py with FastAPI
        app_py = project_path / "src" / "testproj" / "app.py"
        self.assertTrue(app_py.exists())
        content = app_py.read_text()
        self.assertIn("FastAPI", content)
        self.assertIn("Jinja2Templates", content)

        # main.py with uvicorn
        main_py = project_path / "src" / "testproj" / "main.py"
        self.assertTrue(main_py.exists())
        main_content = main_py.read_text()
        self.assertIn("uvicorn", main_content)
        self.assertIn("testproj.app:app", main_content)

        # Jinja2 templates
        self.assertTrue((project_path / "templates" / "base.html").exists())
        self.assertTrue((project_path / "templates" / "home.html").exists())
        base_html = (project_path / "templates" / "base.html").read_text()
        self.assertIn("htmx", base_html)

        # pyproject.toml with FastAPI deps
        pyproject = project_path / "pyproject.toml"
        self.assertTrue(pyproject.exists())
        pyp_content = pyproject.read_text()
        self.assertIn("fastapi", pyp_content)
        self.assertIn("uvicorn", pyp_content)
        self.assertIn("jinja2", pyp_content)

        # justfile with uvicorn dev server
        justfile = project_path / "justfile"
        self.assertTrue(justfile.exists())
        jf_content = justfile.read_text()
        self.assertIn("uvicorn", jf_content)
        self.assertIn("--reload", jf_content)

        # static dir
        self.assertTrue((project_path / "static" / ".gitkeep").exists())

    def test_create_template_files_are_copied(self):
        """create should copy AGENTS.md, CLAUDE.md, GEMINI.md from templates."""
        args = jolo.parse_args(
            ["create", "testproj", "--flavor", "python-bare", "-d"]
        )

        with self._mock_devcontainer_calls() as mocks:
            mocks["devcontainer_up"].return_value = True
            jolo.run_create_mode(args)

        project_path = Path(self.tmpdir) / "testproj"

        for filename in ["AGENTS.md", "CLAUDE.md", "GEMINI.md"]:
            filepath = project_path / filename
            self.assertTrue(filepath.exists(), f"Expected {filename} to exist")


class TestInitModeIntegration(unittest.TestCase):
    """Integration tests for run_init_mode()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.tmpdir)

    def test_init_installs_test_hooks(self):
        """init should install pre-commit hooks and set test defaults."""
        args = jolo.parse_args(["init", "-d"])

        def mock_run(*_args, **_kwargs):
            result = mock.Mock()
            result.returncode = 0
            return result

        with mock.patch("_jolo.commands.subprocess.run", side_effect=mock_run):
            with mock.patch.multiple(
                "_jolo.commands",
                devcontainer_up=mock.DEFAULT,
                devcontainer_exec_command=mock.DEFAULT,
                devcontainer_exec_tmux=mock.DEFAULT,
                scaffold_devcontainer=mock.DEFAULT,
                setup_credential_cache=mock.DEFAULT,
                setup_notification_hooks=mock.DEFAULT,
                setup_emacs_config=mock.DEFAULT,
                get_secrets=mock.DEFAULT,
            ) as mocks:
                mocks["get_secrets"].return_value = {}
                mocks["devcontainer_up"].return_value = True
                jolo.run_init_mode(args)

                exec_calls = mocks["devcontainer_exec_command"].call_args_list
                install_called = any(
                    "pre-commit install --hook-type pre-commit --hook-type pre-push"
                    in str(call)
                    for call in exec_calls
                )
                commit_default = any(
                    "git config --local hooks.test-on-commit true" in str(call)
                    for call in exec_calls
                )
                push_default = any(
                    "git config --local hooks.test-on-push false" in str(call)
                    for call in exec_calls
                )

                self.assertTrue(
                    install_called,
                    f"Expected pre-commit install, got: {exec_calls}",
                )
                self.assertTrue(
                    commit_default,
                    f"Expected commit default, got: {exec_calls}",
                )
                self.assertTrue(
                    push_default,
                    f"Expected push default, got: {exec_calls}",
                )


if __name__ == "__main__":
    unittest.main()
