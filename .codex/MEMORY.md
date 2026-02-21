# Codex Agent Memory

Personal memory for Codex CLI. Record workflow preferences, mistake patterns,
and agent-specific learnings here. Not shared with other agents.

See `docs/MEMORY.org` for shared project knowledge.

## 2026-02-21
- Host-side fixes: rootless Podman on btrfs needs `fuse-overlayfs` with
  `~/.config/containers/storage.conf` forcing overlay + mount_program, or
  switch to btrfs driver. Corrupt store at `~/.local/share/containers/storage`
  may need wipe/move.
- `jolo create` expects a local image `localhost/emacs-gui:latest`; build and
  tag it locally if devcontainers tries to pull from registry.
- Emacs treesit warnings stem from missing grammars + no
  `treesit-language-source-alist` in config.
- User preference: don’t auto-copy URL on `jolo up/create`; make `just browse`
  Wayland-aware to open Chromium on host display.
