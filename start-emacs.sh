#!/bin/sh

USER_ID=$(id -u)
USERNAME=$(whoami)

ENV_FILE=".env"
ENV_ARGS=""
if [ -f "$ENV_FILE" ]; then
    ENV_ARGS=$(xargs -a "$ENV_FILE" -I {} echo -n "-e {} ")
fi

podman run -it --rm \
    --name emacs-gui --userns keep-id \
    -e WAYLAND_DISPLAY \
    -e EMACS_CONTAINER=1 \
    -v "$XDG_RUNTIME_DIR:/tmp/runtime-$USER_ID:ro" \
    -v "$HOME/.config/emacs:/home/$USERNAME/.config/emacs:Z" \
    -v "$HOME/.cache/emacs:/home/$USERNAME/.cache/emacs:Z" \
    --device /dev/dri \
    --security-opt label=disable \
    $ENV_ARGS \
    emacs-gui "$@"
