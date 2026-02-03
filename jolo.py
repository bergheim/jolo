#!/usr/bin/env python3
"""jolo - Devcontainer + Git Worktree Launcher.

A CLI tool that bootstraps devcontainer environments with git worktree support.
Target location: ~/.local/bin/jolo

Pronounced "yolo" in Norwegian. Close enough.
"""

import argparse
import json
import os
import random
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

try:
    import argcomplete

    HAVE_ARGCOMPLETE = True
except ImportError:
    HAVE_ARGCOMPLETE = False

try:
    from pick import pick

    HAVE_PICK = True
except ImportError:
    pick = None  # type: ignore
    HAVE_PICK = False

# Word lists for random name generation
ADJECTIVES = [
    "brave",
    "swift",
    "calm",
    "bold",
    "keen",
    "wild",
    "warm",
    "cool",
    "fair",
    "wise",
]
NOUNS = [
    "panda",
    "falcon",
    "river",
    "mountain",
    "oak",
    "wolf",
    "hawk",
    "cedar",
    "fox",
    "bear",
]

# Default configuration
DEFAULT_CONFIG = {
    "base_image": "localhost/emacs-gui:latest",
    "pass_path_anthropic": "api/llm/anthropic",
    "pass_path_openai": "api/llm/openai",
    "agents": ["claude", "gemini", "codex"],
    "agent_commands": {
        "claude": "claude --dangerously-skip-permissions",
        "gemini": "gemini",
        "codex": "codex",
    },
    "base_port": 4000,
}

# Global verbose flag
VERBOSE = False

# Valid languages for --lang flag
VALID_LANGUAGES = frozenset(["python", "go", "typescript", "rust", "shell", "prose", "other"])

# Language options for interactive selector (display names)
LANGUAGE_OPTIONS = ["Python", "Go", "TypeScript", "Rust", "Shell", "Prose/Docs", "Other"]

# Mapping from display names to language codes
LANGUAGE_CODE_MAP = {
    "Python": "python",
    "Go": "go",
    "TypeScript": "typescript",
    "Rust": "rust",
    "Shell": "shell",
    "Prose/Docs": "prose",
    "Other": "other",
}

# Pre-commit hook configurations by language
PRECOMMIT_HOOKS = {
    "python": {
        "repo": "https://github.com/astral-sh/ruff-pre-commit",
        "rev": "v0.8.6",
        "hooks": [
            {"id": "ruff", "args": ["--fix"]},
            {"id": "ruff-format"},
        ],
    },
    "go": {
        "repo": "https://github.com/golangci/golangci-lint",
        "rev": "v1.62.0",
        "hooks": [
            {"id": "golangci-lint"},
        ],
    },
    "typescript": {
        "repo": "https://github.com/biomejs/pre-commit",
        "rev": "v0.6.0",
        "hooks": [
            {"id": "biome-check", "additional_dependencies": ["@biomejs/biome@1.9.0"]},
        ],
    },
    "rust": {
        "repo": "https://github.com/doublify/pre-commit-rust",
        "rev": "v1.0",
        "hooks": [
            {"id": "fmt"},
            {"id": "cargo-check"},
        ],
    },
    "shell": {
        "repo": "https://github.com/shellcheck-py/shellcheck-py",
        "rev": "v0.10.0.1",
        "hooks": [
            {"id": "shellcheck"},
        ],
    },
    "prose": [
        {
            "repo": "https://github.com/igorshubovych/markdownlint-cli",
            "rev": "v0.43.0",
            "hooks": [
                {"id": "markdownlint"},
            ],
        },
        {
            "repo": "https://github.com/codespell-project/codespell",
            "rev": "v2.3.0",
            "hooks": [
                {"id": "codespell"},
            ],
        },
    ],
}


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
        if lang not in PRECOMMIT_HOOKS:
            continue

        hook_config = PRECOMMIT_HOOKS[lang]

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
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
python_functions = ["test_*"]
addopts = "-v --tb=short"
"""
        example_test_content = '''\
"""Example test module demonstrating pytest usage."""


def test_example_passes():
    """Example test that should pass."""
    assert True


def test_addition():
    """Test basic arithmetic."""
    assert 1 + 1 == 2


def test_string_operations():
    """Test string operations."""
    result = "hello".upper()
    assert result == "HELLO"
'''
        return {
            "config_file": "pyproject.toml",
            "config_content": config_content,
            "example_test_file": "tests/test_example.py",
            "example_test_content": example_test_content,
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
        # Go has built-in testing, no config file needed
        example_test_content = """\
package main

import (
\t"testing"

\t"github.com/stretchr/testify/assert"
)

func TestExample(t *testing.T) {
\t// Basic assertion
\tassert.True(t, true, "This should always pass")
}

func TestAddition(t *testing.T) {
\tresult := 1 + 1
\tassert.Equal(t, 2, result, "1 + 1 should equal 2")
}

func TestStringOperations(t *testing.T) {
\tresult := "hello"
\tassert.Equal(t, "hello", result)
}
"""
        return {
            "config_file": None,
            "config_content": "# Go uses built-in testing. Run tests with: go test ./...",
            "example_test_file": "example_test.go",
            "example_test_content": example_test_content,
        }

    elif language == "rust":
        # Rust has built-in testing, no config file needed
        example_test_content = """\
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
            "example_test_file": "src/lib.rs",
            "example_test_content": example_test_content,
        }

    # Shell, prose, other, and unknown languages have no standard test framework
    return {
        "config_file": None,
        "config_content": "",
        "example_test_file": None,
        "example_test_content": "",
    }


def verbose_print(msg: str) -> None:
    """Print message if verbose mode is enabled."""
    if VERBOSE:
        print(f"[verbose] {msg}", file=sys.stderr)


