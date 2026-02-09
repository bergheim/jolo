"""Constants for the jolo devcontainer launcher."""

import importlib.util

HAVE_ARGCOMPLETE = importlib.util.find_spec("argcomplete") is not None

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
        "claude": "claude",
        "gemini": "gemini",
        "codex": "codex",
    },
    "base_port": 4000,
}

# Port range for dev servers
PORT_MIN = 4000
PORT_MAX = 5000

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

# Base mounts that are always included
BASE_MOUNTS = [
    # AI agent credentials: copy-based isolation (copied to .devcontainer/.<name>-cache/)
    "source=${localWorkspaceFolder}/.devcontainer/.claude-cache,target=/home/${localEnv:USER}/.claude,type=bind",
    "source=${localWorkspaceFolder}/.devcontainer/.claude.json,target=/home/${localEnv:USER}/.claude.json,type=bind",
    "source=${localWorkspaceFolder}/.devcontainer/.gemini-cache,target=/home/${localEnv:USER}/.gemini,type=bind",
    "source=${localWorkspaceFolder}/.devcontainer/.codex-cache,target=/home/${localEnv:USER}/.codex,type=bind",
    "source=${localEnv:HOME}/.zshrc,target=/home/${localEnv:USER}/.zshrc,type=bind,readonly",
    "source=${localWorkspaceFolder}/.devcontainer/.histfile,target=/home/${localEnv:USER}/.histfile,type=bind",
    "source=${localEnv:HOME}/.tmux.conf,target=/home/${localEnv:USER}/.tmux.conf,type=bind,readonly",
    "source=${localEnv:HOME}/.gitconfig,target=/home/${localEnv:USER}/.gitconfig,type=bind,readonly",
    "source=${localEnv:HOME}/.config/tmux,target=/home/${localEnv:USER}/.config/tmux,type=bind,readonly",
    # Emacs: config copied for isolation, packages in container-specific cache
    # Uses ~/.cache/emacs-container/ (not ~/.cache/emacs/) so the container builds
    # its own elpaca/tree-sitter for its Emacs version + musl, separate from host.
    # First boot is slow (elpaca builds everything), subsequent boots reuse the cache.
    "source=${localWorkspaceFolder}/.devcontainer/.emacs-config,target=/home/${localEnv:USER}/.config/emacs,type=bind",
    "source=${localWorkspaceFolder}/.devcontainer/.emacs-cache,target=/home/${localEnv:USER}/.cache/emacs,type=bind",
    "source=${localEnv:HOME}/.cache/emacs-container/elpaca,target=/home/${localEnv:USER}/.cache/emacs/elpaca,type=bind",
    "source=${localEnv:HOME}/.cache/emacs-container/tree-sitter,target=/home/${localEnv:USER}/.cache/emacs/tree-sitter,type=bind",
    "source=${localEnv:HOME}/.gnupg/pubring.kbx,target=/home/${localEnv:USER}/.gnupg/pubring.kbx,type=bind,readonly",
    "source=${localEnv:HOME}/.gnupg/trustdb.gpg,target=/home/${localEnv:USER}/.gnupg/trustdb.gpg,type=bind,readonly",
    "source=${localEnv:XDG_RUNTIME_DIR}/gnupg/S.gpg-agent,target=/home/${localEnv:USER}/.gnupg/S.gpg-agent,type=bind",
    "source=${localEnv:HOME}/.config/gh,target=/home/${localEnv:USER}/.config/gh,type=bind,readonly",
]

# Wayland mount - only included when WAYLAND_DISPLAY is set
WAYLAND_MOUNT = "source=${localEnv:XDG_RUNTIME_DIR}/${localEnv:WAYLAND_DISPLAY},target=/tmp/container-runtime/${localEnv:WAYLAND_DISPLAY},type=bind"
