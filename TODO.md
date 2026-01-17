# TODO

## Zero-Config GPG Signing - VERIFIED WORKING

**Goal:** GPG signing should work immediately in devcontainers with no manual setup.

### Implementation
- [x] `entrypoint.sh` - GPG setup inlined (symlinks socket + imports public key)
- [x] `Containerfile` - copies entrypoint.sh into image
- [x] `.devcontainer/devcontainer.json` - mounts host GPG socket directory
- [x] `yolo.py` - templates updated with dynamic paths

### Portability Fixes
- [x] Replaced hardcoded `/home/tsb/` with `${localEnv:USER}` in devcontainer.json
- [x] Replaced hardcoded `/tmp/runtime-1000/` with `/tmp/container-runtime/`
- [x] yolo.py substitutes `CONTAINER_USER` placeholder with actual username

### Verification
```bash
gpg --list-keys
git commit --allow-empty -m "Test signed commit"
git log -1 --show-signature
```

GPG socket should be at: `~/.gnupg/S.gpg-agent -> /tmp/container-runtime/gnupg/S.gpg-agent`
