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
    # pi leads: it is a meta harness that can delegate to the others.
    "agents": ["pi", "claude", "codex", "grok", "gemini"],
    "agent_commands": {
        "claude": "env -u ANTHROPIC_API_KEY claude --dangerously-skip-permissions",
        "gemini": "gemini --yolo --no-sandbox",
        "codex": "codex --dangerously-bypass-approvals-and-sandbox",
        "pi": "env -u ANTHROPIC_API_KEY pi --append-system-prompt @$HOME/.pi/agent/delegation.md",
        # --no-auto-update per launch, not via config.toml: that file is the
        # host's and shared, and the host may want auto-update. The image owns
        # the binary version here.
        "grok": "grok --always-approve --no-auto-update",
    },
    # LiteLLM control-plane gateway base URL. Default empty; load_config()
    # populates it from the host env LITELLM_HOST (e.g. http://<tailnet-host>:8088),
    # so the rest of the code just reads config. Real provider keys live only in
    # the gateway; containers get a per-project virtual key. Master key mints.
    "litellm_base_url": "",
    "pass_path_litellm_master": "api/llm/litellm-master",
    "pass_path_crawl4ai": "api/crawl/crawl4ai-token",
    "litellm_key_max_budget": 50.0,
    "litellm_key_budget_duration": "30d",
    "litellm_key_models": [],
    "base_port": 4000,
    "notify_threshold": 60,
    "research_home": "~/jolo/research",
}

# Port range for dev servers
PORT_MIN = 4000
PORT_MAX = 5000
WORKTREE_PORTS = 3  # extra ports per container for agent-shell worktrees

# `jolo expose`: the host-side Caddy vhost reverse-proxies pub.glvortex.net to
# this loopback slot; `expose` runs socat forwarding the slot to a project port.
EXPOSE_SLOT_PORT = 9999
EXPOSE_PUBLIC_URL = "https://pub.glvortex.net"

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
    # Claude: one host dir bind, same rule as pi and grok below. Binding
    # individual files instead made rename(2) fail with EBUSY, so any tool
    # using write-tmp-then-rename broke, and copying the host settings.json
    # leaked host-absolute hook paths into the container.
    #
    # Everything Claude keys by path on disk (projects/ holds memory and
    # transcripts under a cwd slug) is already per-project when shared, so it
    # is shared. Only state the container's namespace makes non-unique is
    # shadowed below.
    "source=${localEnv:HOME}/.claude,target=/home/${localEnv:USER}/.claude,type=bind",
    # sessions/ is the live peer registry for cross-session messaging, keyed
    # by PID and reaped by local PID liveness. Containers have their own PID
    # namespace, so a shared sessions/ has each container garbage-collecting
    # every other container's live records.
    "source=${localWorkspaceFolder}/.devcontainer/.claude-sessions,target=/home/${localEnv:USER}/.claude/sessions,type=bind",
    # history.jsonl is one flat file; its "project" field is internal, so
    # sharing it mixes every project into up-arrow prompt recall.
    "source=${localWorkspaceFolder}/.devcontainer/.claude-history.jsonl,target=/home/${localEnv:USER}/.claude/history.jsonl,type=bind",
    # Lives outside ~/.claude, so it needs its own line. Shared: global state
    # (onboarding, model choice) follows into every container, and its
    # projects{} map is keyed by absolute path.
    "source=${localEnv:HOME}/.claude.json,target=/home/${localEnv:USER}/.claude.json,type=bind",
    # caveman: harness-bound like .pi and .grok. The Go binaries live in
    # ~/.caveman/bin and every agent's hooks reference them by absolute path,
    # so the host path has to resolve identically inside the container or the
    # hooks die with "not found". State (ccr.db, caveman.db) rides along.
    "source=${localEnv:HOME}/.caveman,target=/home/${localEnv:USER}/.caveman,type=bind",
    # Account token lives here (config.json), not in ~/.caveman. Without this
    # bind, every new container re-asks "do you have a Caveman account?".
    "source=${localEnv:HOME}/.caveman-cloud,target=/home/${localEnv:USER}/.caveman-cloud,type=bind",
    "source=${localWorkspaceFolder}/.devcontainer/.gemini-cache,target=/home/${localEnv:USER}/.gemini,type=bind",
    "source=${localWorkspaceFolder}/.devcontainer/.codex-cache,target=/home/${localEnv:USER}/.codex,type=bind",
    # pi: one host config shared by every container, so packages/themes/agents
    # and the OAuth login added in one project are live in all of them. Only
    # sessions are per-project — nested mount below shadows the shared dir.
    # The gateway's LiteLLM key is NOT in here: models.json stores the literal
    # "$LITELLM_VIRTUAL_KEY" and each container resolves its own, keeping
    # per-project spend attribution.
    "source=${localEnv:HOME}/.pi,target=/home/${localEnv:USER}/.pi,type=bind",
    "source=${localWorkspaceFolder}/.devcontainer/.pi-sessions,target=/home/${localEnv:USER}/.pi/agent/sessions,type=bind",
    # grok (Grok Build): same rule as pi — one host config shared everywhere, so
    # the xAI login and config.toml are live in every container. Sessions are
    # per-project like pi's. Worktrees too, and for a second reason: `grok du`
    # measures session worktrees in hundreds of GB, and they are keyed by cwd,
    # so sharing them across projects would be a disk disaster.
    "source=${localEnv:HOME}/.grok,target=/home/${localEnv:USER}/.grok,type=bind",
    "source=${localWorkspaceFolder}/.devcontainer/.grok-sessions,target=/home/${localEnv:USER}/.grok/sessions,type=bind",
    "source=${localWorkspaceFolder}/.devcontainer/.grok-worktrees,target=/home/${localEnv:USER}/.grok/worktrees,type=bind",
    "source=${localEnv:HOME}/.zshrc,target=/home/${localEnv:USER}/.zshrc,type=bind,readonly",
    "source=${localEnv:HOME}/.zshenv,target=/home/${localEnv:USER}/.zshenv,type=bind,readonly",
    "source=${localEnv:HOME}/.profile.container,target=/home/${localEnv:USER}/.profile,type=bind,readonly",
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
    # rpiv-advisor stores config under XDG, not ~/.pi, so it does not ride the
    # shared pi mount and vanishes on recreate. Writable: /advisor edits persist.
    "source=${localEnv:HOME}/.config/rpiv-advisor,target=/home/${localEnv:USER}/.config/rpiv-advisor,type=bind",
    "source=${localEnv:HOME}/stash,target=/workspaces/stash,type=bind",
    # The invoking user's own host-key trust store, so clones from personal
    # forges skip the interactive host-key prompt headless agents cannot
    # answer. Read-only: new hosts get accepted on the host, not in here.
    "source=${localEnv:HOME}/.ssh/known_hosts,target=/home/${localEnv:USER}/.ssh/known_hosts,type=bind,readonly",
]

