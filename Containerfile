FROM alpine:edge

# Alpine uses musl libc - we use system Chromium with Playwright API
# This gives us excellent package coverage AND browser automation

# Skip Playwright's bundled browser - use system Chromium instead
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser
ENV CHROME_PATH=/usr/bin/chromium

RUN apk update && apk add --no-cache \
    autoconf \
    automake \
    bash \
    bat \
    bubblewrap \
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
    gettext-envsubst \
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
    nsjail \
    openssh-client \
    parallel \
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
    socat \
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

# Real glibc layer (x86_64 only). The Antigravity CLI (agy, installed later as
# the agent user) is a glibc binary needing <= GLIBC_2.25; musl's gcompat lacks
# glibc internals (__open/__read/__lseek), so a full glibc is required. Install
# only the `glibc` pkg: `glibc-bin` pulls libc6-compat -> gcompat, which collides
# on the loader. The pkg ships only /lib/ld-linux...; symlink /lib64 (agy's
# interpreter path, absent on Alpine) to it.
RUN curl -fsSL -o /etc/apk/keys/sgerrand.rsa.pub https://alpine-pkgs.sgerrand.com/sgerrand.rsa.pub && \
    curl -fsSL -o /tmp/glibc.apk https://github.com/sgerrand/alpine-pkg-glibc/releases/download/2.35-r1/glibc-2.35-r1.apk && \
    apk add --no-cache /tmp/glibc.apk && \
    mkdir -p /lib64 && ln -sf /usr/glibc-compat/lib/ld-linux-x86-64.so.2 /lib64/ld-linux-x86-64.so.2 && \
    rm -f /tmp/glibc.apk

USER $USERNAME
ENV HOME=/home/$USERNAME
WORKDIR $HOME

# Pre-commit cache primed at build time to avoid first-commit delays
ENV PRE_COMMIT_HOME=/opt/pre-commit-cache

# pnpm for all Node.js global packages
ENV PNPM_HOME=$HOME/.local/share/pnpm
ENV PATH="$PNPM_HOME/bin:$HOME/.bun/bin:/usr/local/go/bin:$HOME/go/bin:$HOME/.local/bin:$PATH"

# All Node.js global packages in one pnpm install.
# pnpm gates install-time scripts; allow the ones pi/gemini need (else silently skipped).
RUN pnpm add -g \
    --allow-build=@google/genai \
    --allow-build=protobufjs \
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
    @earendil-works/pi-coding-agent \
    pi-acp \
    @agentclientprotocol/claude-agent-acp@latest \
    @zed-industries/codex-acp@latest \
    markdownlint-cli \
    pa11y \
    lighthouse \
    @lhci/cli

RUN cargo install --locked --root $HOME/.local bacon squawk

# Downloads and installs (parallel — cached layer, rarely changes)
RUN mkdir -p $HOME/.local/bin && \
    gem install --user-install --bindir "$HOME/.local/bin" tmuxinator && \
    pids="" && \
    (curl -fsSL -o $HOME/.local/bin/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64-musl && chmod +x $HOME/.local/bin/tailwindcss) & pids="$pids $!" && \
    (go install github.com/air-verse/air@latest) & pids="$pids $!" && \
    (go install github.com/zricethezav/gitleaks/v8@latest) & pids="$pids $!" && \
    (go install github.com/a-h/templ/cmd/templ@latest) & pids="$pids $!" && \
    (curl -fsSL https://bun.sh/install | bash) & pids="$pids $!" && \
    (curl -fsSL https://raw.githubusercontent.com/gastownhall/beads/main/scripts/install.sh | bash) & pids="$pids $!" && \
    (curl -fsSL -o $HOME/.local/bin/expert https://github.com/expert-lsp/expert/releases/latest/download/expert_linux_amd64 && chmod +x $HOME/.local/bin/expert) & pids="$pids $!" && \
    (uv tool install ruff) & pids="$pids $!" && \
    (uv tool install ty) & pids="$pids $!" && \
    (uv tool install pre-commit) & pids="$pids $!" && \
    (uv tool install open-terminal) & pids="$pids $!" && \
    for p in $pids; do wait "$p" || exit 1; done && \
    curl -fsSL https://claude.ai/install.sh | bash && \
    command -v claude >/dev/null && \
    # browser-check wrapper (resolve playwright's real node_modules at build time)
    printf '#!/bin/sh\nNODE_PATH=%s exec node /usr/local/lib/browser-check.js "$@"\n' "$(dirname "$(pnpm ls -g playwright --depth 0 --json | jq -r '.[0].dependencies.playwright.path')")" > $HOME/.local/bin/browser-check && \
    chmod +x $HOME/.local/bin/browser-check

# Antigravity CLI (agy): ships glibc-only with no musl build, so the upstream
# installer 404s on Alpine. Fetch the glibc tarball directly; it runs via the
# glibc layer installed above. Final 'agy --version' gates a working install.
RUN manifest="$(curl -fsSL https://antigravity-cli-auto-updater-974169037036.us-central1.run.app/manifests/linux_amd64.json)" && \
    curl -fsSL -o /tmp/agy.tar.gz "$(echo "$manifest" | jq -r .url)" && \
    echo "$(echo "$manifest" | jq -r .sha512)  /tmp/agy.tar.gz" | sha512sum -c - && \
    tar -xzf /tmp/agy.tar.gz -C /tmp antigravity && \
    install -m755 /tmp/antigravity $HOME/.local/bin/agy && \
    rm -f /tmp/agy.tar.gz /tmp/antigravity && \
    agy --version

COPY --chown=$USERNAME:$USERNAME container/pre-commit-hooks.yaml /tmp/pre-commit-hooks.yaml
RUN git config --global init.defaultBranch main
RUN cd /tmp && git init pre-commit-repo && cd pre-commit-repo && \
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
    echo 'alias agy="agy --dangerously-skip-permissions"' >> $HOME/.zshrc.container && \
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
COPY --chmod=755 container/e container/wt container/motd container/notify container/db container/npm container/npx container/pnpmx container/share /usr/local/bin/
COPY --chown=$USERNAME:$USERNAME container/entrypoint.sh container/tmux-layout.sh $HOME/
RUN mkdir -p $HOME/.config/tmuxinator
COPY --chown=$USERNAME:$USERNAME container/dev.yml $HOME/.config/tmuxinator/dev.yml
COPY --chown=$USERNAME:$USERNAME container/zimrc $HOME/.zimrc
RUN chmod +x $HOME/entrypoint.sh $HOME/tmux-layout.sh && \
    mkdir -p $HOME/.claude && \
    ln -sfn $HOME/.agents/skills $HOME/.claude/skills && \
    curl -fsSL -o $HOME/.zim/zimfw.zsh --create-dirs \
        https://github.com/zimfw/zimfw/releases/latest/download/zimfw.zsh && \
    zsh -c "ZIM_HOME=$HOME/.zim source $HOME/.zim/zimfw.zsh init -q"

ENTRYPOINT ["sh", "-c", "exec \"$HOME/entrypoint.sh\" \"$@\"", "--"]
