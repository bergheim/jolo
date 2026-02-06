#!/bin/sh
# Smart Emacs launcher - GUI when available, terminal otherwise

if [ -n "$SSH_CLIENT" ] || [ -n "$SSH_CONNECTION" ] || [ -n "$SSH_TTY" ]; then
    # SSH session - terminal mode
    emacs -nw "$@"
elif [ -n "$WAYLAND_DISPLAY" ] || [ -n "$DISPLAY" ]; then
    # GUI available
    emacs "$@"
else
    # Fallback to terminal
    emacs -nw "$@"
fi