# Host paths jolo owns, relative to $HOME, that BASE_MOUNTS binds as
# directories. They are created at render time rather than only in
# setup_credential_cache, because the devcontainer.json is written before
# setup runs — without this, a fresh host would render with these mounts
# dropped and quietly lose shared agent config instead of gaining it.
# Files are deliberately absent: a directory auto-created at ~/.gitconfig
# would be a silently broken config, so missing files are dropped instead.
HOST_OWNED_MOUNT_DIRS = (
    ".claude",
    ".caveman",
    ".caveman-cloud",
    ".agents/skills",
    ".pi",
    ".grok",
    ".cache/jolo/elpaca",
    ".cache/jolo/tree-sitter",
    ".config/rpiv-advisor",
    "stash",
)

# Host-side only. Containers never see this: it holds the routing and DNS
# control plane for every project, so a single container could rewrite all
# of them.
TAILNET_CONTROL_DIR = "/srv/tailnet"

# Project sites live under the Headscale MagicDNS base, so each one needs an
# explicit A record; unknown names do not fall through to public DNS. The
# value is burial's tailnet address, which holds the wildcard certificate.
TAILNET_SITE_DOMAIN = "ts.glvortex.net"
TAILNET_ROUTER_IP = "100.64.0.4"

# Public counterpart to the tailnet sites. One wildcard A record at the
# registrar points *.pub.glvortex.net at berghome; Caddy issues a cert per
# explicitly-declared name over HTTP-01, so no wildcard cert is needed.
PUBLIC_SITE_DOMAIN = "pub.glvortex.net"
PUBLIC_AUTH_USER = "tsb"

# Wayland mount - only included when WAYLAND_DISPLAY is set
WAYLAND_MOUNT = "source=${localEnv:XDG_RUNTIME_DIR}/${localEnv:WAYLAND_DISPLAY},target=/tmp/container-runtime/${localEnv:WAYLAND_DISPLAY},type=bind"

# SSH agent mount - only included when SSH_AUTH_SOCK is set, so git auth
# uses the invoking user's own host agent and no key material enters the
# image. ponytail: binds the socket file, so a host agent restart leaves it
# stale until container recreate — same ceiling as the Wayland socket above.
SSH_AGENT_MOUNT = "source=${localEnv:SSH_AUTH_SOCK},target=/tmp/container-runtime/ssh-agent,type=bind"
