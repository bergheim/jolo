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
    mesa \
    ncurses \
    ncurses-terminfo \
    ncurses-terminfo-base \
    neovim \
    nodejs \
    npm \
    openssh-client \
    pinentry \
    pkgconf \
    podman \
    python3 \
    py3-pip \
    ripgrep \
    rust \
    rust-analyzer \
    shellcheck \
    sqlite \
    sudo \
    tmux \
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

# npm global packages (language servers, etc.)
# Note: agent-browser excluded - ships glibc binary, won't work on Alpine
# Note: playwright included - works with system Chromium via executablePath
# Note: typescript and pnpm now from apk
RUN npm install -g \
    @biomejs/biome \
    playwright \
    typescript-language-server \
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

# fzf completion.zsh lives in /usr/share/zsh/plugins/fzf/ on Alpine
# but most configs expect /usr/share/fzf/completion.zsh
RUN ln -s /usr/share/zsh/plugins/fzf/completion.zsh /usr/share/fzf/completion.zsh

# hadolint (Dockerfile linter) - static binary works on musl
RUN wget -qO /usr/local/bin/hadolint https://github.com/hadolint/hadolint/releases/latest/download/hadolint-Linux-x86_64 && \
    chmod +x /usr/local/bin/hadolint

# browser-check - Alpine-compatible browser automation CLI
COPY browser-check.js /usr/local/lib/browser-check.js
RUN printf '#!/bin/sh\nNODE_PATH=/usr/lib/node_modules exec node /usr/local/lib/browser-check.js "$@"\n' > /usr/local/bin/browser-check && \
    chmod +x /usr/local/bin/browser-check

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
    echo 'alias gemini="gemini --yolo"' >> $HOME/.zshrc.container && \
    echo 'alias vi=nvim' >> $HOME/.zshrc.container && \
    # Fallback TERM if tmux-direct not in terminfo
    echo '[ -z "$TERMINFO" ] && [ ! -f "/usr/share/terminfo/t/tmux-direct" ] && export TERM=tmux-256color' >> $HOME/.zshrc.container && \
    curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash && \
    # tmux clipboard (OSC 52)
    echo 'set -s set-clipboard on' > $HOME/.tmux.conf && \
    echo 'set -s copy-command "wl-copy"' >> $HOME/.tmux.conf && \
    # Python tools via uv (only ones not in apk)
    # pre-commit, ruff, ansible-lint now from apk
    uv tool install ty && \
    # mise from apk, just need to activate it
    echo 'eval "$(mise activate zsh)"' >> $HOME/.zshrc.container

ENV EMACS_CONTAINER=1

# ENTRYPOINT script for GUI launch
COPY --chown=$USERNAME:$USERNAME entrypoint.sh $HOME/
RUN chmod +x $HOME/entrypoint.sh

ENTRYPOINT ["sh", "-c", "exec \"$HOME/entrypoint.sh\" \"$@\"", "--"]
