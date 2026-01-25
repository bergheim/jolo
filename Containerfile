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
    python3 \
    ripgrep \
    rust \
    rust-analyzer \
    sqlite \
    sudo \
    tmux \
    ttf-dejavu \
    wayland-libs-client \
    wayland-libs-cursor \
    wl-clipboard \
    wget \
    yadm \
    yq \
    zoxide \
    zsh

RUN npm install -g \
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

USER $USERNAME
ENV HOME /home/$USERNAME
WORKDIR $HOME

# Local npm prefix for user-managed tools (AI CLIs, etc.)
ENV NPM_CONFIG_PREFIX=$HOME/.npm-global
ENV PATH="$HOME/.npm-global/bin:/usr/local/go/bin:$HOME/go/bin:$HOME/.local/bin:$PATH"

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
    # AI tools (installed to ~/.npm-global via NPM_CONFIG_PREFIX)
    npm i -g @google/gemini-cli && \
    echo 'alias claude="claude --dangerously-skip-permissions"' >> $HOME/.zshrc.container && \
    echo 'alias vi=nvim' >> $HOME/.zshrc.container && \
    # tmux clipboard (OSC 52) - enable clipboard passthrough to terminal
    echo 'set -s set-clipboard on' > $HOME/.tmux.conf && \
    echo 'set -s copy-command "wl-copy"' >> $HOME/.tmux.conf

# don't load elfeed, org, etc
ENV EMACS_CONTAINER=1

# ENTRYPOINT script for GUI launch
COPY --chown=$USERNAME:$USERNAME entrypoint.sh $HOME/
RUN chmod +x $HOME/entrypoint.sh

ENTRYPOINT ["sh", "-c", "exec \"$HOME/entrypoint.sh\" \"$@\"", "--"]