def select_languages_interactive() -> list[str]:
    """Show interactive multi-select picker for project languages.

    Uses the `pick` library for a nice terminal UI. Falls back to simple
    numbered input if pick is not available.

    Returns:
        List of selected language codes (lowercase), e.g. ['python', 'typescript'].
        First selected = primary language. Returns empty list if user cancels.
    """
    if HAVE_PICK:
        try:
            title = "Select project languages (SPACE to toggle, ENTER to confirm):"
            selected = pick(
                LANGUAGE_OPTIONS,
                title,
                multiselect=True,
                min_selection_count=0,
            )
            # pick returns list of (option, index) tuples
            return [LANGUAGE_CODE_MAP[option] for option, _ in selected]
        except KeyboardInterrupt:
            return []
    else:
        # Fallback: simple numbered input
        print("Select project languages (comma-separated numbers):")
        for i, option in enumerate(LANGUAGE_OPTIONS, 1):
            print(f"  {i}. {option}")
        print()

        try:
            response = input("Enter numbers (e.g., 1,3): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return []

        if not response:
            return []

        selected = []
        for part in response.split(","):
            part = part.strip()
            try:
                idx = int(part)
                if 1 <= idx <= len(LANGUAGE_OPTIONS):
                    option = LANGUAGE_OPTIONS[idx - 1]
                    selected.append(LANGUAGE_CODE_MAP[option])
            except ValueError:
                continue  # Skip invalid numbers

        return selected


def parse_lang_arg(value: str) -> list[str]:
    """Parse and validate --lang argument.

    Accepts comma-separated language names, strips whitespace, validates
    each language against VALID_LANGUAGES.

    Args:
        value: Comma-separated string of language names

    Returns:
        List of validated language names

    Raises:
        argparse.ArgumentTypeError: If any language is invalid
    """
    languages = [lang.strip() for lang in value.split(",")]
    invalid = [lang for lang in languages if lang not in VALID_LANGUAGES]
    if invalid:
        valid_list = ", ".join(sorted(VALID_LANGUAGES))
        raise argparse.ArgumentTypeError(
            f"Invalid language(s): {', '.join(invalid)}. "
            f"Valid options: {valid_list}"
        )
    return languages


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
        commands.append(["uv", "init", "--no-readme"])  # non-interactive
        commands.append(["mkdir", "-p", "tests"])
    elif language == "typescript":
        commands.append(["bun", "init", "-y"])  # non-interactive, accept defaults
    elif language == "go":
        commands.append(["go", "mod", "init", project_name])
    elif language == "rust":
        commands.append(["cargo", "new", ".", "--name", project_name])
    elif language == "shell":
        commands.append(["mkdir", "-p", "src"])
    elif language == "prose":
        commands.append(["mkdir", "-p", "docs"])
    else:
        # Default fallback for 'other' or unknown languages
        commands.append(["mkdir", "-p", "src"])

    return commands


def get_precommit_install_command() -> list[str]:
    """Get the command to install pre-commit hooks.

    Returns:
        A list of strings representing the command to run pre-commit install.
        This will be executed via devcontainer exec in the wiring phase.
    """
    return ["pre-commit", "install"]


def get_agent_command(config: dict, agent_name: str | None = None, index: int = 0) -> str:
    """Get the command to run an agent.

    Args:
        config: Configuration dict
        agent_name: Specific agent name, or None for round-robin based on index
        index: Index for round-robin selection (used when agent_name is None)

    Returns:
        The command string to run the agent
    """
    agents = config.get("agents", ["claude"])
    agent_commands = config.get("agent_commands", {})

    if agent_name:
        # Specific agent requested
        name = agent_name
    else:
        # Round-robin through available agents
        name = agents[index % len(agents)]

    # Get command, fall back to just the agent name
    return agent_commands.get(name, name)


def get_agent_name(config: dict, agent_name: str | None = None, index: int = 0) -> str:
    """Get the agent name for a given index.

    Args:
        config: Configuration dict
        agent_name: Specific agent name, or None for round-robin based on index
        index: Index for round-robin selection

    Returns:
        The agent name
    """
    if agent_name:
        return agent_name

    agents = config.get("agents", ["claude"])
    return agents[index % len(agents)]


def parse_mount(arg: str, project_name: str) -> dict:
    """Parse mount argument into structured data.

    Syntax:
        source:target        - relative target, read-write
        source:target:ro     - relative target, read-only
        source:/abs/target   - absolute target
        source:/abs/target:ro - absolute target, read-only

    Returns dict with keys: source, target, readonly
    """
    parts = arg.split(":")
    readonly = False

    # Check for :ro suffix
    if len(parts) >= 2 and parts[-1] == "ro":
        readonly = True
        parts = parts[:-1]

    if len(parts) < 2:
        sys.exit(f"Error: Invalid mount syntax: {arg} (expected source:target)")

    # Handle Windows-style paths or paths with colons
    source = parts[0]
    target = ":".join(parts[1:])

    # Expand ~ in source
    source = os.path.expanduser(source)

    # Resolve target: absolute if starts with /, else relative to workspace
    if not target.startswith("/"):
        target = f"/workspaces/{project_name}/{target}"

    return {"source": source, "target": target, "readonly": readonly}


def parse_copy(arg: str, project_name: str) -> dict:
    """Parse copy argument into structured data.

    Syntax:
        source:target  - copy to target path
        source         - copy to workspace with original basename

    Returns dict with keys: source, target
    """
    if ":" in arg:
        # Split on first colon only (in case target has colons)
        parts = arg.split(":", 1)
        source = parts[0]
        target = parts[1]
    else:
        source = arg
        target = None

    # Expand ~ in source
    source = os.path.expanduser(source)

    # Resolve target
    if target is None:
        # Use basename of source
        target = f"/workspaces/{project_name}/{Path(source).name}"
    elif not target.startswith("/"):
        # Relative target - prepend workspace
        target = f"/workspaces/{project_name}/{target}"

    return {"source": source, "target": target}


def verbose_cmd(cmd: list[str]) -> None:
    """Print command if verbose mode is enabled."""
    if VERBOSE:
        print(f'[verbose] $ {" ".join(cmd)}', file=sys.stderr)


def load_config(global_config_dir: Path | None = None) -> dict:
    """Load configuration from TOML files.

    Config is loaded in order (later overrides earlier):
    1. Default config
    2. Global config: ~/.config/jolo/config.toml
    3. Project config: .jolo.toml in current directory
    """
    config = DEFAULT_CONFIG.copy()

    if global_config_dir is None:
        global_config_dir = Path.home() / ".config" / "jolo"

    # Load global config
    global_config_file = global_config_dir / "config.toml"
    if global_config_file.exists():
        with open(global_config_file, "rb") as f:
            global_cfg = tomllib.load(f)
            config.update(global_cfg)

    # Load project config
    project_config_file = Path.cwd() / ".jolo.toml"
    if project_config_file.exists():
        with open(project_config_file, "rb") as f:
            project_cfg = tomllib.load(f)
            config.update(project_cfg)

    return config


# Base mounts that are always included
BASE_MOUNTS = [
    "source=/tmp/.X11-unix,target=/tmp/.X11-unix,type=bind",
    # Gemini: copy-based isolation (credentials copied to .devcontainer/.gemini-cache/)
    "source=${localWorkspaceFolder}/.devcontainer/.gemini-cache,target=/home/${localEnv:USER}/.gemini,type=bind",
    # Claude: copy-based isolation (credentials copied to .devcontainer/.claude-cache/)
    "source=${localWorkspaceFolder}/.devcontainer/.claude-cache,target=/home/${localEnv:USER}/.claude,type=bind",
    "source=${localWorkspaceFolder}/.devcontainer/.claude.json,target=/home/${localEnv:USER}/.claude.json,type=bind",
    "source=${localEnv:HOME}/.zshrc,target=/home/${localEnv:USER}/.zshrc,type=bind,readonly",
    "source=${localWorkspaceFolder}/.devcontainer/.histfile,target=/home/${localEnv:USER}/.histfile,type=bind",
    "source=${localEnv:HOME}/.tmux.conf,target=/home/${localEnv:USER}/.tmux.conf,type=bind,readonly",
    "source=${localEnv:HOME}/.gitconfig,target=/home/${localEnv:USER}/.gitconfig,type=bind,readonly",
    "source=${localEnv:HOME}/.config/tmux,target=/home/${localEnv:USER}/.config/tmux,type=bind,readonly",
    # Emacs: config copied for isolation, packages mounted readonly from ~/.cache/emacs
    "source=${localWorkspaceFolder}/.devcontainer/.emacs-config,target=/home/${localEnv:USER}/.config/emacs,type=bind",
    "source=${localWorkspaceFolder}/.devcontainer/.emacs-cache,target=/home/${localEnv:USER}/.cache/emacs,type=bind",
    "source=${localEnv:HOME}/.cache/emacs/elpaca,target=/home/${localEnv:USER}/.cache/emacs/elpaca,type=bind,readonly",
    "source=${localEnv:HOME}/.cache/emacs/tree-sitter,target=/home/${localEnv:USER}/.cache/emacs/tree-sitter,type=bind,readonly",
    "source=${localEnv:HOME}/.gnupg/pubring.kbx,target=/home/${localEnv:USER}/.gnupg/pubring.kbx,type=bind,readonly",
    "source=${localEnv:HOME}/.gnupg/trustdb.gpg,target=/home/${localEnv:USER}/.gnupg/trustdb.gpg,type=bind,readonly",
    "source=${localEnv:XDG_RUNTIME_DIR}/gnupg/S.gpg-agent,target=/home/${localEnv:USER}/.gnupg/S.gpg-agent,type=bind",
    "source=${localEnv:HOME}/.config/gh,target=/home/${localEnv:USER}/.config/gh,type=bind,readonly",
]

# Wayland mount - only included when WAYLAND_DISPLAY is set
WAYLAND_MOUNT = "source=${localEnv:XDG_RUNTIME_DIR}/${localEnv:WAYLAND_DISPLAY},target=/tmp/container-runtime/${localEnv:WAYLAND_DISPLAY},type=bind"


def build_devcontainer_json(project_name: str, port: int = 4000) -> str:
    """Build devcontainer.json content dynamically.

    Conditionally includes Wayland mount only if WAYLAND_DISPLAY is set.

    Args:
        project_name: Name of the project/container
        port: Port number for dev servers (default 4000)
    """
    mounts = BASE_MOUNTS.copy()

    # Only add Wayland mount if WAYLAND_DISPLAY is set
    if os.environ.get("WAYLAND_DISPLAY"):
        mounts.append(WAYLAND_MOUNT)

    config = {
        "name": project_name,
        "build": {"dockerfile": "Dockerfile"},
        "runArgs": ["--hostname", project_name],
        "mounts": mounts,
        "containerEnv": {
            "TERM": "xterm-256color",
            "DISPLAY": "${localEnv:DISPLAY}",
            "WAYLAND_DISPLAY": "${localEnv:WAYLAND_DISPLAY}",
            "XDG_RUNTIME_DIR": "/tmp/container-runtime",
            "ANTHROPIC_API_KEY": "${localEnv:ANTHROPIC_API_KEY}",
            "OPENAI_API_KEY": "${localEnv:OPENAI_API_KEY}",
            "PORT": str(port),
        },
    }

    return json.dumps(config, indent=4)


DOCKERFILE_TEMPLATE = """FROM BASE_IMAGE

USER root
RUN apk add --no-cache nodejs npm
LABEL devcontainer.metadata='[{"remoteUser":"CONTAINER_USER"}]'

USER CONTAINER_USER
"""


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="jolo",
        description="Devcontainer + Git Worktree Launcher",
        epilog="Run with no arguments to start devcontainer in current git project.",
    )

    parser.add_argument(
        "--tree",
        nargs="?",
        const="",
        default=None,
        metavar="NAME",
        help="Create git worktree and start devcontainer there. "
        "If NAME not provided, generates random name.",
    )

    parser.add_argument(
        "--create", metavar="NAME", help="Create new project with git + devcontainer"
    )

    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize git + devcontainer in current directory",
    )

    parser.add_argument(
        "--new", action="store_true", help="Remove existing container before starting"
    )

    parser.add_argument(
        "--sync",
        action="store_true",
        help="Regenerate .devcontainer from template using current config",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List running containers and worktrees for current project",
    )

    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="With --list: show all devcontainers globally. "
        "With --stop: stop all containers for project (worktrees + main)",
    )

    parser.add_argument(
        "--stop", action="store_true", help="Stop the devcontainer for current project"
    )

    parser.add_argument(
        "--prune",
        action="store_true",
        help="Clean up stopped containers and stale worktrees for project",
    )

    parser.add_argument(
        "--destroy",
        nargs="?",
        const="",
        default=None,
        metavar="PATH",
        help="Stop and remove all containers for project (before rm -rf)",
    )

    parser.add_argument(
        "--attach",
        action="store_true",
        help="Attach to running container (error if not running)",
    )

    parser.add_argument(
        "--shell",
        action="store_true",
        help="Exec into container with zsh (no tmux)",
    )

    parser.add_argument(
        "--run",
        metavar="CMD",
        help="Exec command directly in container (no tmux)",
    )

    parser.add_argument(
        "--detach", "-d", action="store_true", help="Start container without attaching"
    )

    parser.add_argument(
        "--from",
        dest="from_branch",
        metavar="BRANCH",
        help="With --tree: create worktree from specified branch",
    )

    parser.add_argument(
        "--prompt",
        "-p",
        metavar="PROMPT",
        help="Start AI agent with this prompt (implies --detach)",
    )

    parser.add_argument(
        "--agent",
        default="claude",
        metavar="CMD",
        help="AI agent command to use with --prompt (default: claude)",
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print commands being executed"
    )

    parser.add_argument(
        "--spawn",
        type=int,
        metavar="N",
        help="Create N worktrees in parallel, each with its own container and agent",
    )

    parser.add_argument(
        "--prefix",
        metavar="NAME",
        help="Prefix for worktree names in spawn mode (e.g., --prefix feat creates feat-1, feat-2, ...)",
    )

    parser.add_argument(
        "--mount",
        action="append",
        default=[],
        metavar="SRC:TARGET[:ro]",
        help="Mount host path into container. TARGET is relative to workspace "
        "unless absolute. Append :ro for readonly. Can be repeated.",
    )

    parser.add_argument(
        "--copy",
        action="append",
        default=[],
        metavar="SRC[:TARGET]",
        help="Copy file to workspace before start. TARGET defaults to basename. "
        "Can be repeated.",
    )

    parser.add_argument(
        "--lang",
        type=parse_lang_arg,
        default=None,
        metavar="LANG[,LANG,...]",
        help="Project language(s), comma-separated. "
        "Valid: python, go, typescript, rust, shell, prose, other",
    )

    if HAVE_ARGCOMPLETE:
        argcomplete.autocomplete(parser)

    return parser.parse_args(argv)


