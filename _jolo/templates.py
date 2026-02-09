"""Template and config generation functions for jolo."""

import json
from pathlib import Path

from _jolo import constants

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _read_template(path: str) -> str:
    """Read a template file relative to templates/ dir."""
    return (_TEMPLATES_DIR / path).read_text()


def _render(template: str, **variables: str) -> str:
    """Replace {{VAR}} placeholders in template text."""
    for key, value in variables.items():
        template = template.replace(f"{{{{{key}}}}}", value)
    return template


def _format_hook_yaml(hook: dict, indent: str = "        ") -> str:
    """Format a single hook as YAML.

    Args:
        hook: Hook configuration dict with 'id' and optional other keys
        indent: Indentation string for the hook

    Returns:
        YAML-formatted hook string
    """
    lines = [f"{indent}- id: {hook['id']}"]
    if "args" in hook:
        args_str = ", ".join(hook["args"])
        lines.append(f"{indent}  args: [{args_str}]")
    if "additional_dependencies" in hook:
        deps = hook["additional_dependencies"]
        deps_str = ", ".join(f'"{d}"' for d in deps)
        lines.append(f"{indent}  additional_dependencies: [{deps_str}]")
    return "\n".join(lines)


def _format_repo_yaml(repo_config: dict) -> str:
    """Format a single repo configuration as YAML.

    Args:
        repo_config: Repo configuration dict with 'repo', 'rev', and 'hooks'

    Returns:
        YAML-formatted repo string
    """
    lines = [
        f"  - repo: {repo_config['repo']}",
        f"    rev: {repo_config['rev']}",
        "    hooks:",
    ]
    for hook in repo_config["hooks"]:
        lines.append(_format_hook_yaml(hook))
    return "\n".join(lines)


def generate_precommit_config(languages: list[str]) -> str:
    """Generate .pre-commit-config.yaml content based on selected languages.

    Args:
        languages: List of language codes (e.g., ['python', 'typescript'])

    Returns:
        Valid YAML string for .pre-commit-config.yaml
    """
    # Start with base hooks that are always included
    repos = [
        {
            "repo": "https://github.com/pre-commit/pre-commit-hooks",
            "rev": "v5.0.0",
            "hooks": [
                {"id": "trailing-whitespace"},
                {"id": "end-of-file-fixer"},
                {"id": "check-added-large-files"},
            ],
        },
        {
            "repo": "https://github.com/gitleaks/gitleaks",
            "rev": "v8.24.2",
            "hooks": [
                {"id": "gitleaks"},
            ],
        },
    ]

    # Track which repos we've already added (to avoid duplicates)
    added_repos = set()

    # Add language-specific hooks
    for lang in languages:
        if lang not in constants.PRECOMMIT_HOOKS:
            continue

        hook_config = constants.PRECOMMIT_HOOKS[lang]

        # Handle languages with multiple repos (like prose)
        if isinstance(hook_config, list):
            for config in hook_config:
                if config["repo"] not in added_repos:
                    repos.append(config)
                    added_repos.add(config["repo"])
        else:
            if hook_config["repo"] not in added_repos:
                repos.append(hook_config)
                added_repos.add(hook_config["repo"])

    # Generate YAML output
    lines = ["repos:"]
    for repo in repos:
        lines.append(_format_repo_yaml(repo))

    return "\n".join(lines) + "\n"


def get_precommit_install_command() -> list[str]:
    """Get the command to install pre-commit hooks.

    Returns:
        List of command parts: ['pre-commit', 'install']
    """
    return ["pre-commit", "install"]


def get_type_checker_config(language: str) -> dict | None:
    """Get type checker configuration for a language.

    Returns configuration for setting up type checking based on language.
    For languages with built-in type checking (Go, Rust), returns None.

    Args:
        language: The programming language (python, typescript, go, rust, etc.)

    Returns:
        dict with 'config_file' and 'config_content' keys, or None if no
        external type checker config is needed.
    """
    if language == "python":
        # ty (by Astral, the ruff folks) configuration
        config_content = """\
[tool.ty]
# ty type checker configuration
# See: https://github.com/astral-sh/ty
"""
        return {
            "config_file": "pyproject.toml",
            "config_content": config_content,
        }

    elif language == "typescript":
        # tsconfig.json with strict mode
        tsconfig = {
            "compilerOptions": {
                "strict": True,
                "noEmit": True,
                "target": "ES2022",
                "module": "NodeNext",
                "moduleResolution": "NodeNext",
                "esModuleInterop": True,
                "skipLibCheck": True,
                "forceConsistentCasingInFileNames": True,
            },
            "include": ["**/*.ts", "**/*.tsx"],
            "exclude": ["node_modules", "dist"],
        }
        return {
            "config_file": "tsconfig.json",
            "config_content": json.dumps(tsconfig, indent=2),
        }

    # Go and Rust have built-in type checking, no external config needed
    # Shell, prose, other have no type checking
    return None


