FROM cgr.dev/chainguard/wolfi-base:latest

# Wolfi uses glibc (not musl) - playwright/browser automation will work!
# Package names may differ from Alpine - this is a best-effort port

RUN apk update && apk add --no-cache \
    bash \
    build-base \
    cmake \
    coreutils \
    curl \
    emacs \
    fd \
    fontconfig \
    fzf \
    git \
    glibc-locale-en \
    gnupg \
    go \
    jq \
    neovim \
    nodejs \
    npm \
    openssh-client \
    python3 \
    ripgrep \
    rust \
    sqlite \
    sudo \
    tmux \
    wget \
    yq \
    zsh

# Packages not in Wolfi - install via other means
# - github-cli: install from GitHub releases
# - gum: install from GitHub releases
# - shellcheck: install from GitHub releases
# - cargo: comes with rust (rustup)
RUN wget -qO- https://github.com/cli/cli/releases/download/v2.67.0/gh_2.67.0_linux_amd64.tar.gz | tar xz -C /tmp && \
    mv /tmp/gh_2.67.0_linux_amd64/bin/gh /usr/local/bin/ && \
    wget -qO- https://github.com/charmbracelet/gum/releases/download/v0.14.5/gum_0.14.5_Linux_x86_64.tar.gz | tar xz -C /tmp && \
    mv /tmp/gum_0.14.5_Linux_x86_64/gum /usr/local/bin/ && \
    wget -qO- https://github.com/koalaman/shellcheck/releases/download/v0.10.0/shellcheck-v0.10.0.linux.x86_64.tar.xz | tar xJ -C /tmp && \
    mv /tmp/shellcheck-v0.10.0/shellcheck /usr/local/bin/

# npm global packages (language servers, browser automation, etc.)
RUN npm install -g \
    @biomejs/biome \
    agent-browser \
    playwright \
    typescript-language-server \
    typescript \
    pnpm \
    vscode-langservers-extracted \
    bash-language-server \
    yaml-language-server \
    dockerfile-language-server-nodejs \
    pyright \
    @ansible/ansible-language-server

# User setup
ARG USERNAME=tsb
ARG USER_ID=1000
ARG GROUP_ID=1000
ARG USER_PASSWORD=dev123

RUN addgroup -g $GROUP_ID $USERNAME && \
    adduser -D -h /home/$USERNAME -s /bin/zsh -u $USER_ID -G $USERNAME $USERNAME && \
    echo "$USERNAME:$USER_PASSWORD" | chpasswd && \
    echo "$USERNAME ALL=(ALL) ALL" > /etc/sudoers.d/$USERNAME && \
    chmod 0440 /etc/sudoers.d/$USERNAME

# Smart emacsclient wrapper (must be before USER switch)
COPY e /usr/local/bin/e
RUN chmod +x /usr/local/bin/e

# hadolint (Dockerfile linter)
RUN wget -qO /usr/local/bin/hadolint https://github.com/hadolint/hadolint/releases/latest/download/hadolint-Linux-x86_64 && \
    chmod +x /usr/local/bin/hadolint

USER $USERNAME
ENV HOME=/home/$USERNAME
WORKDIR $HOME

# Local package managers for user-managed tools
ENV NPM_CONFIG_PREFIX=$HOME/.npm-global
ENV PNPM_HOME=$HOME/.local/share/pnpm
ENV PATH="$PNPM_HOME:$NPM_CONFIG_PREFIX/bin:/usr/local/go/bin:$HOME/go/bin:$HOME/.local/bin:$PATH"

RUN curl -fsSL https://bun.sh/install | bash && \
    echo 'export PATH="$HOME/.bun/bin:$PATH"' >> $HOME/.zshrc.container && \
    # Create directories for mounts
    mkdir -p $HOME/.config/emacs && \
    mkdir -p $HOME/.claude && \
    mkdir -p $HOME/.gemini && \
    mkdir -p $HOME/.local/bin && \
    # GPG setup with loopback pinentry for signing
    mkdir -p $HOME/.gnupg && \
    chmod 700 $HOME/.gnupg && \
    echo "allow-loopback-pinentry" > $HOME/.gnupg/gpg-agent.conf && \
    # Claude CLI (YOLO mode)
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> $HOME/.zshrc.container && \
    curl -fsSL https://claude.ai/install.sh | bash && \
    # AI tools (installed to $PNPM_HOME via pnpm)
    pnpm add -g @google/gemini-cli @openai/codex && \
    echo 'alias claude="claude --dangerously-skip-permissions"' >> $HOME/.zshrc.container && \
    echo 'alias vi=nvim' >> $HOME/.zshrc.container && \
    curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash && \
    # tmux clipboard (OSC 52)
    echo 'set -s set-clipboard on' > $HOME/.tmux.conf && \
    echo 'set -s copy-command "wl-copy"' >> $HOME/.tmux.conf && \
    # uv - fast Python package manager
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    # Python tools via uv
    $HOME/.local/bin/uv tool install pre-commit && \
    $HOME/.local/bin/uv tool install ruff && \
    $HOME/.local/bin/uv tool install ansible-lint && \
    $HOME/.local/bin/uv tool install ty && \
    # Browser automation (glibc = playwright just works!)
    npx playwright install chromium

ENV EMACS_CONTAINER=1

# ENTRYPOINT script for GUI launch
COPY --chown=$USERNAME:$USERNAME entrypoint.sh $HOME/
RUN chmod +x $HOME/entrypoint.sh

ENTRYPOINT ["sh", "-c", "exec \"$HOME/entrypoint.sh\" \"$@\"", "--"]
