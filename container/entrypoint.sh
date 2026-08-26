#!/bin/sh
# entrypoint.sh: PID 1+ — XDG dirs, DBus session bus, open-terminal, emacs/sleep
set -e

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/runtime-$(id -u)}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"

mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME"

# Host+container service URLs. Stash is already mounted; missing file is a no-op.
if [ -r /workspaces/stash/.profile.container ]; then
    set -a
    # shellcheck disable=SC1091
    . /workspaces/stash/.profile.container
    set +a
fi

# Host ~/.agents/skills + jolo templates/skills. Never wipe ~/.agents/skills
# if it is still the old templates bind — that deletes the checkout.
_host_skills="$HOME/.agents/host-skills"
_jolo_skills="$HOME/.agents/jolo-skills"
_union_skills="$HOME/.agents/skills"
if [ -d "$_host_skills" ] && [ -d "$_jolo_skills" ]; then
    if ! awk -v t="$_union_skills" '$5 == t { found=1 } END { exit !found }' /proc/self/mountinfo 2>/dev/null; then
        _tmp="$_union_skills.tmp"
        rm -rf "$_tmp"
        mkdir -p "$_tmp"
        _shadowed=
        for _d in "$_host_skills"/*; do
            [ -e "$_d" ] || continue
            ln -sfn "$_d" "$_tmp/$(basename "$_d")"
        done
        for _d in "$_jolo_skills"/*; do
            [ -e "$_d" ] || continue
            _name=$(basename "$_d")
            if [ -e "$_tmp/$_name" ] || [ -L "$_tmp/$_name" ]; then
                _shadowed="$_shadowed $_name"
            fi
            ln -sfn "$_d" "$_tmp/$_name"
        done
        rm -rf "$_union_skills"
        mv "$_tmp" "$_union_skills"
        if [ -n "$_shadowed" ]; then
            echo "skills: jolo overrides$_shadowed"
        fi
        ln -sfn "$_union_skills" "$HOME/.claude/skills"
    fi
fi

GPG_TTY="$(tty 2>/dev/null || echo "/dev/console")"
export GPG_TTY

# Session bus for Emacs GUI / DBus features
if [ -z "$DBUS_SESSION_BUS_ADDRESS" ]; then
    mkdir -p "$XDG_RUNTIME_DIR"
    dbus-daemon --session --fork --address="unix:path=$XDG_RUNTIME_DIR/bus" 2>/dev/null || true
    export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
fi

export NO_AT_BRIDGE=1

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