def check_tmux_guard() -> None:
    """Check if already inside tmux session."""
    if os.environ.get("TMUX"):
        sys.exit("Error: Already in tmux session. Nested tmux not supported.")


def find_git_root(start_path: Path | None = None) -> Path | None:
    """Find git repository root by traversing up from start_path.

    Returns None if not in a git repository.
    """
    if start_path is None:
        start_path = Path.cwd()

    current = Path(start_path).resolve()

    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent

    # Check root directory too
    if (current / ".git").exists():
        return current

    return None


def generate_random_name() -> str:
    """Generate random adjective-noun name for worktree."""
    adj = random.choice(ADJECTIVES)
    noun = random.choice(NOUNS)
    return f"{adj}-{noun}"


def clear_directory_contents(path: Path) -> None:
    """Remove all contents of a directory without removing the directory itself.

    This preserves the directory inode, which is important for bind mounts.
    """
    if not path.exists():
        return
    for item in path.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def setup_emacs_config(workspace_dir: Path) -> None:
    """Set up Emacs config by copying to .devcontainer/.emacs-config/.

    Copies ~/.config/emacs to .devcontainer/.emacs-config/ so the container
    has an isolated, writable copy of the config. Package directories
    (straight, eln-cache, tree-sitter) are mounted readonly from
    ~/.cache/emacs/ via BASE_MOUNTS.
    """
    home = Path.home()
    emacs_src = home / ".config" / "emacs"
    emacs_dst = workspace_dir / ".devcontainer" / ".emacs-config"
    cache_dst = workspace_dir / ".devcontainer" / ".emacs-cache"

    # Skip if source doesn't exist
    if not emacs_src.exists():
        return

    # Create cache dir (fresh each time is fine)
    cache_dst.mkdir(parents=True, exist_ok=True)

    # Copy entire config directory, preserving the directory itself for bind mounts
    if emacs_dst.exists():
        clear_directory_contents(emacs_dst)
        shutil.copytree(emacs_src, emacs_dst, symlinks=True, dirs_exist_ok=True)
    else:
        shutil.copytree(emacs_src, emacs_dst, symlinks=True)


def setup_credential_cache(workspace_dir: Path) -> None:
    """Copy AI credentials to workspace for container isolation.

    Copies only the necessary files from ~/.claude and ~/.gemini to
    .devcontainer/.claude-cache/ and .devcontainer/.gemini-cache/
    so the container has working auth but can't write back to host directories.

    Note: We clear contents rather than rmtree to preserve directory inodes,
    which keeps bind mounts working in running containers.
    """
    home = Path.home()

    # Claude credentials
    claude_cache = workspace_dir / ".devcontainer" / ".claude-cache"
    if claude_cache.exists():
        clear_directory_contents(claude_cache)
    else:
        claude_cache.mkdir(parents=True)

    claude_dir = home / ".claude"
    for filename in [".credentials.json", "settings.json"]:
        src = claude_dir / filename
        if src.exists():
            shutil.copy2(src, claude_cache / filename)

    statsig_src = claude_dir / "statsig"
    statsig_dst = claude_cache / "statsig"
    if statsig_src.exists():
        if statsig_dst.exists():
            shutil.rmtree(statsig_dst)
        shutil.copytree(statsig_src, statsig_dst)

    claude_json_src = home / ".claude.json"
    claude_json_dst = workspace_dir / ".devcontainer" / ".claude.json"
    if claude_json_src.exists():
        shutil.copy2(claude_json_src, claude_json_dst)

    # Gemini credentials
    gemini_cache = workspace_dir / ".devcontainer" / ".gemini-cache"
    if gemini_cache.exists():
        clear_directory_contents(gemini_cache)
    else:
        gemini_cache.mkdir(parents=True)

    gemini_dir = home / ".gemini"
    for filename in ["settings.json", "google_accounts.json", "oauth_creds.json"]:
        src = gemini_dir / filename
        if src.exists():
            shutil.copy2(src, gemini_cache / filename)


def copy_template_files(target_dir: Path) -> None:
    """Copy template files to the target directory.

    Copies AGENTS.md, CLAUDE.md, GEMINI.md, .gitignore, and .editorconfig
    from the templates/ directory relative to jolo.py.

    Note: .pre-commit-config.yaml is generated dynamically based on language selection,
    not copied from templates.

    Prints a warning if templates/ directory doesn't exist but continues.
    """
    templates_dir = Path(__file__).resolve().parent / "templates"

    if not templates_dir.exists():
        print(f"Warning: Templates directory not found: {templates_dir}", file=sys.stderr)
        return

    template_files = ["AGENTS.md", "CLAUDE.md", "GEMINI.md", ".gitignore", ".editorconfig"]

    for filename in template_files:
        src = templates_dir / filename
        if src.exists():
            dst = target_dir / filename
            shutil.copy2(src, dst)
            verbose_print(f"Copied template: {filename}")


def scaffold_devcontainer(
    project_name: str,
    target_dir: Path | None = None,
    config: dict | None = None,
    port: int = 4000,
) -> bool:
    """Create .devcontainer directory with templates.

    Returns True if created, False if already exists.
    """
    if target_dir is None:
        target_dir = Path.cwd()
    if config is None:
        config = DEFAULT_CONFIG

    devcontainer_dir = target_dir / ".devcontainer"

    if devcontainer_dir.exists():
        return False

    devcontainer_dir.mkdir(parents=True)

    # Get current username for Dockerfile
    username = os.environ.get("USER", "dev")

    # Write devcontainer.json (dynamically built based on environment)
    json_content = build_devcontainer_json(project_name, port=port)
    (devcontainer_dir / "devcontainer.json").write_text(json_content)

    # Write Dockerfile with substituted base image and username
    dockerfile_content = DOCKERFILE_TEMPLATE.replace("BASE_IMAGE", config["base_image"])
    dockerfile_content = dockerfile_content.replace("CONTAINER_USER", username)
    (devcontainer_dir / "Dockerfile").write_text(dockerfile_content)

    return True


