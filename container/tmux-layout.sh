#!/bin/sh
set -e
SESSION="dev"

# Reattach if session already exists (-d detaches other clients for proper resizing)
if tmux has-session -t "$SESSION" 2>/dev/null; then
    exec tmux attach-session -d -t "$SESSION"
fi

CONFIG="$HOME/.config/tmuxinator/dev.yml"
WS="${WORKSPACE_FOLDER:-$(pwd)}"
PROMPT_FILE="$WS/.devcontainer/.agent-prompt"
AGENT_FILE="$WS/.devcontainer/.agent-name"

# If prompt file exists, patch config with prompt for the target agent
if [ -f "$PROMPT_FILE" ]; then
    PROMPT=$(cat "$PROMPT_FILE")
    AGENT=$(cat "$AGENT_FILE" 2>/dev/null || echo "claude")
    rm -f "$PROMPT_FILE" "$AGENT_FILE"

    case "$AGENT" in
        claude)  CMD="claude" ;;
        gemini)  CMD="gemini" ;;
        codex)   CMD="codex" ;;
        pi)      CMD="pi" ;;
        *)       CMD="$AGENT" ;;
    esac
    CMD="notify stamp && $CMD"

    TMP_CONFIG=$(mktemp)
    cp "$CONFIG" "$TMP_CONFIG"
    ESCAPED=$(printf '%s' "$CMD $PROMPT" | sed 's/[&/\]/\\&/g')
    sed -i "s|  - $AGENT:.*|  - $AGENT: $ESCAPED|" "$TMP_CONFIG"
    sed -i "s|startup_window:.*|startup_window: $AGENT|" "$TMP_CONFIG"

    exec tmuxinator start -p "$TMP_CONFIG"
fi

exec tmuxinator start dev
