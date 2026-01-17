#!/bin/sh
# entrypoint.sh: Start D-Bus and launch Emacs GUI
set -e

if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    echo "Neither DISPLAY nor WAYLAND_DISPLAY is set"
    exit 1
fi

# Set up XDG directories
export XDG_RUNTIME_DIR="/tmp/runtime-$(id -u)"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"

mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME"

# debug things
# echo "WAYLAND_DISPLAY: $WAYLAND_DISPLAY"
# echo "XDG_RUNTIME_DIR: $XDG_RUNTIME_DIR"
# ls -la "$XDG_RUNTIME_DIR/" 2>/dev/null || echo "XDG_RUNTIME_DIR contents not accessible"

# Export GPG_TTY for gpg-agent/pinentry communication
export GPG_TTY=$(tty 2>/dev/null || echo "/dev/console")

# GPG setup: use forwarded socket from XDG_RUNTIME_DIR if available
# The socket should be at $XDG_RUNTIME_DIR/gnupg/S.gpg-agent (mounted from host)
# The keyring is at ~/.gnupg (mounted read-only from host)
GPG_SOCKET="$XDG_RUNTIME_DIR/gnupg/S.gpg-agent"
if [ -S "$GPG_SOCKET" ]; then
    echo "Using forwarded GPG agent from $GPG_SOCKET"
else
    echo "No forwarded GPG agent at $GPG_SOCKET - git signing won't work"
    echo "Ensure host gpg-agent is running: gpgconf --launch gpg-agent"
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
