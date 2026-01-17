# TODO

## Zero-Config GPG Signing - FIXED

**Goal:** GPG signing should work immediately in devcontainers with no manual setup.

### Solution
Mount only what's needed (no private keys exposed):
1. `pubring.kbx` (read-only) - public keyring so GPG knows what keys exist
2. `trustdb.gpg` (read-only) - trust database
3. `gnupg` socket directory - agent socket for signing operations

The entrypoint.sh symlinks the socket to `~/.gnupg/S.gpg-agent`. Private keys stay on the host; the agent handles signing.

### Portability Fixes - DONE
- [x] yolo.py template uses `${localEnv:USER}` for all target paths
- [x] yolo.py template uses `${localEnv:HOME}` for all source paths
- [x] All three GPG mounts included in template (pubring.kbx, trustdb.gpg, socket dir)

### Verification
```bash
gpg --list-secret-keys  # Should show your key
git commit --allow-empty -m "Test signed commit"
git log -1 --show-signature
```

## Code Quality Fixes - DONE

- [x] Added `.gitignore` for secrets, build artifacts, editor files
- [x] Fixed duplicate GPG config in `Containerfile`
- [x] Fixed DBus daemon setup in `entrypoint.sh` (was commented out but address still exported)
- [x] Fixed `.zshrc.container` overwrite bug in `Containerfile` (`>` -> `>>`)
- [x] Added `yolo.py` to version control