def sync_devcontainer(
    project_name: str,
    target_dir: Path | None = None,
    config: dict | None = None,
    port: int = 4000,
) -> None:
    """Regenerate .devcontainer from template, overwriting existing files.

    Unlike scaffold_devcontainer, this always writes the files even if
    .devcontainer already exists.
    """
    if target_dir is None:
        target_dir = Path.cwd()
    if config is None:
        config = DEFAULT_CONFIG

    devcontainer_dir = target_dir / ".devcontainer"
    devcontainer_dir.mkdir(parents=True, exist_ok=True)

    # Get current username for Dockerfile
    username = os.environ.get("USER", "dev")

    # Write devcontainer.json (dynamically built based on environment)
    json_content = build_devcontainer_json(project_name, port=port)
    (devcontainer_dir / "devcontainer.json").write_text(json_content)

    # Write Dockerfile with substituted base image and username
    dockerfile_content = DOCKERFILE_TEMPLATE.replace("BASE_IMAGE", config["base_image"])
    dockerfile_content = dockerfile_content.replace("CONTAINER_USER", username)
    (devcontainer_dir / "Dockerfile").write_text(dockerfile_content)

    print(f"Synced .devcontainer/ with current config")


def get_secrets(config: dict | None = None) -> dict[str, str]:
    """Get API secrets from pass or environment variables."""
    if config is None:
        config = DEFAULT_CONFIG

    secrets = {}

    # Check if pass is available
    pass_available = shutil.which("pass") is not None

    if pass_available:
        # Try to get secrets from pass using configured paths
        for key, pass_path in [
            ("ANTHROPIC_API_KEY", config["pass_path_anthropic"]),
            ("OPENAI_API_KEY", config["pass_path_openai"]),
        ]:
            try:
                result = subprocess.run(
                    ["pass", "show", pass_path],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    secrets[key] = result.stdout.strip()
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                pass

    # Fallback to environment variables for any missing secrets
    for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]:
        if key not in secrets:
            secrets[key] = os.environ.get(key, "")

    return secrets


def get_container_name(project_path: str, worktree_name: str | None) -> str:
    """Generate container name from project path and optional worktree name."""
    project_name = Path(project_path.rstrip("/")).name.lower()

    if worktree_name:
        return f"{project_name}-{worktree_name}"
    return project_name


def get_worktree_path(project_path: str, worktree_name: str) -> Path:
    """Compute worktree path: ../PROJECT-worktrees/NAME."""
    project_path = Path(project_path.rstrip("/"))
    project_name = project_path.name
    worktrees_dir = project_path.parent / f"{project_name}-worktrees"
    return worktrees_dir / worktree_name


def validate_tree_mode() -> Path:
    """Validate that --tree mode is being run inside a git repo.

    Returns the git root path.
    """
    git_root = find_git_root()
    if git_root is None:
        sys.exit("Error: Not in a git repository. --tree requires an existing repo.")
    return git_root


def validate_create_mode(name: str) -> None:
    """Validate that --create mode is NOT being run inside a git repo."""
    git_root = find_git_root()
    if git_root is not None:
        sys.exit("Error: Already in a git repository. Use --tree for worktrees.")

    target_dir = Path.cwd() / name
    if target_dir.exists():
        sys.exit(f"Error: Directory already exists: {target_dir}")


def validate_init_mode() -> None:
    """Validate that --init mode is NOT being run inside a git repo."""
    git_root = find_git_root()
    if git_root is not None:
        sys.exit("Error: Already in a git repository. Use jolo without --init.")


def add_user_mounts(devcontainer_json_path: Path, mounts: list[dict]) -> None:
    """Add user-specified mounts to devcontainer.json.

    Args:
        devcontainer_json_path: Path to devcontainer.json
        mounts: List of mount dicts with keys: source, target, readonly
    """
    if not mounts:
        return

    content = json.loads(devcontainer_json_path.read_text())

    if "mounts" not in content:
        content["mounts"] = []

    for mount in mounts:
        mount_str = f"source={mount['source']},target={mount['target']},type=bind"
        if mount["readonly"]:
            mount_str += ",readonly"
        content["mounts"].append(mount_str)

    devcontainer_json_path.write_text(json.dumps(content, indent=4))


def copy_user_files(copies: list[dict], workspace_dir: Path) -> None:
    """Copy user-specified files to workspace.

    Args:
        copies: List of copy dicts with keys: source, target
        workspace_dir: The workspace directory (project root)
    """
    for copy_spec in copies:
        source = Path(copy_spec["source"])
        # Convert absolute container path to workspace-relative path
        target_path = copy_spec["target"]
        if target_path.startswith("/workspaces/"):
            # Strip /workspaces/project/ prefix to get relative path
            parts = target_path.split("/", 3)
            if len(parts) >= 4:
                relative = parts[3]
                target = workspace_dir / relative
            else:
                # Just the project dir, use source basename
                target = workspace_dir / source.name
        else:
            # Absolute path outside workspace - copy there directly
            target = Path(target_path)

        if not source.exists():
            sys.exit(f"Error: Copy source does not exist: {source}")

        # Create parent directories if needed
        target.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        shutil.copy2(source, target)
        verbose_print(f"Copied {source} -> {target}")


def add_worktree_git_mount(devcontainer_json_path: Path, main_git_dir: Path) -> None:
    """Add a mount for the main repo's .git directory to devcontainer.json.

    This is needed for worktrees because git worktrees use a .git file that
    points to the main repo's .git/worktrees/NAME directory with an absolute
    path. We need to mount that path into the container.
    """
    content = json.loads(devcontainer_json_path.read_text())

    if "mounts" not in content:
        content["mounts"] = []

    # Mount the main .git directory at the same absolute path in the container
    git_mount = f"source={main_git_dir},target={main_git_dir},type=bind"
    content["mounts"].append(git_mount)

    devcontainer_json_path.write_text(json.dumps(content, indent=4))


def is_container_running(workspace_dir: Path) -> bool:
    """Check if devcontainer for workspace is already running."""
    cmd = ["devcontainer", "exec", "--workspace-folder", str(workspace_dir), "true"]
    verbose_cmd(cmd)
    result = subprocess.run(cmd, capture_output=True, cwd=workspace_dir)
    return result.returncode == 0


def devcontainer_up(workspace_dir: Path, remove_existing: bool = False) -> bool:
    """Start devcontainer with devcontainer up.

    Returns True if successful.
    """
    # Ensure histfile exists as a file (otherwise mount creates a directory)
    histfile = workspace_dir / ".devcontainer" / ".histfile"
    histfile.touch(exist_ok=True)

    cmd = ["devcontainer", "up", "--workspace-folder", str(workspace_dir)]

    if remove_existing:
        cmd.append("--remove-existing-container")

    verbose_cmd(cmd)
    result = subprocess.run(cmd, cwd=workspace_dir)
    return result.returncode == 0


def devcontainer_exec_tmux(workspace_dir: Path) -> None:
    """Execute into container and attach/create tmux session."""
    cmd = [
        "devcontainer",
        "exec",
        "--workspace-folder",
        str(workspace_dir),
        "sh",
        "-c",
        "tmux attach-session -t dev || tmux new-session -s dev",
    ]

    verbose_cmd(cmd)
    subprocess.run(cmd, cwd=workspace_dir)


def devcontainer_exec_command(workspace_dir: Path, command: str) -> None:
    """Execute a command directly in container (no tmux)."""
    cmd = [
        "devcontainer",
        "exec",
        "--workspace-folder",
        str(workspace_dir),
        "sh",
        "-c",
        command,
    ]

    verbose_cmd(cmd)
    subprocess.run(cmd, cwd=workspace_dir)


def devcontainer_exec_prompt(workspace_dir: Path, agent: str, prompt: str) -> None:
    """Start AI agent with a prompt in a detached tmux session."""
    quoted_prompt = shlex.quote(prompt)
    # Claude needs --dangerously-skip-permissions since shell aliases aren't loaded
    if agent == "claude":
        agent_cmd = "claude --dangerously-skip-permissions"
    else:
        agent_cmd = agent
    tmux_cmd = f"tmux new-session -d -s dev {agent_cmd} {quoted_prompt}"
    cmd = [
        "devcontainer",
        "exec",
        "--workspace-folder",
        str(workspace_dir),
        "sh",
        "-c",
        tmux_cmd,
    ]

    verbose_cmd(cmd)
    subprocess.run(cmd, cwd=workspace_dir)


