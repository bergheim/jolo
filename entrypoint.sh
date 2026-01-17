#!/bin/sh
# entrypoint.sh: Container startup - display detection, GPG setup, tmux/emacs launch
set -e

if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    echo "Neither DISPLAY nor WAYLAND_DISPLAY is set"
    exit 1
fi

# Set up XDG directories (use env var if set by devcontainer, else compute)
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/runtime-$(id -u)}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"

mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME"

# Export GPG_TTY for gpg-agent/pinentry communication
export GPG_TTY=$(tty 2>/dev/null || echo "/dev/console")

# GPG setup: symlink to forwarded agent socket if available
GPG_SOCKET="$XDG_RUNTIME_DIR/gnupg/S.gpg-agent"
if [ -S "$GPG_SOCKET" ]; then
    echo "GPG: Found forwarded agent at $GPG_SOCKET"
    mkdir -p "$HOME/.gnupg"
    chmod 700 "$HOME/.gnupg"
    ln -sf "$GPG_SOCKET" "$HOME/.gnupg/S.gpg-agent"

    # Import public key from keyserver if not present
    SIGNING_KEY=$(git config --global user.signingkey 2>/dev/null || true)
    if [ -n "$SIGNING_KEY" ]; then
        if ! gpg --list-keys "$SIGNING_KEY" >/dev/null 2>&1; then
            echo "GPG: Importing signing key $SIGNING_KEY from keyserver..."
            gpg --keyserver keys.openpgp.org --recv-keys "$SIGNING_KEY" 2>/dev/null || \
                echo "GPG: Warning - could not import key from keyserver"
        fi
    fi
    echo "GPG: Ready for signing"
else
    echo "GPG: No forwarded agent at $GPG_SOCKET - signing won't work"
fi

# Start session bus for Emacs GUI (needed for DBus features)
# if [ -z "$DBUS_SESSION_BUS_ADDRESS" ]; then
#     dbus-daemon --session --fork --address="unix:path=$XDG_RUNTIME_DIR/bus" || true
#     export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
# fi

export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"

export NO_AT_BRIDGE=1

# these errors are annoying:
# Gdk-Message: 13:58:28.552: Unable to load sb_v_double_arrow from the cursor theme
# export G_MESSAGES_DEBUG=""
# export XCURSOR_PATH=${XCURSOR_PATH}:~/.local/share/icons
# export XCURSOR_THEME=cursor_theme_name

if [ "$START_EMACS" = "true" ]; then
    exec emacs --fg-daemon
else
    # auto-reattach to existing, else create
    tmux attach-session -t dev || tmux new-session -s dev
fi
