#!/bin/sh

USER_ID=$(id -u)
USERNAME=$(whoami)
WORKTREE_DIR="$HOME/.cache/aimacs-lyra"
CONFIG_DIR="$HOME/.config/emacs"
ENV_FILE=".env"
ENV_ARGS=""

if [ -f "$ENV_FILE" ]; then
    ENV_ARGS=$(xargs -a "$ENV_FILE" -I {} echo -n "-e {} ")
fi

if [ ! -d "$WORKTREE_DIR" ]; then
    yadm worktree prune
    yadm worktree remove "$WORKTREE_DIR"
    yadm branch -D lyra-experiments
    rm -rf "$WORKTREE_DIR"

    yadm worktree add "$WORKTREE_DIR" -b lyra-experiments

    cd "$WORKTREE_DIR/.config/emacs"
    git init
    git remote add origin "$CONFIG_DIR"
    git fetch
    git checkout -b main --track origin/master

    # delete my secrets file, we don't need it
    rm private.el
fi

mkdir -p "$HOME/.cache/emacs-lyra"

podman run -it --rm \
    --name emacs-gui --userns keep-id \
    -e WAYLAND_DISPLAY \
    -e EMACS_CONTAINER=1 \
    -v "$XDG_RUNTIME_DIR:/tmp/runtime-$USER_ID:ro" \
    -v "$WORKTREE_DIR/.config/emacs:/home/$USERNAME/.config/emacs:Z" \
    -v "$HOME/.cache/emacs-lyra:/home/$USERNAME/.cache/emacs:Z" \
    -v "$HOME/.local/share/yadm:/home/$USERNAME/.local/share/yadm:Z" \
    -v "$HOME/llm:/home/$USERNAME/llm:Z" \
    -v "$HOME/.gnupg/pubring.kbx:/home/$USERNAME/.gnupg/pubring.kbx:ro,Z" \
    -v "$HOME/.gnupg/trustdb.gpg:/home/$USERNAME/.gnupg/trustdb.gpg:ro,Z" \
    --device /dev/dri \
    --security-opt label=disable \
    $ENV_ARGS \
    emacs-gui "$@"
