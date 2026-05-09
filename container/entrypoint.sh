#!/bin/sh
# entrypoint.sh: Container startup - DBus, open-terminal, tmux/emacs launch
set -e

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/runtime-$(id -u)}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"

mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME"

GPG_TTY="$(tty 2>/dev/null || echo "/dev/console")"
export GPG_TTY

# Session bus for Emacs GUI / DBus features
if [ -z "$DBUS_SESSION_BUS_ADDRESS" ]; then
    mkdir -p "$XDG_RUNTIME_DIR"
    dbus-daemon --session --fork --address="unix:path=$XDG_RUNTIME_DIR/bus" 2>/dev/null || true
    export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
fi

export NO_AT_BRIDGE=1

# these errors are annoying:
# Gdk-Message: 13:58:28.552: Unable to load sb_v_double_arrow from the cursor theme
# export G_MESSAGES_DEBUG=""
# export XCURSOR_PATH=${XCURSOR_PATH}:~/.local/share/icons
# export XCURSOR_THEME=cursor_theme_name

# Start open-terminal on the last port in the container's range
if [ -n "$PORT" ]; then
    OT_PORT=$((PORT + 3))
    open-terminal run --host 0.0.0.0 --port "$OT_PORT" --api-key "${OPEN_TERMINAL_API_KEY:-devcontainer}" &
    echo "open-terminal: listening on port $OT_PORT"
fi

if [ "$START_EMACS" = "true" ]; then
    exec emacs --fg-daemon
else
    exec sleep infinity
fi