def get_coverage_config(language: str) -> dict:
    """Get code coverage configuration for a language.

    Returns configuration for setting up code coverage based on language.
    For languages without standard coverage tooling, returns None values.

    Args:
        language: The programming language (python, typescript, go, rust, etc.)

    Returns:
        dict with keys:
            - 'config_addition': Config to add to project config file, or None
            - 'run_command': Command to run coverage, or None
    """
    if language == "python":
        config_addition = """\
[tool.pytest.ini_options]
addopts = "--cov=src --cov-report=term-missing"
"""
        return {
            "config_addition": config_addition,
            "run_command": "pytest --cov=src --cov-report=term-missing",
        }

    elif language == "typescript":
        # Bun has built-in coverage support
        return {
            "config_addition": None,
            "run_command": "bun test --coverage",
        }

    elif language == "go":
        # Go has built-in coverage support
        return {
            "config_addition": None,
            "run_command": "go test -cover ./...",
        }

    elif language == "rust":
        # Rust uses cargo-llvm-cov for coverage
        return {
            "config_addition": None,
            "run_command": "cargo llvm-cov",
        }

    # Shell, prose, other, and unknown languages have no standard coverage
    return {
        "config_addition": None,
        "run_command": None,
    }


def get_justfile_content(language: str, project_name: str) -> str:
    """Generate justfile content for a project based on language.

    Args:
        language: The programming language
        project_name: The project name

    Returns:
        justfile content string
    """
    module_name = project_name.replace("-", "_")
    lang = language if language in ("python", "typescript", "go", "rust") else "other"
    template = _read_template(f"lang/{lang}/justfile")
    return _render(template, PROJECT_NAME=project_name, MODULE_NAME=module_name)


def get_motd_content(language: str, project_name: str) -> str:
    """Generate MOTD content for a project based on language.

    Args:
        language: The programming language
        project_name: The project name

    Returns:
        MOTD content string
    """
    template = _read_template("motd")
    return _render(template, PROJECT_NAME=project_name)


def get_test_framework_config(language: str) -> dict:
    """Get test framework configuration for a language.

    Returns configuration for setting up test frameworks based on language.
    For languages with built-in testing (Go, Rust), config_file is None.

    Args:
        language: The programming language (python, typescript, go, rust, etc.)

    Returns:
        dict with keys:
            - 'config_file': File name for test config, or None for built-in testing
            - 'config_content': Content to write/append to config file
            - 'example_test_file': Path to example test file
            - 'example_test_content': Content for example test file
    """
    if language == "python":
        return {
            "config_file": "pyproject.toml",
            "config_content": _read_template("lang/python/pyproject.toml"),
            "example_test_file": "tests/test_main.py",
            "example_test_content": _read_template("lang/python/test_main.py"),
            "main_file": "src/{{PROJECT_NAME_UNDERSCORE}}/main.py",
            "main_content": _read_template("lang/python/main.py"),
            "init_file": "src/{{PROJECT_NAME_UNDERSCORE}}/__init__.py",
            "tests_init_file": "tests/__init__.py",
        }

    elif language == "typescript":
        return {
            "config_file": None,
            "config_content": "# Bun has built-in testing. Run tests with: bun test",
            "example_test_file": "src/example.test.ts",
            "example_test_content": _read_template("lang/typescript/example.test.ts"),
        }

    elif language == "go":
        return {
            "config_file": None,
            "config_content": "# Go uses built-in testing. Run tests with: go test ./...",
            "example_test_file": "example_test.go",
            "example_test_content": _read_template("lang/go/example_test.go"),
            "main_file": "main.go",
            "main_content": _read_template("lang/go/main.go"),
        }

    elif language == "rust":
        return {
            "config_file": None,
            "config_content": "# Rust uses built-in testing. Run tests with: cargo test",
            "example_test_file": "src/main.rs",
            "example_test_content": _read_template("lang/rust/main.rs"),
        }

    # Shell, prose, other, and unknown languages have no standard test framework
    return {
        "config_file": None,
        "config_content": "",
        "example_test_file": None,
        "example_test_content": "",
    }


def get_project_init_commands(language: str, project_name: str) -> list[list[str]]:
    """Get initialization commands for a project based on language.

    Returns a list of command lists to execute inside the container.
    Each inner list is a command + arguments.

    Args:
        language: The programming language (python, typescript, go, rust, shell, prose, other)
        project_name: The name of the project (used in go mod init, cargo new, etc.)

    Returns:
        List of command lists, e.g. [['uv', 'init'], ['mkdir', '-p', 'tests']]
    """
    commands: list[list[str]] = []

    if language == "python":
        # pyproject.toml is created during scaffolding, just ensure tests dir exists
        commands.append(["mkdir", "-p", "tests"])
    elif language == "typescript":
        commands.append(["bun", "init"])
        commands.append(["mkdir", "-p", "src"])
        commands.append(["mv", "index.ts", "src/index.ts"])
    elif language == "go":
        commands.append(["go", "mod", "init", project_name])
    elif language == "rust":
        commands.append(["cargo", "init", "--name", project_name])
    elif language == "shell":
        commands.append(["mkdir", "-p", "src"])
    elif language == "prose":
        commands.append(["mkdir", "-p", "docs"])
    else:
        # Default fallback for 'other' or unknown languages
        commands.append(["mkdir", "-p", "src"])

    return commands