def list_worktrees(git_root: Path) -> list[tuple[Path, str, str]]:
    """List git worktrees for a repository.

    Returns list of tuples: (path, commit, branch)
    """
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=git_root,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return []

    worktrees = []
    current_worktree = {}

    for line in result.stdout.strip().split("\n"):
        if not line:
            if current_worktree:
                worktrees.append(
                    (
                        Path(current_worktree.get("worktree", "")),
                        current_worktree.get("HEAD", "")[:7],
                        current_worktree.get("branch", "").replace("refs/heads/", ""),
                    )
                )
                current_worktree = {}
            continue

        if line.startswith("worktree "):
            current_worktree["worktree"] = line[9:]
        elif line.startswith("HEAD "):
            current_worktree["HEAD"] = line[5:]
        elif line.startswith("branch "):
            current_worktree["branch"] = line[7:]

    # Don't forget last worktree
    if current_worktree:
        worktrees.append(
            (
                Path(current_worktree.get("worktree", "")),
                current_worktree.get("HEAD", "")[:7],
                current_worktree.get("branch", "").replace("refs/heads/", ""),
            )
        )

    return worktrees


def find_project_workspaces(git_root: Path) -> list[tuple[Path, str]]:
    """Find all workspace directories for a project.

    Returns list of tuples: (path, type) where type is 'main' or worktree name.
    """
    project_name = git_root.name
    workspaces = [(git_root, "main")]

    # Check for worktrees directory
    worktrees_dir = git_root.parent / f"{project_name}-worktrees"
    if worktrees_dir.exists():
        worktrees = list_worktrees(git_root)
        for wt_path, _, branch in worktrees:
            if wt_path != git_root:
                workspaces.append((wt_path, branch or wt_path.name))

    return workspaces


def get_container_runtime() -> str | None:
    """Detect available container runtime (docker or podman)."""
    if shutil.which("docker"):
        return "docker"
    if shutil.which("podman"):
        return "podman"
    return None


