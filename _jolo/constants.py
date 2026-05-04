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
    "base_image": "localhost/jolo:latest",
    "pass_path_anthropic": "api/llm/anthropic",
    "pass_path_openai": "api/llm/openai",
    "pass_path_gemini": ["api/llm/gemini", "api/llm/google"],
    "agents": ["claude", "gemini", "codex", "pi"],
    "agent_commands": {
        "claude": "env -u ANTHROPIC_API_KEY claude --dangerously-skip-permissions",
        "gemini": "gemini --yolo --no-sandbox",
        "codex": "codex --dangerously-bypass-approvals-and-sandbox",
        "pi": "env -u ANTHROPIC_API_KEY pi",
    },
    "base_port": 4000,
    "notify_threshold": 60,
    "research_home": "~/jolo/research",
}

# Port range for dev servers
PORT_MIN = 4000
PORT_MAX = 5000
WORKTREE_PORTS = 3  # extra ports per container for agent-shell worktrees

# Global verbose flag
VERBOSE = False

# Valid flavors for --flavor flag (also used directly in interactive picker)
VALID_FLAVORS = [
    "typescript-web",
    "typescript",
    "elixir-web",
    "go-web",
    "go",
    "python-web",
    "python",
    "rust-web",
    "rust",
    "shell",
    "prose",
    "other",
]
# Note: "meta" is intentionally absent from VALID_FLAVORS — it is detected
# from the project shape (jolo meta-repo only) and never user-selectable.
# It still appears in FLAVOR_LANGUAGE below so runtime lookups resolve.

# Map flavor to base language for pre-commit hooks, coverage, etc.
FLAVOR_LANGUAGE = {
    "typescript-web": "typescript",
    "typescript": "typescript",
    "elixir-web": "elixir",
    "go-web": "go",
    "go": "go",
    "python-web": "python",
    "python": "python",
    "rust-web": "rust",
    "rust": "rust",
    "shell": "shell",
    "prose": "prose",
    "meta": "meta",
    "other": "other",
}

