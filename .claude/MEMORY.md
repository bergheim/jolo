# Claude Agent Memory — emacs-container project

See `docs/MEMORY.org` for shared project knowledge across all agents.

## Codebase quirks

- Grep tool sometimes fails to find matches in `_jolo/*.py` files — use `bash grep` as fallback
- `_jolo/` files don't show up with `Glob` pattern `_jolo/*.py` — use `**/_jolo/**/*.py` or check with `ls`
- `containerEnv` is built in `_jolo/container.py:build_devcontainer_json()`, secrets injected via `os.environ.update()` in commands.py before devcontainer starts
- Secrets flow: `get_secrets()` (setup.py) -> `os.environ.update()` (commands.py) -> `${localEnv:...}` (devcontainer.json)

## User preferences

- User runs this on Arch Linux with rootless Podman
- Host uses `pass` (password-store) for secrets
- `gh` auth token stored in OS keyring, not in `hosts.yml`
- Prefers concise changes, follows project's "plan before acting" policy

## Patterns learned

- `devcontainer_up(remove_existing=True)` means the old container will be torn down first — port checks should be skipped since the port will be freed
- `is_container_running()` is cheap (podman ps with label filter) — safe to call early and branch on the result
- motd in `.zshrc.container` runs in ALL tmux panes (claude, gemini, codex) not just shell — move per-window commands to `dev.yml` instead
- Worktree branches checked out in a worktree can't be rebased from main — must `cd` into the worktree dir and rebase from there

## Git workflow

- User prefers: rebase feature onto main, then `merge --no-ff` for multi-commit branches
- Commit style: imperative, short first line, body explains why
- `sdd` branch was a worktree at `/workspaces/sdd` — had to rebase from there

## Session context

- 2026-02-09: Added GH_TOKEN passthrough to devcontainers. The gh config mount alone is insufficient because modern gh uses OS keyring. Solution: `get_secrets()` runs `gh auth token` on host and passes result as env var.
- Could not push to GitHub from this container because it was started before the GH_TOKEN fix. Needs `jolo up --sync --new` to apply.
- 2026-02-09: Fixed `jolo up --new --sync` port conflict — skip port check when `remove_existing=True`. Added reattach notice. Moved motd from .zshrc.container to dev.yml shell window. Merged `sdd` branch (OpenSpec trial, credential RW mount).
- 2026-02-17: Moved TODO.org and RESEARCH.org to docs/ for consistency with generated projects. Deleted stale docs/STATUS.org.
- 2026-02-17: Simplified tmux terminal-features to `*:sixel:extkeys` wildcard. Host `~/.tmux.conf` is EROFS in emacs-container — can't edit from here.
- 2026-02-17: User concerned about scaffolding complexity growth. Saved flavor menu refactoring plan to docs/TODO.org (flatten `--bare` into `typescript-web`/`typescript-bare` picker). Parked for later.
- 2026-02-17: Host tmux.conf yadm sandbox has `set -g terminal-features` (no -a) that clobbers /etc/tmux.conf. User needs to fix on host side.
- 2026-02-17: Saved Claude Code skills ecosystem research to docs/research/skills-claude.org (841 lines, 30+ repos, 17 HN threads).
