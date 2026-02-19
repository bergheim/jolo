"""Template and config generation functions for jolo."""

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
    if "name" in hook:
        lines.append(f"{indent}  name: {hook['name']}")
    if "entry" in hook:
        lines.append(f"{indent}  entry: {hook['entry']}")
    if "language" in hook:
        lines.append(f"{indent}  language: {hook['language']}")
    if "pass_filenames" in hook:
        value = "true" if hook["pass_filenames"] else "false"
        lines.append(f"{indent}  pass_filenames: {value}")
    if "stages" in hook:
        stages_str = ", ".join(hook["stages"])
        lines.append(f"{indent}  stages: [{stages_str}]")
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
    lines = [f"  - repo: {repo_config['repo']}"]
    if "rev" in repo_config:
        lines.append(f"    rev: {repo_config['rev']}")
    lines.append("    hooks:")
    for hook in repo_config["hooks"]:
        lines.append(_format_hook_yaml(hook))
    return "\n".join(lines)


def generate_precommit_config(flavors: list[str]) -> str:
    """Generate .pre-commit-config.yaml content based on selected flavors.

    Args:
        flavors: List of flavor codes (e.g., ['python-web', 'typescript-bare'])

    Returns:
        Valid YAML string for .pre-commit-config.yaml
    """
    # Resolve flavors to base languages for hook lookup
    languages = list(
        dict.fromkeys(constants.FLAVOR_LANGUAGE.get(f, f) for f in flavors)
    )

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
        {
            "repo": "local",
            "hooks": [
                {
                    "id": "test",
                    "name": "tests (commit)",
                    "entry": "scripts/test-gate commit",
                    "language": "script",
                    "pass_filenames": False,
                    "stages": ["pre-commit"],
                },
                {
                    "id": "test-push",
                    "name": "tests (push)",
                    "entry": "scripts/test-gate push",
                    "language": "script",
                    "pass_filenames": False,
                    "stages": ["pre-push"],
                },
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
    return [
        "pre-commit",
        "install",
        "--hook-type",
        "pre-commit",
        "--hook-type",
        "pre-push",
    ]


def get_type_checker_config(flavor: str) -> dict | None:
    """Get type checker configuration for a flavor.

    Returns configuration for setting up type checking based on flavor.
    For languages with built-in type checking (Go, Rust), returns None.

    Args:
        flavor: The project flavor (e.g., 'python-web', 'typescript-bare')

    Returns:
        dict with 'config_file' and 'config_content' keys, or None if no
        external type checker config is needed.
    """
    lang = constants.FLAVOR_LANGUAGE.get(flavor, flavor)

    if lang == "python":
        return {
            "config_file": "pyproject.toml",
            "config_content": "[tool.ty]\n# See: https://github.com/astral-sh/ty\n",
        }

    elif lang == "typescript":
        return {
            "config_file": "tsconfig.json",
            "config_content": _read_template(
                _flavor_template_path(flavor, "tsconfig.json")
            ),
        }

    return None


def get_coverage_config(flavor: str) -> dict:
    """Get code coverage configuration for a flavor.

    Returns configuration for setting up code coverage based on flavor.
    For languages without standard coverage tooling, returns None values.

    Args:
        flavor: The project flavor (e.g., 'python-web', 'go-bare')

    Returns:
        dict with keys:
            - 'config_addition': Config to add to project config file, or None
            - 'run_command': Command to run coverage, or None
    """
    lang = constants.FLAVOR_LANGUAGE.get(flavor, flavor)

    if lang == "python":
        return {
            "config_addition": '[tool.pytest.ini_options]\naddopts = "--cov=src --cov-report=term-missing"\n',
            "run_command": "pytest --cov=src --cov-report=term-missing",
        }

    elif lang == "typescript":
        return {
            "config_addition": None,
            "run_command": "bun test --coverage",
        }

    elif lang == "go":
        return {
            "config_addition": None,
            "run_command": "go test -cover ./...",
        }

    elif lang == "rust":
        return {
            "config_addition": None,
            "run_command": "cargo llvm-cov",
        }

    # Shell, prose, other, and unknown languages have no standard coverage
    return {
        "config_addition": None,
        "run_command": None,
    }


def _flavor_template_path(flavor: str, filename: str) -> str:
    """Resolve template path for a flavor.

    Flavors like 'go-web' map to 'lang/go/web/<filename>',
    'go-bare' maps to 'lang/go/<filename>' (bare is the base variant).
    Non-split flavors like 'rust' map to 'lang/rust/<filename>'.
    Falls back to 'lang/other/<filename>' when the resolved path doesn't exist.
    """
    lang = constants.FLAVOR_LANGUAGE.get(flavor, flavor)
    is_web = flavor.endswith("-web")
    subdir = "web" if is_web else ""
    if subdir:
        path = f"lang/{lang}/{subdir}/{filename}"
    else:
        path = f"lang/{lang}/{filename}"
    if not (_TEMPLATES_DIR / path).exists():
        path = f"lang/other/{filename}"
    return path


def get_justfile_content(flavor: str, project_name: str) -> str:
    """Generate justfile content for a project based on flavor.

    Args:
        flavor: The project flavor (e.g., 'python-web', 'go-bare')
        project_name: The project name

    Returns:
        justfile content string
    """
    module_name = project_name.replace("-", "_")
    template_path = _flavor_template_path(flavor, "justfile")
    template = _read_template(template_path)
    return _render(
        template, PROJECT_NAME=project_name, MODULE_NAME=module_name
    )


def get_motd_content(flavor: str, project_name: str) -> str:
    """Generate MOTD content for a project based on flavor.

    Args:
        flavor: The project flavor
        project_name: The project name

    Returns:
        MOTD content string
    """
    template = _read_template("motd")
    return _render(template, PROJECT_NAME=project_name)


def get_test_framework_config(flavor: str) -> dict:
    """Get test framework configuration for a flavor.

    Returns configuration for setting up test frameworks based on flavor.
    For languages with built-in testing (Go, Rust), config_file is None.

    Args:
        flavor: The project flavor (e.g., 'python-web', 'typescript-bare')

    Returns:
        dict with keys:
            - 'config_file': File name for test config, or None for built-in testing
            - 'config_content': Content to write/append to config file
            - 'example_test_file': Path to example test file
            - 'example_test_content': Content for example test file
    """
    lang = constants.FLAVOR_LANGUAGE.get(flavor, flavor)

    if lang == "python":
        pyproject_path = _flavor_template_path(flavor, "pyproject.toml")
        return {
            "config_file": "pyproject.toml",
            "config_content": _read_template(pyproject_path),
            "example_test_file": "tests/test_main.py",
            "example_test_content": _read_template(
                _flavor_template_path(flavor, "test_main.py")
            ),
            "main_file": "src/{{PROJECT_NAME_UNDERSCORE}}/main.py",
            "main_content": _read_template(
                _flavor_template_path(flavor, "main.py")
            ),
            "init_file": "src/{{PROJECT_NAME_UNDERSCORE}}/__init__.py",
            "tests_init_file": "tests/__init__.py",
        }

    elif lang == "typescript":
        test_file = "example.test.ts"
        return {
            "config_file": None,
            "config_content": "# Bun has built-in testing. Run tests with: bun test",
            "example_test_file": "src/example.test.ts",
            "example_test_content": _read_template(
                _flavor_template_path(flavor, test_file)
            ),
        }

    elif lang == "go":
        return {
            "config_file": None,
            "config_content": "# Go uses built-in testing. Run tests with: go test ./...",
            "example_test_file": "example_test.go",
            "example_test_content": _read_template(
                _flavor_template_path(flavor, "example_test.go")
            ),
            "main_file": "main.go",
            "main_content": _read_template(
                _flavor_template_path(flavor, "main.go")
            ),
        }

    elif lang == "rust":
        if flavor == "rust-web":
            main_rs = _read_template("lang/rust/web/src/main.rs")
        else:
            main_rs = _read_template("lang/rust/main.rs")
        return {
            "config_file": None,
            "config_content": "# Rust uses built-in testing. Run tests with: cargo test",
            "example_test_file": "src/main.rs",
            "example_test_content": main_rs,
        }

    return {
        "config_file": None,
        "config_content": "",
        "example_test_file": None,
        "example_test_content": "",
    }


def get_scaffold_files(flavor: str) -> list[tuple[str, str]]:
    """Get additional scaffold source files for a flavor.

    Args:
        flavor: The project flavor (e.g., 'typescript-web', 'go-web')

    Returns:
        List of (relative_path, content) tuples.
    """
    if flavor == "typescript-web":
        return [
            (
                "src/index.tsx",
                _read_template("lang/typescript/web/src/index.tsx"),
            ),
            (
                "src/styles.css",
                _read_template("lang/typescript/web/src/styles.css"),
            ),
            (
                "src/pages/home.tsx",
                _read_template("lang/typescript/web/src/pages/home.tsx"),
            ),
            (
                "src/components/layout.tsx",
                _read_template(
                    "lang/typescript/web/src/components/layout.tsx"
                ),
            ),
            ("public/.gitkeep", ""),
        ]
    elif flavor == "go-web":
        return [
            (
                "components/page.templ",
                _read_template("lang/go/web/components/page.templ"),
            ),
            (
                "components/home.templ",
                _read_template("lang/go/web/components/home.templ"),
            ),
            (
                ".air.toml",
                _read_template("lang/go/web/.air.toml"),
            ),
            (
                "static/.gitkeep",
                "",
            ),
        ]
    elif flavor == "python-web":
        return [
            (
                "src/{{PROJECT_NAME_UNDERSCORE}}/app.py",
                _read_template("lang/python/web/app.py"),
            ),
            (
                "templates/base.html",
                _read_template("lang/python/web/templates/base.html"),
            ),
            (
                "templates/home.html",
                _read_template("lang/python/web/templates/home.html"),
            ),
            (
                "static/.gitkeep",
                "",
            ),
        ]
    elif flavor == "rust-web":
        return [
            (
                "bacon.toml",
                _read_template("lang/rust/web/bacon.toml"),
            ),
            (
                "src/styles.css",
                _read_template("lang/rust/web/src/styles.css"),
            ),
            (
                "templates/base.html",
                _read_template("lang/rust/web/templates/base.html"),
            ),
            (
                "templates/index.html",
                _read_template("lang/rust/web/templates/index.html"),
            ),
            (
                "static/.gitkeep",
                "",
            ),
        ]
    return []


def get_project_init_commands(
    flavor: str, project_name: str
) -> list[list[str]]:
    """Get initialization commands for a project based on flavor.

    Returns a list of command lists to execute inside the container.
    Each inner list is a command + arguments.

    Args:
        flavor: The project flavor (e.g., 'python-web', 'go-bare')
        project_name: The name of the project (used in go mod init, cargo new, etc.)

    Returns:
        List of command lists, e.g. [['uv', 'init'], ['mkdir', '-p', 'tests']]
    """
    commands: list[list[str]] = []
    lang = constants.FLAVOR_LANGUAGE.get(flavor, flavor)

    if lang == "python":
        commands.append(["mkdir", "-p", "tests"])
        if flavor == "python-web":
            commands.append(
                ["uv", "add", "fastapi", "uvicorn[standard]", "jinja2"]
            )
            commands.append(["uv", "add", "--dev", "httpx"])
    elif lang == "typescript":
        commands.append(["bun", "init", "-y"])
        if flavor == "typescript-bare":
            commands.append(["mkdir", "-p", "src"])
            commands.append(["mv", "index.ts", "src/index.ts"])
        else:
            commands.append(["rm", "-f", "index.ts"])
            commands.append(
                [
                    "bun",
                    "add",
                    "elysia",
                    "@elysiajs/html",
                    "@elysiajs/static",
                    "@kitajs/html",
                    "htmx.org",
                ]
            )
            commands.append(
                ["bun", "add", "-d", "tailwindcss", "@tailwindcss/cli"]
            )
            commands.append(["just", "setup"])
    elif lang == "go":
        commands.append(["go", "mod", "init", project_name])
        if flavor == "go-web":
            commands.append(["go", "get", "github.com/a-h/templ"])
            commands.append(["templ", "generate"])
    elif lang == "rust":
        commands.append(["cargo", "init", "--name", project_name])
        if flavor == "rust-web":
            commands.append(
                ["cargo", "add", "axum", "axum-htmx", "tower-livereload"]
            )
            commands.append(["cargo", "add", "tokio", "-F", "full"])
            commands.append(["cargo", "add", "minijinja", "-F", "builtins"])
            commands.append(["cargo", "add", "tower-http", "-F", "fs"])
            commands.append(["cargo", "add", "serde", "-F", "derive"])
            commands.append(["cargo", "add", "--dev", "tower"])
            commands.append(["just", "setup"])
    elif lang == "shell":
        commands.append(["mkdir", "-p", "src"])
    elif lang == "prose":
        commands.append(["mkdir", "-p", "docs"])
    else:
        commands.append(["mkdir", "-p", "src"])

    return commands
