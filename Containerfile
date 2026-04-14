FROM alpine:edge

# Alpine uses musl libc - we use system Chromium with Playwright API
# This gives us excellent package coverage AND browser automation

# Skip Playwright's bundled browser - use system Chromium instead
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser

RUN apk update && apk add --no-cache \
    autoconf \
    automake \
    bash \
    bat \
    build-base \
    bind-tools \
    chromium \
    cmake \
    coreutils \
    curl \
    dbus \
    diffutils \
    emacs-gtk3-nativecomp \
    aspell-en \
    enchant2 \
    enchant2-dev \
    entr \
    eza \
    fd \
    fontconfig \
    fzf \
    fzf-zsh-plugin \
    git \
    github-cli \
    gnupg \
    elixir \
    erlang-dev \
    inotify-tools \
    go \
    golangci-lint \
    gstreamer \
    gum \
    hunspell \
    hunspell-en-us \
    jq \
    just \
    kitty-kitten \
    chafa \
    vips-tools \
    libwebp-tools \
    libavif-apps \
    libsixel \
    libsixel-tools \
    mesa \
    ncurses \
    ncurses-terminfo \
    ncurses-terminfo-base \
    neovim \
    nodejs \
    openssh-client \
    pinentry \
    pkgconf \
    podman \
    procps \
    python3 \
    py3-pip \
    grep \
    ripgrep \
    ruby \
    cargo \
    rust \
    rust-analyzer \
    rustfmt \
    shellcheck \
    sqlite \
    sudo \
    tmux \
    uv \
    wget \
    wl-clipboard \
    yadm \
    yamllint \
    util-linux-misc \
    yq \
    poppler-utils \
    zoxide \
    zsh \
    gopls \
    postgresql \
    postgresql-client \
    postgresql-contrib \
    postgresql-pgvector \
    # Tools that were manually installed in Wolfi
    ansible-lint \
    mise \
    musl-locales \
    musl-locales-lang \
    pnpm \
    pre-commit \
    typescript \
    # build files for codex-acp
    libcap-dev \
    openssl-dev \
    # Chromium dependencies for headless operation
    nss \
    freetype \
    iproute2 \
    iproute2-ss \
    harfbuzz \
    yazi \
    ttf-freefont \
    ttf-dejavu \
    wayland-libs-client \
    wayland-libs-cursor \
    ca-certificates

# User setup
ARG USERNAME=tsb
ARG USER_ID=1000
ARG GROUP_ID=1000
ARG USER_PASSWORD=dev123

RUN addgroup -g $GROUP_ID $USERNAME && \
    adduser -D -h /home/$USERNAME -s /bin/zsh -u $USER_ID -G $USERNAME $USERNAME && \
    echo "$USERNAME:$USER_PASSWORD" | chpasswd && \
    echo "$USERNAME ALL=(ALL) ALL" > /etc/sudoers.d/$USERNAME && \
    chmod 0440 /etc/sudoers.d/$USERNAME && \
    mkdir -p /tmp/container-runtime && \
    chown $USERNAME:$USERNAME /tmp/container-runtime && \
    chmod 700 /tmp/container-runtime

# tmux system config (must be written as root)
RUN echo 'set -g allow-passthrough on' > /etc/tmux.conf && \
    echo 'set -s set-clipboard on' >> /etc/tmux.conf && \
    echo 'set -as terminal-features ",*:clipboard:sixel:extkeys"' >> /etc/tmux.conf

# Root-level setup (no script COPYs here — those go after heavy layers to avoid cache busting)
COPY container/browser-check.js /usr/local/lib/browser-check.js
RUN ln -s /usr/share/zsh/plugins/fzf/completion.zsh /usr/share/fzf/completion.zsh && \
    wget -qO /usr/local/bin/hadolint https://github.com/hadolint/hadolint/releases/latest/download/hadolint-Linux-x86_64 && \
    chmod +x /usr/local/bin/hadolint && \
    mkdir -p /workspaces /opt/pre-commit-cache && \
    chown $USERNAME:$USERNAME /workspaces /opt/pre-commit-cache

USER $USERNAME
ENV HOME=/home/$USERNAME
WORKDIR $HOME

# Pre-commit cache primed at build time to avoid first-commit delays
ENV PRE_COMMIT_HOME=/opt/pre-commit-cache

# pnpm for all Node.js global packages
ENV PNPM_HOME=$HOME/.local/share/pnpm
ENV PATH="$PNPM_HOME:$HOME/.bun/bin:/usr/local/go/bin:$HOME/go/bin:$HOME/.local/bin:$PATH"

# All Node.js global packages in one pnpm install
RUN pnpm add -g \
    @biomejs/biome \
    playwright \
    @playwright/cli \
    typescript-language-server \
    vscode-langservers-extracted \
    bash-language-server \
    yaml-language-server \
    dockerfile-language-server-nodejs \
    pyright \
    @ansible/ansible-language-server \
    @openai/codex \
    @google/gemini-cli \
    @mariozechner/pi-coding-agent \
    @agentclientprotocol/claude-agent-acp@latest \
    @zed-industries/codex-acp@latest \
    markdownlint-cli \
    pa11y

