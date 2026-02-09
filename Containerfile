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
    build-base \
    chromium \
    cmake \
    coreutils \
    curl \
    dbus \
    diffutils \
    emacs-pgtk-nativecomp \
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
    go \
    golangci-lint \
    gstreamer \
    gum \
    hunspell \
    hunspell-en-us \
    jq \
    just \
    libsixel \
    libsixel-utils \
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
    ripgrep \
    ruby \
    cargo \
    rust \
    rust-analyzer \
    shellcheck \
    sqlite \
    sudo \
    tmux \
    tmuxinator \
    uv \
    wget \
    wl-clipboard \
    yadm \
    yamllint \
    yq \
    zoxide \
    zsh \
    gopls \
    # Tools that were manually installed in Wolfi
    ansible-lint \
    mise \
    pnpm \
    pre-commit \
    ruff \
    typescript \
    # Chromium dependencies for headless operation
    nss \
    freetype \
    harfbuzz \
    ttf-freefont \
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
    chmod 0440 /etc/sudoers.d/$USERNAME

# Root-level files and setup
COPY container/e /usr/local/bin/e
COPY container/wt /usr/local/bin/wt
COPY container/motd /usr/local/bin/motd
COPY container/browser-check.js /usr/local/lib/browser-check.js
RUN chmod +x /usr/local/bin/e /usr/local/bin/wt /usr/local/bin/motd && \
    ln -s /usr/share/zsh/plugins/fzf/completion.zsh /usr/share/fzf/completion.zsh && \
    wget -qO /usr/local/bin/hadolint https://github.com/hadolint/hadolint/releases/latest/download/hadolint-Linux-x86_64 && \
    chmod +x /usr/local/bin/hadolint

USER $USERNAME
ENV HOME=/home/$USERNAME
WORKDIR $HOME

# pnpm for all Node.js global packages
ENV PNPM_HOME=$HOME/.local/share/pnpm
ENV PATH="$PNPM_HOME:$HOME/.bun/bin:/usr/local/go/bin:$HOME/go/bin:$HOME/.local/bin:$PATH"

# All Node.js global packages in one pnpm install
RUN pnpm add -g \
    @biomejs/biome \
    playwright \
    @playwright/mcp \
    typescript-language-server \
    vscode-langservers-extracted \
    bash-language-server \
    yaml-language-server \
    dockerfile-language-server-nodejs \
    pyright \
    @ansible/ansible-language-server \
    @openai/codex \
    @google/gemini-cli

# Downloads and installs (parallel — cached layer, rarely changes)
RUN mkdir -p $HOME/.local/bin && \
    pids="" && \
    (go install github.com/air-verse/air@latest) & pids="$pids $!" && \
    (curl -fsSL https://bun.sh/install | bash) & pids="$pids $!" && \
    (curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash) & pids="$pids $!" && \
    (uv tool install ty) & pids="$pids $!" && \
    for p in $pids; do wait "$p" || exit 1; done && \
    curl -fsSL https://claude.ai/install.sh | bash && \
    command -v claude >/dev/null && \
    # browser-check wrapper (resolve pnpm global node_modules at build time)
    printf '#!/bin/sh\nNODE_PATH=%s exec node /usr/local/lib/browser-check.js "$@"\n' "$(pnpm root -g)" > $HOME/.local/bin/browser-check && \
    chmod +x $HOME/.local/bin/browser-check

# Config (changes often — keep on its own layer)
RUN mkdir -p $HOME/.config/emacs $HOME/.claude $HOME/.gemini $HOME/.codex && \
    mkdir -p $HOME/.gnupg && chmod 700 $HOME/.gnupg && \
    echo "allow-loopback-pinentry" > $HOME/.gnupg/gpg-agent.conf && \
    echo 'set -g allow-passthrough on' > /etc/tmux.conf && \
    echo 'set -g terminal-features ",xterm-256color:sixel,wezterm:sixel"' >> /etc/tmux.conf && \
    echo 'set -s set-clipboard on' > $HOME/.tmux.conf && \
    echo 'set -s copy-command "wl-copy"' >> $HOME/.tmux.conf && \
    echo 'set -g base-index 1' >> $HOME/.tmux.conf && \
    echo 'alias claude="claude --dangerously-skip-permissions"' >> $HOME/.zshrc.container && \
    echo 'alias gemini="gemini --yolo --no-sandbox"' >> $HOME/.zshrc.container && \
    echo 'alias codex="codex --dangerously-bypass-approvals-and-sandbox"' >> $HOME/.zshrc.container && \
    echo 'alias vi=nvim' >> $HOME/.zshrc.container && \
    echo 'alias vim=nvim' >> $HOME/.zshrc.container && \
    echo 'export EDITOR=nvim' >> $HOME/.zshrc.container && \
    # echo '[ -z "$TERMINFO" ] && [ ! -f "/usr/share/terminfo/t/tmux-direct" ] && export TERM=tmux-256color' >> $HOME/.zshrc.container && \
    echo 'export TERM=tmux-256color' >> $HOME/.zshrc.container && \
    echo 'eval "$(mise activate zsh)"' >> $HOME/.zshrc.container && \
    echo 'motd 2>/dev/null' >> $HOME/.zshrc.container

ENV EMACS_CONTAINER=1

# Container scripts, tmuxinator layout, and zimfw
COPY --chown=$USERNAME:$USERNAME container/entrypoint.sh container/tmux-layout.sh $HOME/
RUN mkdir -p $HOME/.config/tmuxinator
COPY --chown=$USERNAME:$USERNAME container/dev.yml $HOME/.config/tmuxinator/dev.yml
COPY --chown=$USERNAME:$USERNAME container/zimrc $HOME/.zimrc
RUN chmod +x $HOME/entrypoint.sh $HOME/tmux-layout.sh && \
    curl -fsSL -o $HOME/.zim/zimfw.zsh --create-dirs \
        https://github.com/zimfw/zimfw/releases/latest/download/zimfw.zsh && \
    zsh -c "ZIM_HOME=$HOME/.zim source $HOME/.zim/zimfw.zsh init -q"

ENTRYPOINT ["sh", "-c", "exec \"$HOME/entrypoint.sh\" \"$@\"", "--"]