def list_all_devcontainers() -> list[tuple[str, str, str]]:
    """List all running devcontainers globally.

    Returns list of tuples: (container_name, workspace_folder, status)
    """
    runtime = get_container_runtime()
    if runtime is None:
        return []

    # Query containers with devcontainer label
    result = subprocess.run(
        [
            runtime,
            "ps",
            "-a",
            "--filter",
            "label=devcontainer.local_folder",
            "--format",
            '{{.Names}}\t{{.Label "devcontainer.local_folder"}}\t{{.State}}',
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return []

    containers = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            name, folder, state = parts[0], parts[1], parts[2]
            containers.append((name, folder, state))

    return containers


def run_list_global_mode() -> None:
    """Run --list --all mode: show all running devcontainers globally."""
    runtime = get_container_runtime()
    if runtime is None:
        sys.exit("Error: No container runtime found (docker or podman required)")

    containers = list_all_devcontainers()

    print("Running devcontainers:")
    print()

    running_containers = [(n, f, s) for n, f, s in containers if s == "running"]

    if not running_containers:
        print("  (none)")
    else:
        for name, folder, _ in running_containers:
            print(f"  {name:<24} {folder}")

    # Also show stopped containers
    stopped_containers = [(n, f, s) for n, f, s in containers if s != "running"]
    if stopped_containers:
        print()
        print("Stopped devcontainers:")
        print()
        for name, folder, state in stopped_containers:
            print(f"  {name:<24} {folder}  ({state})")


def get_container_for_workspace(workspace_dir: Path) -> str | None:
    """Get container name for a workspace directory.

    Returns container name if found, None otherwise.
    """
    runtime = get_container_runtime()
    if runtime is None:
        return None

    # Query containers with matching workspace folder
    result = subprocess.run(
        [
            runtime,
            "ps",
            "-a",
            "--filter",
            f"label=devcontainer.local_folder={workspace_dir}",
            "--format",
            "{{.Names}}",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return None

    return result.stdout.strip().split("\n")[0]


def stop_container(workspace_dir: Path) -> bool:
    """Stop the devcontainer for a workspace.

    Returns True if stopped successfully, False otherwise.
    """
    runtime = get_container_runtime()
    if runtime is None:
        print(
            "Error: No container runtime found (docker or podman required)",
            file=sys.stderr,
        )
        return False

    container_name = get_container_for_workspace(workspace_dir)
    if container_name is None:
        print(f"No container found for {workspace_dir}", file=sys.stderr)
        return False

    cmd = [runtime, "stop", container_name]
    verbose_cmd(cmd)
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"Stopped: {container_name}")
        return True
    else:
        print(f"Failed to stop {container_name}: {result.stderr}", file=sys.stderr)
        return False


def run_stop_mode(args: argparse.Namespace) -> None:
    """Run --stop mode: stop the devcontainer for current project."""
    git_root = find_git_root()

    if git_root is None:
        sys.exit("Error: Not in a git repository.")

    if args.all:
        # Stop all containers for this project (worktrees first, then main)
        workspaces = find_project_workspaces(git_root)
        # Reverse so worktrees come before main
        worktrees = [(p, t) for p, t in workspaces if t != "main"]
        main = [(p, t) for p, t in workspaces if t == "main"]

        any_stopped = False
        for ws_path, ws_type in worktrees + main:
            # Skip if directory doesn't exist (stale worktree)
            if not ws_path.exists():
                continue
            if is_container_running(ws_path):
                if stop_container(ws_path):
                    any_stopped = True

        if not any_stopped:
            print("No running containers found for this project")
    else:
        if not stop_container(git_root):
            sys.exit(1)


def find_containers_for_project(
    git_root: Path, state_filter: str | None = None
) -> list[tuple[str, str, str]]:
    """Find containers for a project.

    Args:
        git_root: The git repository root path
        state_filter: If set, only return containers in this state (e.g., "running")
                      If None, return all containers

    Returns list of tuples: (container_name, workspace_folder, state)
    """
    runtime = get_container_runtime()
    if runtime is None:
        return []

    project_name = git_root.name

    # Get all containers (including stopped) with devcontainer label
    all_containers = list_all_devcontainers()

    # Filter to containers that match this project
    matched = []
    for name, folder, state in all_containers:
        # Check if folder is under this project or its worktrees
        folder_path = Path(folder)
        if (
            folder_path == git_root
            or folder_path.parent.name == f"{project_name}-worktrees"
        ):
            if state_filter is None or state == state_filter:
                matched.append((name, folder, state))

    return matched


def find_stopped_containers_for_project(git_root: Path) -> list[tuple[str, str]]:
    """Find stopped containers for a project.

    Returns list of tuples: (container_name, workspace_folder)
    """
    containers = find_containers_for_project(git_root)
    return [(name, folder) for name, folder, state in containers if state != "running"]


def find_stale_worktrees(git_root: Path) -> list[tuple[Path, str]]:
    """Find worktrees that no longer exist on disk.

    Returns list of tuples: (worktree_path, branch_name)
    """
    worktrees = list_worktrees(git_root)
    stale = []

    for wt_path, _, branch in worktrees:
        if wt_path == git_root:
            continue  # Skip main repo
        if not wt_path.exists():
            stale.append((wt_path, branch))

    return stale


def remove_container(container_name: str) -> bool:
    """Remove a container."""
    runtime = get_container_runtime()
    if runtime is None:
        return False

    cmd = [runtime, "rm", container_name]
    verbose_cmd(cmd)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def remove_worktree(git_root: Path, worktree_path: Path) -> bool:
    """Remove a git worktree."""
    cmd = ["git", "worktree", "remove", "--force", str(worktree_path)]
    verbose_cmd(cmd)
    result = subprocess.run(cmd, cwd=git_root, capture_output=True, text=True)
    return result.returncode == 0


def run_prune_global_mode() -> None:
    """Run --prune --all mode: clean up all stopped devcontainers globally."""
    all_containers = list_all_devcontainers()
    stopped_containers = [
        (name, folder) for name, folder, state in all_containers if state != "running"
    ]

    if not stopped_containers:
        print("No stopped containers to prune.")
        return

    print("Stopped containers:")
    for name, folder in stopped_containers:
        print(f"  {name:<24} {folder}")
    print()

    # Prompt for confirmation
    try:
        response = input("Remove these? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if response.lower() != "y":
        print("Cancelled.")
        return

    for name, _ in stopped_containers:
        if remove_container(name):
            print(f"Removed: {name}")
        else:
            print(f"Failed to remove: {name}", file=sys.stderr)


def run_prune_mode(args: argparse.Namespace) -> None:
    """Run --prune mode: clean up stopped containers and stale worktrees."""
    git_root = find_git_root()

    # Prune all stopped containers if --all flag or not in a git repo
    if args.all or git_root is None:
        run_prune_global_mode()
        return

    # Find stopped containers
    stopped_containers = find_stopped_containers_for_project(git_root)

    # Find stale worktrees
    stale_worktrees = find_stale_worktrees(git_root)

    if not stopped_containers and not stale_worktrees:
        print("Nothing to prune.")
        return

    # Show what will be pruned
    if stopped_containers:
        print("Stopped containers:")
        for name, folder in stopped_containers:
            print(f"  {name:<24} {folder}")
        print()

    if stale_worktrees:
        print("Stale worktrees:")
        for wt_path, branch in stale_worktrees:
            print(f"  {wt_path.name:<24} ({branch})")
        print()

    # Prompt for confirmation
    try:
        response = input("Remove these? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if response.lower() != "y":
        print("Cancelled.")
        return

    # Remove containers
    for name, _ in stopped_containers:
        if remove_container(name):
            print(f"Removed container: {name}")
        else:
            print(f"Failed to remove container: {name}", file=sys.stderr)

    # Remove worktrees
    for wt_path, _ in stale_worktrees:
        if remove_worktree(git_root, wt_path):
            print(f"Removed worktree: {wt_path.name}")
        else:
            print(f"Failed to remove worktree: {wt_path.name}", file=sys.stderr)


def run_destroy_mode(args: argparse.Namespace) -> None:
    """Run --destroy mode: stop and remove all containers for project."""
    # If path argument provided, use it; otherwise detect from cwd
    if args.destroy:
        target_path = Path(args.destroy).resolve()
        if not target_path.exists():
            sys.exit(f"Error: Path does not exist: {target_path}")
        git_root = find_git_root(target_path)
        if git_root is None:
            sys.exit(f"Error: Not a git repository: {target_path}")
    else:
        git_root = find_git_root()
        if git_root is None:
            sys.exit("Error: Not in a git repository.")

    runtime = get_container_runtime()
    if runtime is None:
        sys.exit("Error: No container runtime found (docker or podman required)")

    # Find all containers for this project
    containers = find_containers_for_project(git_root)

    if not containers:
        print("No containers found for this project.")
        return

    # Show what will be destroyed
    print(f"Project: {git_root.name}")
    print()
    print("Containers to destroy:")
    for name, folder, state in containers:
        print(f"  {name:<24} {state:<10} {folder}")
    print()

    # Prompt for confirmation
    try:
        response = input("Stop and remove these containers? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if response.lower() != "y":
        print("Cancelled.")
        return

    # Stop running containers first
    for name, folder, state in containers:
        if state == "running":
            cmd = [runtime, "stop", name]
            verbose_cmd(cmd)
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"Stopped: {name}")
            else:
                print(f"Failed to stop {name}: {result.stderr}", file=sys.stderr)

    # Remove all containers
    for name, folder, state in containers:
        if remove_container(name):
            print(f"Removed: {name}")
        else:
            print(f"Failed to remove: {name}", file=sys.stderr)

    print()
    print("Containers removed.")
    print()

    # Ask about directory removal
    worktrees_dir = git_root.parent / f"{git_root.name}-worktrees"
    dirs_to_remove = [git_root]
    if worktrees_dir.exists():
        dirs_to_remove.append(worktrees_dir)

    print("Directories:")
    for d in dirs_to_remove:
        print(f"  {d}")
    print()

    try:
        response = input("Also remove these directories? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        print()
        print(f"Directories preserved. To remove later: rm -rf {git_root}")
        return

    if response.lower() != "y":
        print(f"Directories preserved. To remove later: rm -rf {git_root}")
        return

    for d in dirs_to_remove:
        try:
            shutil.rmtree(d)
            print(f"Removed: {d}")
        except Exception as e:
            print(f"Failed to remove {d}: {e}", file=sys.stderr)


def run_attach_mode(args: argparse.Namespace) -> None:
    """Run --attach mode: attach to running container."""
    git_root = find_git_root()

    if git_root is None:
        sys.exit("Error: Not in a git repository.")

    if not is_container_running(git_root):
        sys.exit("Error: Container is not running. Use jolo to start it.")

    # Direct exec modes (no tmux)
    if args.shell:
        devcontainer_exec_command(git_root, "zsh")
        return

    if args.run:
        devcontainer_exec_command(git_root, args.run)
        return

    # Attach to tmux
    devcontainer_exec_tmux(git_root)


def run_list_mode(args: argparse.Namespace) -> None:
    """Run --list mode: show containers and worktrees for current project."""
    git_root = find_git_root()

    # Show all containers if --all flag or not in a git repo
    if args.all or git_root is None:
        run_list_global_mode()
        return

    project_name = git_root.name

    print(f"Project: {project_name}")
    print()

    # Find all workspaces
    workspaces = find_project_workspaces(git_root)

    # Check container status for each
    print("Containers:")
    any_running = False
    for ws_path, ws_type in workspaces:
        devcontainer_dir = ws_path / ".devcontainer"
        if devcontainer_dir.exists():
            running = is_container_running(ws_path)
            status = "running" if running else "stopped"
            status_marker = "*" if running else " "
            print(f"  {status_marker} {ws_path.name:<20} {status:<10} ({ws_type})")
            if running:
                any_running = True

    if not any_running:
        print("  (no containers running)")
    print()

    # List worktrees
    worktrees = list_worktrees(git_root)
    if len(worktrees) > 1:  # More than just main repo
        print("Worktrees:")
        for wt_path, commit, branch in worktrees:
            if wt_path == git_root:
                continue  # Skip main repo
            print(f"    {wt_path.name:<20} {branch:<15} [{commit}]")
    else:
        print("Worktrees: (none)")


def run_default_mode(args: argparse.Namespace) -> None:
    """Run default mode: start devcontainer in current git project."""
    git_root = find_git_root()

    if git_root is None:
        sys.exit("Error: Not in a git repository. Use --init to initialize here.")

    os.chdir(git_root)
    project_name = git_root.name

    # Load config
    config = load_config()

    # Scaffold .devcontainer if missing
    scaffold_devcontainer(project_name, config=config)

    # Add user-specified mounts to devcontainer.json
    if args.mount:
        parsed_mounts = [parse_mount(m, project_name) for m in args.mount]
        devcontainer_json = git_root / ".devcontainer" / "devcontainer.json"
        add_user_mounts(devcontainer_json, parsed_mounts)

    # Copy user-specified files
    if args.copy:
        parsed_copies = [parse_copy(c, project_name) for c in args.copy]
        copy_user_files(parsed_copies, git_root)

    # Set up secrets in environment
    secrets = get_secrets(config)
    os.environ.update(secrets)

    # Copy AI credentials for container isolation
    setup_credential_cache(git_root)

    # Set up Emacs config (copy config files, symlink packages)
    setup_emacs_config(git_root)

    # Start devcontainer only if not already running (or --new forces restart)
    if args.new or not is_container_running(git_root):
        if not devcontainer_up(git_root, remove_existing=args.new):
            sys.exit("Error: Failed to start devcontainer")

    if args.prompt:
        devcontainer_exec_prompt(git_root, args.agent, args.prompt)
        print(f"Started {args.agent} in: {project_name}")
        return

    if args.detach:
        print(f"Container started: {project_name}")
        return

    # Direct exec modes (no tmux)
    if args.shell:
        devcontainer_exec_command(git_root, "zsh")
        return

    if args.run:
        devcontainer_exec_command(git_root, args.run)
        return

    # Attach to tmux
    devcontainer_exec_tmux(git_root)


def branch_exists(git_root: Path, branch: str) -> bool:
    """Check if a branch or ref exists in the repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch], cwd=git_root, capture_output=True
    )
    return result.returncode == 0


def get_or_create_worktree(
    git_root: Path,
    worktree_name: str,
    worktree_path: Path,
    config: dict | None = None,
    from_branch: str | None = None,
) -> Path:
    """Get existing worktree or create a new one.

    Returns the worktree path. If the worktree already exists, just returns
    the path. If it doesn't exist, creates the worktree with devcontainer.

    If from_branch is specified, creates the worktree from that branch.
    """
    if worktree_path.exists():
        print(f"Using existing worktree: {worktree_path}")
        return worktree_path

    # Create worktrees directory if needed
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    # Create git worktree with new branch
    cmd = ["git", "worktree", "add", "-b", worktree_name, str(worktree_path)]
    if from_branch:
        cmd.append(from_branch)

    verbose_cmd(cmd)
    result = subprocess.run(cmd, cwd=git_root)
    if result.returncode != 0:
        sys.exit("Error: Failed to create git worktree")

    # Set up .devcontainer in worktree
    src_devcontainer = git_root / ".devcontainer"
    dst_devcontainer = worktree_path / ".devcontainer"

    if dst_devcontainer.exists():
        # Already checked out by git worktree (was committed to repo)
        pass
    elif src_devcontainer.exists():
        # Copy from main repo (not committed, just local)
        shutil.copytree(src_devcontainer, dst_devcontainer, symlinks=True)
    else:
        # Scaffold new .devcontainer
        container_name = get_container_name(str(git_root), worktree_name)
        scaffold_devcontainer(container_name, worktree_path, config=config)

    # Add mount for main repo's .git directory so worktree git operations work
    main_git_dir = git_root / ".git"
    devcontainer_json = dst_devcontainer / "devcontainer.json"
    add_worktree_git_mount(devcontainer_json, main_git_dir)

    print(f"Created worktree: {worktree_path}")
    print(f"Branch: {worktree_name}")

    return worktree_path


def run_tree_mode(args: argparse.Namespace) -> None:
    """Run --tree mode: create worktree and start devcontainer."""
    git_root = validate_tree_mode()

    # Validate --from branch if specified
    if args.from_branch and not branch_exists(git_root, args.from_branch):
        sys.exit(f"Error: Branch does not exist: {args.from_branch}")

    # Generate name if not provided
    worktree_name = args.tree if args.tree else generate_random_name()

    # Compute paths
    worktree_path = get_worktree_path(str(git_root), worktree_name)

    # Load config
    config = load_config()

    # Get or create the worktree
    worktree_path = get_or_create_worktree(
        git_root,
        worktree_name,
        worktree_path,
        config=config,
        from_branch=args.from_branch,
    )

    # Add user-specified mounts to devcontainer.json
    if args.mount:
        parsed_mounts = [parse_mount(m, worktree_name) for m in args.mount]
        devcontainer_json = worktree_path / ".devcontainer" / "devcontainer.json"
        add_user_mounts(devcontainer_json, parsed_mounts)

    # Copy user-specified files
    if args.copy:
        parsed_copies = [parse_copy(c, worktree_name) for c in args.copy]
        copy_user_files(parsed_copies, worktree_path)

    # Set up secrets in environment
    secrets = get_secrets(config)
    os.environ.update(secrets)

    # Copy AI credentials for container isolation
    setup_credential_cache(worktree_path)

    # Set up Emacs config (copy config files, symlink packages)
    setup_emacs_config(worktree_path)

    # Start devcontainer only if not already running (or --new forces restart)
    if args.new or not is_container_running(worktree_path):
        if not devcontainer_up(worktree_path, remove_existing=args.new):
            sys.exit("Error: Failed to start devcontainer")

    if args.prompt:
        devcontainer_exec_prompt(worktree_path, args.agent, args.prompt)
        print(f"Started {args.agent} in: {worktree_path.name}")
        return

    if args.detach:
        print(f"Container started: {worktree_path.name}")
        return

    # Direct exec modes (no tmux)
    if args.shell:
        devcontainer_exec_command(worktree_path, "zsh")
        return

    if args.run:
        devcontainer_exec_command(worktree_path, args.run)
        return

    # Attach to tmux
    devcontainer_exec_tmux(worktree_path)


def run_create_mode(args: argparse.Namespace) -> None:
    """Run --create mode: create new project with devcontainer."""
    validate_create_mode(args.create)

    project_name = args.create
    project_path = Path.cwd() / project_name

    # Load config
    config = load_config()

    # Get languages from --lang or interactive selector
    if args.lang:
        languages = args.lang
    else:
        languages = select_languages_interactive()
        # Abort if user cancels (Ctrl+C or no selection)
        if not languages:
            print("No languages selected, aborting.", file=sys.stderr)
            sys.exit(1)

    # Primary language is the first in the list
    primary_language = languages[0] if languages else 'other'

    # Create project directory
    project_path.mkdir()

    # Copy template files (AGENTS.md, CLAUDE.md, .gitignore, .editorconfig, etc.)
    copy_template_files(project_path)

    # Generate and write .pre-commit-config.yaml based on selected languages
    precommit_content = generate_precommit_config(languages)
    (project_path / ".pre-commit-config.yaml").write_text(precommit_content)
    verbose_print(f"Generated .pre-commit-config.yaml for languages: {', '.join(languages)}")

    # Write test framework config for primary language
    test_config = get_test_framework_config(primary_language)
    if test_config.get("config_file"):
        config_file = project_path / test_config["config_file"]
        if config_file.exists():
            # Append to existing file
            existing = config_file.read_text()
            config_file.write_text(existing + "\n" + test_config["config_content"])
        else:
            config_file.write_text(test_config["config_content"])
        verbose_print(f"Wrote test framework config: {test_config['config_file']}")

    # Write example test file for primary language
    if test_config.get("example_test_file") and test_config.get("example_test_content"):
        example_test_path = project_path / test_config["example_test_file"]
        example_test_path.parent.mkdir(parents=True, exist_ok=True)
        example_test_path.write_text(test_config["example_test_content"])
        verbose_print(f"Wrote example test: {test_config['example_test_file']}")

    # Write type checker config for primary language
    type_config = get_type_checker_config(primary_language)
    if type_config:
        config_file = project_path / type_config["config_file"]
        if config_file.exists():
            # Append to existing file (e.g., pyproject.toml)
            existing = config_file.read_text()
            config_file.write_text(existing + "\n" + type_config["config_content"])
        else:
            config_file.write_text(type_config["config_content"])
        verbose_print(f"Wrote type checker config: {type_config['config_file']}")

    # Initialize git repo
    cmd = ["git", "init"]
    verbose_cmd(cmd)
    result = subprocess.run(cmd, cwd=project_path)
    if result.returncode != 0:
        sys.exit("Error: Failed to initialize git repository")

    # Scaffold .devcontainer
    scaffold_devcontainer(project_name, project_path, config=config)

    # Initial commit with .devcontainer
    cmd = ["git", "add", ".devcontainer"]
    verbose_cmd(cmd)
    subprocess.run(cmd, cwd=project_path)

    cmd = ["git", "commit", "-m", "Initial commit with devcontainer setup"]
    verbose_cmd(cmd)
    subprocess.run(cmd, cwd=project_path)

    print(f"Created project: {project_path}")

    # Change to project directory for devcontainer commands
    os.chdir(project_path)

    # Add user-specified mounts to devcontainer.json
    if args.mount:
        parsed_mounts = [parse_mount(m, project_name) for m in args.mount]
        devcontainer_json = project_path / ".devcontainer" / "devcontainer.json"
        add_user_mounts(devcontainer_json, parsed_mounts)

    # Copy user-specified files
    if args.copy:
        parsed_copies = [parse_copy(c, project_name) for c in args.copy]
        copy_user_files(parsed_copies, project_path)

    # Set up secrets in environment
    secrets = get_secrets(config)
    os.environ.update(secrets)

    # Copy AI credentials for container isolation
    setup_credential_cache(project_path)

    # Set up Emacs config (copy config files, symlink packages)
    setup_emacs_config(project_path)

    # Start devcontainer (always remove existing for fresh project)
    if not devcontainer_up(project_path, remove_existing=True):
        sys.exit("Error: Failed to start devcontainer")

    # Run project init commands for primary language inside the container
    init_commands = get_project_init_commands(primary_language, project_name)
    for cmd_parts in init_commands:
        cmd_str = " ".join(cmd_parts)
        verbose_print(f"Running in container: {cmd_str}")
        devcontainer_exec_command(project_path, cmd_str)

    if args.prompt:
        devcontainer_exec_prompt(project_path, args.agent, args.prompt)
        print(f"Started {args.agent} in: {project_name}")
        return

    if args.detach:
        print(f"Container started: {project_name}")
        return

    # Direct exec modes (no tmux)
    if args.shell:
        devcontainer_exec_command(project_path, "zsh")
        return

    if args.run:
        devcontainer_exec_command(project_path, args.run)
        return

    # Attach to tmux
    devcontainer_exec_tmux(project_path)


def run_init_mode(args: argparse.Namespace) -> None:
    """Run --init mode: initialize git + devcontainer in current directory."""
    validate_init_mode()

    project_path = Path.cwd()
    project_name = project_path.name

    # Load config
    config = load_config()

    # Initialize git repo
    cmd = ["git", "init"]
    verbose_cmd(cmd)
    result = subprocess.run(cmd, cwd=project_path)
    if result.returncode != 0:
        sys.exit("Error: Failed to initialize git repository")

    # Scaffold .devcontainer
    scaffold_devcontainer(project_name, project_path, config=config)

    # Initial commit with .devcontainer
    cmd = ["git", "add", ".devcontainer"]
    verbose_cmd(cmd)
    subprocess.run(cmd, cwd=project_path)

    cmd = ["git", "commit", "-m", "Initial commit with devcontainer setup"]
    verbose_cmd(cmd)
    subprocess.run(cmd, cwd=project_path)

    print(f"Initialized: {project_path}")

    # Add user-specified mounts to devcontainer.json
    if args.mount:
        parsed_mounts = [parse_mount(m, project_name) for m in args.mount]
        devcontainer_json = project_path / ".devcontainer" / "devcontainer.json"
        add_user_mounts(devcontainer_json, parsed_mounts)

    # Copy user-specified files
    if args.copy:
        parsed_copies = [parse_copy(c, project_name) for c in args.copy]
        copy_user_files(parsed_copies, project_path)

    # Set up secrets in environment
    secrets = get_secrets(config)
    os.environ.update(secrets)

    # Copy AI credentials for container isolation
    setup_credential_cache(project_path)

    # Set up Emacs config (copy config files, symlink packages)
    setup_emacs_config(project_path)

    # Start devcontainer (always remove existing for fresh project)
    if not devcontainer_up(project_path, remove_existing=True):
        sys.exit("Error: Failed to start devcontainer")

    if args.prompt:
        devcontainer_exec_prompt(project_path, args.agent, args.prompt)
        print(f"Started {args.agent} in: {project_name}")
        return

    if args.detach:
        print(f"Container started: {project_name}")
        return

    # Direct exec modes (no tmux)
    if args.shell:
        devcontainer_exec_command(project_path, "zsh")
        return

    if args.run:
        devcontainer_exec_command(project_path, args.run)
        return

    # Attach to tmux
    devcontainer_exec_tmux(project_path)


def run_spawn_mode(args: argparse.Namespace) -> None:
    """Run --spawn mode: create N worktrees with containers and agents."""
    git_root = validate_tree_mode()

    n = args.spawn
    if n < 1:
        sys.exit("Error: --spawn requires a positive integer")

    # Load config
    config = load_config()
    base_port = config.get("base_port", 4000)

    # Generate worktree names (number prefix for sorting + uniqueness)
    worktree_names = []
    used_names = set()
    for i in range(n):
        idx = i + 1
        if args.prefix:
            name = f"{idx}-{args.prefix}"
        else:
            # Generate unique random name with number prefix
            for _ in range(100):  # Max attempts
                random_part = generate_random_name()
                if random_part not in used_names:
                    break
            else:
                random_part = f"spawn-{idx}"
            used_names.add(random_part)
            name = f"{idx}-{random_part}"
        worktree_names.append(name)

    print(f"Spawning {n} worktrees: {', '.join(worktree_names)}")

    # Create worktrees and scaffold devcontainers
    worktree_paths = []
    for i, name in enumerate(worktree_names):
        worktree_path = get_worktree_path(str(git_root), name)
        port = base_port + i

        # Create or get existing worktree
        worktree_path = get_or_create_worktree(
            git_root,
            name,
            worktree_path,
            config=config,
            from_branch=args.from_branch,
        )

        # Update devcontainer.json with correct port
        devcontainer_json = worktree_path / ".devcontainer" / "devcontainer.json"
        if devcontainer_json.exists():
            content = json.loads(devcontainer_json.read_text())
            if "containerEnv" not in content:
                content["containerEnv"] = {}
            content["containerEnv"]["PORT"] = str(port)
            devcontainer_json.write_text(json.dumps(content, indent=4))

        # Add user-specified mounts
        if args.mount:
            parsed_mounts = [parse_mount(m, name) for m in args.mount]
            add_user_mounts(devcontainer_json, parsed_mounts)

        # Copy user-specified files
        if args.copy:
            parsed_copies = [parse_copy(c, name) for c in args.copy]
            copy_user_files(parsed_copies, worktree_path)

        # Set up credentials and emacs config
        setup_credential_cache(worktree_path)
        setup_emacs_config(worktree_path)

        # Ensure histfile exists (otherwise mount creates a directory)
        histfile = worktree_path / ".devcontainer" / ".histfile"
        histfile.touch(exist_ok=True)

        worktree_paths.append(worktree_path)

    # Set up secrets in environment
    secrets = get_secrets(config)
    os.environ.update(secrets)

    # Start containers in parallel
    print(f"Starting {n} containers...")
    processes = []
    for i, path in enumerate(worktree_paths):
        cmd = ["devcontainer", "up", "--workspace-folder", str(path)]
        if args.new:
            cmd.append("--remove-existing-container")
        verbose_cmd(cmd)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        processes.append((path, proc))
        print(f"  [{i+1}/{n}] Launched: {path.name}")

    # Wait for all containers to start
    print(f"Waiting for {n} containers to be ready...")
    failed = []
    for path, proc in processes:
        stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            failed.append(path.name)
            print(f"  Failed: {path.name}", file=sys.stderr)
            if stderr:
                # Show last few lines of error
                err_lines = stderr.decode().strip().split('\n')
                for line in err_lines[-5:]:
                    print(f"    {line}", file=sys.stderr)
        else:
            print(f"  Ready: {path.name}")

    if failed:
        print(f"Warning: {len(failed)} container(s) failed to start: {', '.join(failed)}")

    # If no prompt, just report status
    if not args.prompt:
        print(f"\n{len(worktree_paths) - len(failed)} containers running.")
        print("Use --prompt to start agents, or attach manually.")
        return

    # Launch agents in tmux multi-pane
    spawn_tmux_multipane(
        worktree_paths=[p for p in worktree_paths if p.name not in failed],
        worktree_names=[n for n in worktree_names if n not in failed],
        prompt=args.prompt,
        config=config,
        agent_override=args.agent if args.agent != "claude" else None,
    )


def spawn_tmux_multipane(
    worktree_paths: list[Path],
    worktree_names: list[str],
    prompt: str,
    config: dict,
    agent_override: str | None = None,
) -> None:
    """Create tmux session with one pane per agent.

    Args:
        worktree_paths: List of worktree paths
        worktree_names: List of worktree names
        prompt: The prompt to give each agent
        config: Configuration dict
        agent_override: If set, use this agent for all; otherwise round-robin
    """
    session_name = "spawn"
    n = len(worktree_paths)

    if n == 0:
        print("No containers to attach to.")
        return

    # Kill existing session if present
    subprocess.run(
        ["tmux", "kill-session", "-t", session_name],
        capture_output=True,
    )

    # Create new session with first pane
    first_path = worktree_paths[0]
    first_agent_cmd = get_agent_command(config, agent_override, index=0)
    first_agent_name = get_agent_name(config, agent_override, index=0)

    quoted_prompt = shlex.quote(prompt)

    # Build exec command using sh -c to properly handle agent flags
    def build_exec_cmd(path: Path, agent_cmd: str) -> str:
        inner_cmd = f"{agent_cmd} {quoted_prompt}"
        return f"devcontainer exec --workspace-folder {path} sh -c {shlex.quote(inner_cmd)}"

    # Create new session with first window
    first_exec_cmd = build_exec_cmd(first_path, first_agent_cmd)
    subprocess.run([
        "tmux", "new-session", "-d", "-s", session_name, "-n", worktree_names[0],
    ])
    subprocess.run([
        "tmux", "send-keys", "-t", f"{session_name}:{worktree_names[0]}", first_exec_cmd, "Enter"
    ])

    # Create additional windows (not panes - full screen each)
    for i in range(1, n):
        path = worktree_paths[i]
        name = worktree_names[i]
        agent_cmd = get_agent_command(config, agent_override, index=i)

        exec_cmd = build_exec_cmd(path, agent_cmd)

        # Create new window (full screen) and send command
        subprocess.run([
            "tmux", "new-window", "-t", session_name, "-n", name
        ])
        subprocess.run([
            "tmux", "send-keys", "-t", f"{session_name}:{name}", exec_cmd, "Enter"
        ])

    print(f"\nStarted {n} agents in tmux session '{session_name}'")
    print(f"Agents: {', '.join(get_agent_name(config, agent_override, i) for i in range(n))}")
    print(f"Attaching to tmux session...")

    # Attach to session
    subprocess.run(["tmux", "attach", "-t", session_name])


def run_sync_mode(args: argparse.Namespace) -> None:
    """Run --sync mode: regenerate .devcontainer from template."""
    git_root = find_git_root()

    if git_root is None:
        sys.exit("Error: Not in a git repository.")

    os.chdir(git_root)
    project_name = git_root.name

    # Load config
    config = load_config()

    # Sync .devcontainer
    sync_devcontainer(project_name, config=config)


def main(argv: list[str] | None = None) -> None:
    """Main entry point."""
    global VERBOSE

    if argv is None:
        argv = sys.argv[1:]

    args = parse_args(argv)

    # Set verbose mode
    if args.verbose:
        VERBOSE = True

    # These modes don't need tmux guard (no container attachment)
    if args.sync:
        run_sync_mode(args)
        # Continue to start container if --new was also specified
        if not args.new:
            return

    if args.list:
        run_list_mode(args)
        return

    if args.stop:
        run_stop_mode(args)
        return

    if args.prune:
        run_prune_mode(args)
        return

    if args.destroy is not None:
        run_destroy_mode(args)
        return

    # Check guards (skip tmux guard if detaching, using prompt, shell, or run)
    if not args.detach and not args.prompt and not args.shell and not args.run:
        check_tmux_guard()

    # Dispatch to appropriate mode
    if args.attach:
        run_attach_mode(args)
    elif args.spawn:
        run_spawn_mode(args)
    elif args.init:
        run_init_mode(args)
    elif args.create:
        run_create_mode(args)
    elif args.tree is not None:
        run_tree_mode(args)
    else:
        run_default_mode(args)


if __name__ == "__main__":
    main()
