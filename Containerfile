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
    coreutils \
    curl \
    dbus \
    emacs-pgtk-nativecomp \
    enchant2 \
    enchant2-dev \
    fd \
    fontconfig \
    font-jetbrains-mono-nerd \
    font-noto-emoji \
    git \
    gnupg \
    hunspell \
    hunspell-en \
    mesa-dri-gallium \
    nodejs \
    npm \
    pinentry \
    pinentry-tty \
    pkgconf \
    python3 \
    ripgrep \
    ttf-dejavu \
    wayland-libs-client \
    wayland-libs-cursor \
    wget \
    zsh

# it's a good idea to set this to your current host user as this will enable better history location sharing. recenf etc)
# Build with say podman build --build-arg USERNAME=$(whoami) -t emacs-gui .
ARG USERNAME=tsb
ARG USER_ID=1000
ARG GROUP_ID=1000

RUN addgroup -g $GROUP_ID $USERNAME && \
    adduser -D -h /home/$USERNAME -s /bin/zsh -u $USER_ID -G $USERNAME $USERNAME

USER $USERNAME
ENV HOME /home/$USERNAME
WORKDIR $HOME

# Create ~/.config/emacs (will be mounted) and ensure ~/.gnupg dir exists with perms
RUN mkdir -p $HOME/.config/emacs && \
    mkdir -p $HOME/.gnupg && \
    echo "allow-loopback-pinentry" > $HOME/.gnupg/gpg-agent.conf && \
    chmod 700 $HOME/.gnupg

# don't load elfeed, org, etc
ENV EMACS_CONTAINER=1

# ENTRYPOINT script for GUI launch
COPY --chown=$USERNAME:$USERNAME entrypoint.sh $HOME/
RUN chmod +x $HOME/entrypoint.sh

ENTRYPOINT ["sh", "-c", "exec \"$HOME/entrypoint.sh\" \"$@\"", "--"]
