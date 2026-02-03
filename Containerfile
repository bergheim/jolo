FROM alpine:latest

RUN apk update && apk add --no-cache \
    adwaita-fonts \
    adwaita-fonts-mono \
    adwaita-fonts-sans \
    adwaita-icon-theme \
    adwaita-icon-theme-dev \
    adwaita-xfce-icon-theme \
    aspell \
    aspell-en \
    breeze-cursors \
    autoconf \
    automake \
    build-base \
    cargo \
    cmake \
    coreutils \
    curl \
    dbus \
    emacs-pgtk-nativecomp \
    enchant2 \
    enchant2-dev \
    eza \
    fd \
    fontconfig \
    font-jetbrains-mono-nerd \
    font-noto-emoji \
    github-cli \
    git \
    go \
    golangci-lint \
    gopls \
    gnupg \
    hunspell \
    hunspell-en \
    jq \
    mesa-dri-gallium \
    mise \
    ncurses-terminfo \
    ncurses-terminfo-base \
    neovim \
    nodejs \
    npm \
    pinentry \
    pinentry-tty \
    podman \
    pkgconf \
    py3-lsp-server \
    py3-pip \
    python3 \
    ripgrep \
    rust \
    rust-analyzer \
    shellcheck \
    sqlite \
    sudo \
    tmux \
    ttf-dejavu \
    wayland-libs-client \
    wayland-libs-cursor \
    wl-clipboard \
    wget \
    yadm \
    yamllint \
    yq \
    zoxide \
    zsh

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

# it's a good idea to set this to your current host user as this will enable better history location sharing. recenf etc)
# Build with say podman build --build-arg USERNAME=$(whoami) -t emacs-gui .
ARG USERNAME=tsb
ARG USER_ID=1000
ARG GROUP_ID=1000
# this is just so YOLO mode does not go bananas
ARG USER_PASSWORD=dev123

RUN addgroup -g $GROUP_ID $USERNAME && \
    adduser -D -h /home/$USERNAME -s /bin/zsh -u $USER_ID -G $USERNAME $USERNAME && \
    echo "$USERNAME:$USER_PASSWORD" | chpasswd && \
    echo "$USERNAME ALL=(ALL) ALL" > /etc/sudoers.d/$USERNAME && \
    chmod 0440 /etc/sudoers.d/$USERNAME

# Smart emacsclient wrapper (must be before USER switch)
COPY e /usr/local/bin/e
RUN chmod +x /usr/local/bin/e

# hadolint (Dockerfile linter) - not in Alpine repos
RUN wget -qO /usr/local/bin/hadolint https://github.com/hadolint/hadolint/releases/latest/download/hadolint-Linux-x86_64 && \
    chmod +x /usr/local/bin/hadolint

USER $USERNAME
ENV HOME /home/$USERNAME
WORKDIR $HOME

# Local package managers for user-managed tools (AI CLIs, etc.)
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
    echo "pinentry-program /usr/bin/pinentry-tty" >> $HOME/.gnupg/gpg-agent.conf && \
    # Claude CLI (YOLO mode)
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> $HOME/.zshrc.container && \
    curl -fsSL https://claude.ai/install.sh | bash && \
    # AI tools (installed to $PNPM_HOME via pnpm)
    pnpm add -g @google/gemini-cli @openai/codex && \
    echo 'alias claude="claude --dangerously-skip-permissions"' >> $HOME/.zshrc.container && \
    echo 'alias vi=nvim' >> $HOME/.zshrc.container && \
    curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash && \
    # tmux clipboard (OSC 52) - enable clipboard passthrough to terminal
    echo 'set -s set-clipboard on' > $HOME/.tmux.conf && \
    echo 'set -s copy-command "wl-copy"' >> $HOME/.tmux.conf && \
    # Linting tools (Python-based) + pick for interactive CLI selectors
    pip install --user pre-commit ruff ansible-lint pick && \
    # Browser automation (agent-agnostic)
    pip install --user webctl && \
    npx playwright install chromium && \
    agent-browser install && \
    # uv - fast Python package manager (10-100x faster than pip)
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    # ty - fast Python type checker (10-60x faster than mypy, from Astral)
    $HOME/.local/bin/uv tool install ty

# don't load elfeed, org, etc
ENV EMACS_CONTAINER=1

# ENTRYPOINT script for GUI launch
COPY --chown=$USERNAME:$USERNAME entrypoint.sh $HOME/
RUN chmod +x $HOME/entrypoint.sh

ENTRYPOINT ["sh", "-c", "exec \"$HOME/entrypoint.sh\" \"$@\"", "--"]
