# TODO

## Zero-Config GPG Signing - DONE

GPG signing works immediately with no manual setup.

**Mounts:**
- `pubring.kbx` (read-only) - public keyring
- `trustdb.gpg` (read-only) - trust database
- `S.gpg-agent` socket - mounted directly to `~/.gnupg/S.gpg-agent`

Private keys stay on host; agent handles signing.

## GitHub CLI - DONE

`gh` command works via mounted config.

**Mount:**
- `~/.config/gh` (read-only)

## Code Quality Fixes - DONE

- [x] `.gitignore` for secrets, build artifacts, editor files
- [x] Fixed duplicate GPG config in `Containerfile`
- [x] Fixed DBus daemon setup in `entrypoint.sh`
- [x] Fixed `.zshrc.container` overwrite bug in `Containerfile`
- [x] `yolo.py` in version control
