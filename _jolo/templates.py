"""Template and config generation functions for jolo."""

import json

from _jolo import constants


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
    return ['pre-commit', 'install']


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

    browse_recipe = """\

# Open in browser
browse:
    @u="http://${DEV_HOST:-localhost}:${PORT:-4000}"; echo "$u"; xdg-open "$u" 2>/dev/null || true
"""

    if language == "python":
        return f"""\
# Run the project
run:
    uv run python src/{module_name}/main.py

# Run with auto-reload
dev:
    fd -e py | entr -r uv run python src/{module_name}/main.py

# Run tests
test:
    uv run pytest

# Run tests continuously (on file change)
test-watch:
    fd -e py | entr -c uv run pytest

# Add a dependency
add *packages:
    uv add {{{{packages}}}}
{browse_recipe}"""
    elif language == "typescript":
        return f"""\
# Run the project
run:
    bun run src/index.ts

# Run with auto-reload
dev:
    bun --hot src/index.ts

# Run tests
test:
    bun test

# Run tests continuously (on file change)
test-watch:
    fd -e ts | entr -c bun test

# Add a dependency
add *packages:
    bun add {{{{packages}}}}
{browse_recipe}"""
    elif language == "go":
        return f"""\
# Run the project
run:
    go run .

# Run with auto-reload
dev:
    air

# Run tests
test:
    go test ./...

# Run tests continuously (on file change)
test-watch:
    fd -e go | entr -c go test ./...

# Add a dependency
add *packages:
    go get {{{{packages}}}}
{browse_recipe}"""
    elif language == "rust":
        return f"""\
# Run the project
run:
    cargo run

# Run with auto-reload
dev:
    fd -e rs | entr -r cargo run

# Run tests
test:
    cargo test

# Run tests continuously (on file change)
test-watch:
    fd -e rs | entr -c cargo test

# Add a dependency
add *packages:
    cargo add {{{{packages}}}}
{browse_recipe}"""
    else:
        return f"""\
# Run the project
run:
    echo "No run command configured"

# Run tests
test:
    echo "No test command configured"
{browse_recipe}"""


def get_motd_content(language: str, project_name: str) -> str:
    """Generate MOTD content for a project based on language.

    Args:
        language: The programming language
        project_name: The project name

    Returns:
        MOTD content string
    """
    return f"""\
{project_name}

  just run        - run the project
  just dev        - run with auto-reload
  just test       - run tests
  just test-watch - run tests on file change
  just add X      - add dependency
  just browse     - open in browser
"""


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
        config_content = """\
[project]
name = "{{PROJECT_NAME}}"
version = "0.1.0"
description = ""
requires-python = ">=3.12"
dependencies = []

[dependency-groups]
dev = ["pytest", "pytest-watch"]

[project.scripts]
{{PROJECT_NAME}} = "{{PROJECT_NAME_UNDERSCORE}}.main:main"

[tool.hatch.build.targets.wheel]
packages = ["src/{{PROJECT_NAME_UNDERSCORE}}"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
python_files = ["test_*.py", "*_test.py"]
python_functions = ["test_*"]
addopts = "-v --tb=short"
"""
        main_content = '''\
def hello() -> str:
    return "Hello, World!"


def main() -> None:
    print(hello())


if __name__ == "__main__":
    main()
'''
        example_test_content = '''\
from {{PROJECT_NAME_UNDERSCORE}}.main import hello


def test_hello():
    assert hello() == "Hello, World!"
'''
        return {
            "config_file": "pyproject.toml",
            "config_content": config_content,
            "example_test_file": "tests/test_main.py",
            "example_test_content": example_test_content,
            "main_file": "src/{{PROJECT_NAME_UNDERSCORE}}/main.py",
            "main_content": main_content,
            "init_file": "src/{{PROJECT_NAME_UNDERSCORE}}/__init__.py",
            "tests_init_file": "tests/__init__.py",
        }

    elif language == "typescript":
        # Bun has built-in test runner, no config file needed
        example_test_content = """\
import { describe, it, expect } from 'bun:test';

describe('Example tests', () => {
  it('should pass a basic test', () => {
    expect(true).toBe(true);
  });

  it('should perform arithmetic correctly', () => {
    expect(1 + 1).toBe(2);
  });

  it('should handle string operations', () => {
    const result = 'hello'.toUpperCase();
    expect(result).toBe('HELLO');
  });
});
"""
        return {
            "config_file": None,
            "config_content": "# Bun has built-in testing. Run tests with: bun test",
            "example_test_file": "src/example.test.ts",
            "example_test_content": example_test_content,
        }

    elif language == "go":
        # Go has built-in testing, no external dependencies needed
        example_test_content = """\
package main

import "testing"

func TestExample(t *testing.T) {
\tif false {
\t\tt.Error("This should always pass")
\t}
}

func TestAddition(t *testing.T) {
\tresult := 1 + 1
\tif result != 2 {
\t\tt.Errorf("expected 2, got %d", result)
\t}
}

func TestStringOperations(t *testing.T) {
\tresult := "hello"
\tif result != "hello" {
\t\tt.Errorf("expected hello, got %s", result)
\t}
}
"""
        return {
            "config_file": None,
            "config_content": "# Go uses built-in testing. Run tests with: go test ./...",
            "example_test_file": "example_test.go",
            "example_test_content": example_test_content,
            "main_file": "main.go",
            "main_content": """\
package main

import "fmt"

func main() {
\tfmt.Println("Hello, world!")
}
""",
        }

    elif language == "rust":
        # Rust has built-in testing, no config file needed
        # Write to src/main.rs so cargo init creates a binary crate (not lib)
        example_test_content = """\
fn main() {
    println!("Hello, world!");
}

#[cfg(test)]
mod tests {
    #[test]
    fn test_example_passes() {
        assert!(true, "This should always pass");
    }

    #[test]
    fn test_addition() {
        let result = 1 + 1;
        assert_eq!(result, 2, "1 + 1 should equal 2");
    }

    #[test]
    fn test_string_operations() {
        let result = "hello".to_uppercase();
        assert_eq!(result, "HELLO");
    }
}
"""
        return {
            "config_file": None,
            "config_content": "# Rust uses built-in testing. Run tests with: cargo test",
            "example_test_file": "src/main.rs",
            "example_test_content": example_test_content,
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