RUN cargo install bacon --locked --root $HOME/.local

# Downloads and installs (parallel — cached layer, rarely changes)
RUN mkdir -p $HOME/.local/bin && \
    gem install --user-install --bindir "$HOME/.local/bin" tmuxinator && \
    pids="" && \
    (curl -fsSL -o $HOME/.local/bin/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64-musl && chmod +x $HOME/.local/bin/tailwindcss) & pids="$pids $!" && \
    (go install github.com/air-verse/air@latest) & pids="$pids $!" && \
    (go install github.com/zricethezav/gitleaks/v8@latest) & pids="$pids $!" && \
    (go install github.com/a-h/templ/cmd/templ@latest) & pids="$pids $!" && \
    (curl -fsSL https://bun.sh/install | bash) & pids="$pids $!" && \
    (curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash) & pids="$pids $!" && \
    (uv tool install ruff) & pids="$pids $!" && \
    (uv tool install ty) & pids="$pids $!" && \
    (uv tool install open-terminal) & pids="$pids $!" && \
    for p in $pids; do wait "$p" || exit 1; done && \
    curl -fsSL https://claude.ai/install.sh | bash && \
    command -v claude >/dev/null && \
    # browser-check wrapper (resolve pnpm global node_modules at build time)
    printf '#!/bin/sh\nNODE_PATH=%s exec node /usr/local/lib/browser-check.js "$@"\n' "$(pnpm root -g)" > $HOME/.local/bin/browser-check && \
    chmod +x $HOME/.local/bin/browser-check

COPY --chown=$USERNAME:$USERNAME container/pre-commit-hooks.yaml /tmp/pre-commit-hooks.yaml
RUN git config --global init.defaultBranch main
RUN cd /tmp && git init pre-commit-repo && cd pre-commit-repo && \
    pre-commit autoupdate -c /tmp/pre-commit-hooks.yaml && \
    pre-commit install-hooks -c /tmp/pre-commit-hooks.yaml && \
    cd / && rm -rf /tmp/pre-commit-repo /tmp/pre-commit-hooks.yaml

# Config (changes often — keep on its own layer)
RUN mkdir -p $HOME/.config/emacs $HOME/.claude $HOME/.gemini $HOME/.codex $HOME/.pi && \
    mkdir -p $HOME/.gnupg && chmod 700 $HOME/.gnupg && \
    echo "allow-loopback-pinentry" > $HOME/.gnupg/gpg-agent.conf && \
    echo 'set -s set-clipboard on' > $HOME/.tmux.conf && \
    echo 'set -s copy-command "wl-copy"' >> $HOME/.tmux.conf && \
    echo 'set -g base-index 1' >> $HOME/.tmux.conf && \
    echo 'alias claude="env -u ANTHROPIC_API_KEY claude --dangerously-skip-permissions"' >> $HOME/.zshrc.container && \
    echo 'alias gemini="gemini --yolo --no-sandbox"' >> $HOME/.zshrc.container && \
    echo 'alias codex="codex --dangerously-bypass-approvals-and-sandbox"' >> $HOME/.zshrc.container && \
    echo 'alias vi=nvim' >> $HOME/.zshrc.container && \
    echo 'alias vim=nvim' >> $HOME/.zshrc.container && \
    echo "alias icat='kitten icat'" >> $HOME/.zshrc.container && \
    echo 'export EDITOR=nvim' >> $HOME/.zshrc.container && \
    echo 'eval "$(mise activate zsh)"' >> $HOME/.zshrc.container && \
    echo 'export HISTFILE=$HOME/.zsh-state/.histfile' >> $HOME/.zshrc.container && \
    echo '[ "$(tmux display-message -p "#{window_name}" 2>/dev/null)" = "shell" ] && motd 2>/dev/null' >> $HOME/.zshrc.container

ENV EMACS_CONTAINER=1
ENV LANG=en_US.UTF-8

# Container scripts (late layer — changes here don't bust pnpm/cargo cache)
COPY --chmod=755 container/e container/wt container/motd container/notify container/db /usr/local/bin/
COPY --chown=$USERNAME:$USERNAME container/entrypoint.sh container/tmux-layout.sh $HOME/
RUN mkdir -p $HOME/.config/tmuxinator
COPY --chown=$USERNAME:$USERNAME container/dev.yml $HOME/.config/tmuxinator/dev.yml
COPY --chown=$USERNAME:$USERNAME container/zimrc $HOME/.zimrc
RUN chmod +x $HOME/entrypoint.sh $HOME/tmux-layout.sh && \
    curl -fsSL -o $HOME/.zim/zimfw.zsh --create-dirs \
        https://github.com/zimfw/zimfw/releases/latest/download/zimfw.zsh && \
    zsh -c "ZIM_HOME=$HOME/.zim source $HOME/.zim/zimfw.zsh init -q"

ENTRYPOINT ["sh", "-c", "exec \"$HOME/entrypoint.sh\" \"$@\"", "--"]
