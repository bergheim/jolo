FROM localhost/emacs-gui:latest

USER root
RUN apk add --no-cache nodejs npm
LABEL devcontainer.metadata='[{"remoteUser":"tsb","workspaceFolder":"/workspace"}]'

WORKDIR /workspace

USER tsb
