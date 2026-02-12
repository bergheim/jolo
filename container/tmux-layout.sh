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

    RESEARCH_FILE="$WS/.devcontainer/.research-mode"
    RESEARCH_MODE=false
    if [ -f "$RESEARCH_FILE" ]; then
        RESEARCH_MODE=true
        rm -f "$RESEARCH_FILE"
    fi

    TMP_CONFIG=$(mktemp)
    cp "$CONFIG" "$TMP_CONFIG"

    if [ "$RESEARCH_MODE" = true ]; then
        # Write wrapper script; escape shell metacharacters in prompt
        WRAPPER=$(mktemp)
        printf '#!/bin/sh\n' > "$WRAPPER"
        # Escape \, $, `, ", ! to prevent expansion inside double quotes
        SAFE_PROMPT=$(printf '%s' "$PROMPT" | sed -e 's/\\/\\\\/g' -e 's/\$/\\$/g' -e 's/`/\\`/g' -e 's/"/\\"/g' -e 's/!/\\!/g')
        printf '%s "%s"\nsleep 5\nkill 1\n' "$CMD" "$SAFE_PROMPT" >> "$WRAPPER"
        chmod +x "$WRAPPER"
        cat > "$TMP_CONFIG" <<YAML
name: dev
windows:
  - $AGENT: $WRAPPER
YAML
    else
        ESCAPED=$(printf '%s' "$CMD $PROMPT" | sed 's/[&/\]/\\&/g')
        sed -i "s|  - $AGENT:.*|  - $AGENT: $ESCAPED|" "$TMP_CONFIG"
        # Focus on the prompted agent's window
        sed -i "s|startup_window:.*|startup_window: $AGENT|" "$TMP_CONFIG"
    fi

    exec tmuxinator start -p "$TMP_CONFIG"
fi

exec tmuxinator start dev
