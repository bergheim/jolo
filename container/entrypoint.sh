#!/bin/sh
# entrypoint.sh: Container startup - GPG setup, DBus, tmux/emacs launch
set -e

# Set up XDG directories (use env var if set by devcontainer, else compute)
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/runtime-$(id -u)}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"

mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME"

# Export GPG_TTY for gpg-agent/pinentry communication
GPG_TTY="$(tty 2>/dev/null || echo "/dev/console")"
export GPG_TTY

# GPG setup: symlink to forwarded agent socket if available
GPG_SOCKET="$XDG_RUNTIME_DIR/gnupg/S.gpg-agent"
if [ -S "$GPG_SOCKET" ]; then
    echo "GPG: Found forwarded agent at $GPG_SOCKET"
    mkdir -p "$HOME/.gnupg"
    chmod 700 "$HOME/.gnupg"
    ln -sf "$GPG_SOCKET" "$HOME/.gnupg/S.gpg-agent"
    echo "GPG: Ready for signing"
else
    echo "GPG: No forwarded agent at $GPG_SOCKET - signing won't work"
fi

# Start session bus for Emacs GUI (needed for DBus features)
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

# PostgreSQL: init on first boot, start in background
PGDATA="${WORKSPACE_FOLDER:-.}/.devcontainer/.pgdata"
if [ ! -d "$PGDATA" ]; then
    initdb -D "$PGDATA" --auth=trust --no-locale -E UTF8
    echo "host all all 0.0.0.0/0 trust" >> "$PGDATA/pg_hba.conf"
    cat >> "$PGDATA/postgresql.conf" <<PGCONF
listen_addresses = '*'
unix_socket_directories = '/tmp'
PGCONF
fi
pg_ctl -D "$PGDATA" -l "$PGDATA/server.log" start
createdb -h /tmp "$(whoami)" 2>/dev/null || true

# Start open-terminal on the last port in the container's range
if [ -n "$PORT" ] && command -v open-terminal >/dev/null 2>&1; then
    OT_PORT=$((PORT + 3))
    open-terminal run --host 0.0.0.0 --port "$OT_PORT" --api-key "${OPEN_TERMINAL_API_KEY:-devcontainer}" &
    echo "open-terminal: listening on port $OT_PORT"
fi

if [ "$START_EMACS" = "true" ]; then
    exec emacs --fg-daemon
else
    exec sleep infinity
fi
