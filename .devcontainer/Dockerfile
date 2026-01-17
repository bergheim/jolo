FROM localhost/emacs-gui:latest

USER root
RUN apk add --no-cache nodejs npm
LABEL devcontainer.metadata='[{"workspaceFolder":"/workspace"}]'

# Create runtime directory for Wayland/XDG
RUN mkdir -p /tmp/container-runtime && chmod 1777 /tmp/container-runtime

WORKDIR /workspace
