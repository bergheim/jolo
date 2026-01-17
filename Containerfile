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
    build-base \
    cargo \
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
    git \
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
    pkgconf \
    py3-lsp-server \
    python3 \
    ripgrep \
    rust \
    rust-analyzer \
    sudo \
    tmux \
    ttf-dejavu \
    wayland-libs-client \
    wayland-libs-cursor \
    wget \
    yadm \
    yq \
    zoxide \
    zsh

# install go
RUN wget https://go.dev/dl/go1.23.5.linux-amd64.tar.gz && \
    tar -C /usr/local -xzf go1.23.5.linux-amd64.tar.gz && \
    rm go1.23.5.linux-amd64.tar.gz && \
    # install global language servers from npm
    npm install -g \
    typescript-language-server \
    typescript \
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

USER $USERNAME
ENV HOME /home/$USERNAME
WORKDIR $HOME

ENV PATH="/usr/local/go/bin:$HOME/go/bin:$HOME/.local/bin/:$PATH"

# Install gopls
RUN go install golang.org/x/tools/gopls@latest && \
    echo 'export PATH="$HOME/go/bin:$PATH"' >> $HOME/.zshrc.container && \
    # bun..
    curl -fsSL https://bun.sh/install | bash && \
    echo 'export PATH="$HOME/.bun/bin:$PATH"' >> $HOME/.zshrc.container && \
    # Create ~/.config/emacs (will be mounted) and ensure ~/.gnupg dir exists with perms
    mkdir -p $HOME/.config/emacs && \
    mkdir -p $HOME/.gnupg && \
    echo "allow-loopback-pinentry" > $HOME/.gnupg/gpg-agent.conf && \
    chmod 700 $HOME/.gnupg && \
    # YOLO
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> $HOME/.zshrc.container && \
    curl -fsSL https://claude.ai/install.sh | bash && \
    echo 'alias claude="claude --dangerously-skip-permissions"' > $HOME/.zshrc.container

# don't load elfeed, org, etc
ENV EMACS_CONTAINER=1

# ENTRYPOINT script for GUI launch
COPY --chown=$USERNAME:$USERNAME entrypoint.sh $HOME/
RUN chmod +x $HOME/entrypoint.sh

ENTRYPOINT ["sh", "-c", "exec \"$HOME/entrypoint.sh\" \"$@\"", "--"]
