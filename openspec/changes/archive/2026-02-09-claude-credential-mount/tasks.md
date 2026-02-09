## 1. Update BASE_MOUNTS in constants.py

- [x] 1.1 Replace the single `.claude-cache` directory mount with individual mounts: `.credentials.json` (RW), `statsig/` (RO), `settings.json` from cache (RW), `.claude.json` from cache (RW)
- [x] 1.2 Remove the old `.claude-cache` directory mount line
- [x] 1.3 Keep `.claude.json` mount pointing at `.devcontainer/.claude.json` (unchanged)

## 2. Update setup_credential_cache() in setup.py

- [x] 2.1 Stop copying `.credentials.json` to `.claude-cache/` (it will be mounted directly from host)
- [x] 2.2 Keep copying `settings.json` to `.claude-cache/` (needed for hook injection)
- [x] 2.3 Keep copying `statsig/` to `.claude-cache/` only if the host has it (mounted RO from host, but fallback to copy if host dir missing)
- [x] 2.4 Keep `.claude.json` copy+inject logic unchanged
- [x] 2.5 Create `.claude-cache/` directory structure so mount targets exist (settings.json needs the directory)

## 3. Verify notification hooks still work

- [x] 3.1 Confirm `setup_notification_hooks()` still writes to `.claude-cache/settings.json` and the mount path in BASE_MOUNTS points there correctly

## 4. Update tests

- [x] 4.1 Update any tests that reference the old `.claude-cache` directory mount pattern in BASE_MOUNTS
- [x] 4.2 Add test: `.credentials.json` is NOT copied to `.claude-cache/` (mount handles it)
- [x] 4.3 Add test: `settings.json` IS still copied to `.claude-cache/`
- [x] 4.4 Add test: BASE_MOUNTS contains individual file mounts instead of directory mount

## 5. Update documentation

- [x] 5.1 Update the security model section in AGENTS.md to reflect selective mounts vs copy isolation
- [x] 5.2 Update TODO.org to mark the task as DONE