# Pre-commit hook configurations by language
PRECOMMIT_HOOKS = {
    "python": {
        "repo": "local",
        "hooks": [
            {
                "id": "ruff",
                "name": "ruff",
                "entry": "ruff check --fix",
                "language": "system",
                "types": ["python"],
            },
            {
                "id": "ruff-format",
                "name": "ruff-format",
                "entry": "ruff format",
                "language": "system",
                "types": ["python"],
            },
        ],
    },
    "go": {
        "repo": "local",
        "hooks": [
            {
                "id": "golangci-lint",
                "name": "golangci-lint",
                "entry": "golangci-lint run --fix",
                "language": "system",
                "types": ["go"],
                "pass_filenames": False,
            },
        ],
    },
    "typescript": {
        "repo": "local",
        "hooks": [
            {
                "id": "biome-check",
                "name": "biome check",
                "entry": "biome check --write --no-errors-on-unmatched --files-ignore-unknown=true",
                "language": "system",
                "types": ["text"],
                "exclude": "^templates/.*\\.html$",
                "pass_filenames": True,
            },
        ],
    },
    "rust": {
        "repo": "local",
        "hooks": [
            {
                "id": "rustfmt",
                "name": "rustfmt",
                "entry": "rustfmt",
                "language": "system",
                "types": ["rust"],
            },
            {
                "id": "cargo-check",
                "name": "cargo check",
                "entry": "cargo check",
                "language": "system",
                "pass_filenames": False,
            },
        ],
    },
    "shell": {
        "repo": "local",
        "hooks": [
            {
                "id": "shellcheck",
                "name": "shellcheck",
                "entry": "shellcheck",
                "language": "system",
                "types": ["shell"],
            },
        ],
    },
    "prose": [
        {
            "repo": "local",
            "hooks": [
                {
                    "id": "markdownlint",
                    "name": "markdownlint",
                    "entry": "markdownlint",
                    "language": "system",
                    "types": ["markdown"],
                },
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
    # Claude: selective mounts — credentials RW to host (token refresh persists),
    # settings/statsig from cache (container-specific hook injection)
    "source=${localEnv:HOME}/.claude/.credentials.json,target=/home/${localEnv:USER}/.claude/.credentials.json,type=bind",
    "source=${localWorkspaceFolder}/.devcontainer/.claude-cache/settings.json,target=/home/${localEnv:USER}/.claude/settings.json,type=bind",
    "source=${localEnv:HOME}/.claude/statsig,target=/home/${localEnv:USER}/.claude/statsig,type=bind,readonly",
    "source=${localEnv:HOME}/.claude/plugins,target=/home/${localEnv:USER}/.claude/plugins,type=bind",
    "source=${localWorkspaceFolder}/.devcontainer/.claude.json,target=/home/${localEnv:USER}/.claude.json,type=bind",
    "source=${localWorkspaceFolder}/.jolo/skills,target=/home/${localEnv:USER}/.agents/skills,type=bind",
    "source=${localWorkspaceFolder}/.devcontainer/.gemini-cache,target=/home/${localEnv:USER}/.gemini,type=bind",
    "source=${localWorkspaceFolder}/.devcontainer/.codex-cache,target=/home/${localEnv:USER}/.codex,type=bind",
    "source=${localWorkspaceFolder}/.devcontainer/.pi-cache,target=/home/${localEnv:USER}/.pi,type=bind",
    "source=${localEnv:HOME}/.zshrc,target=/home/${localEnv:USER}/.zshrc,type=bind,readonly",
    "source=${localWorkspaceFolder}/.devcontainer/.zsh-state,target=/home/${localEnv:USER}/.zsh-state,type=bind",
    "source=${localEnv:HOME}/.tmux.conf,target=/home/${localEnv:USER}/.tmux.conf,type=bind,readonly",
    "source=${localEnv:HOME}/.gitconfig,target=/home/${localEnv:USER}/.gitconfig,type=bind,readonly",
    "source=${localEnv:HOME}/.config/tmux,target=/home/${localEnv:USER}/.config/tmux,type=bind,readonly",
    # Emacs: config copied for isolation, packages in container-specific cache
    # Uses ~/.cache/jolo/ (not ~/.cache/emacs/) so the container builds
    # its own elpaca/tree-sitter for its Emacs version + musl, separate from host.
    # First boot is slow (elpaca builds everything), subsequent boots reuse the cache.
    "source=${localWorkspaceFolder}/.devcontainer/.emacs-config,target=/home/${localEnv:USER}/.config/emacs,type=bind",
    "source=${localWorkspaceFolder}/.devcontainer/.emacs-cache,target=/home/${localEnv:USER}/.cache/emacs,type=bind",
    "source=${localEnv:HOME}/.cache/jolo/elpaca,target=/home/${localEnv:USER}/.cache/emacs/elpaca,type=bind",
    "source=${localEnv:HOME}/.cache/jolo/tree-sitter,target=/home/${localEnv:USER}/.cache/emacs/tree-sitter,type=bind",
    "source=${localEnv:HOME}/.gnupg/pubring.kbx,target=/home/${localEnv:USER}/.gnupg/pubring.kbx,type=bind,readonly",
    "source=${localEnv:HOME}/.gnupg/trustdb.gpg,target=/home/${localEnv:USER}/.gnupg/trustdb.gpg,type=bind,readonly",
    "source=${localEnv:XDG_RUNTIME_DIR}/gnupg/S.gpg-agent,target=/home/${localEnv:USER}/.gnupg/S.gpg-agent,type=bind",
    "source=${localEnv:HOME}/.config/gh,target=/home/${localEnv:USER}/.config/gh,type=bind,readonly",
    "source=${localEnv:HOME}/stash,target=/workspaces/stash,type=bind",
]

# Wayland mount - only included when WAYLAND_DISPLAY is set
WAYLAND_MOUNT = "source=${localEnv:XDG_RUNTIME_DIR}/${localEnv:WAYLAND_DISPLAY},target=/tmp/container-runtime/${localEnv:WAYLAND_DISPLAY},type=bind"
