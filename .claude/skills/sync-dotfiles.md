# /sync-dotfiles

Sync the latest dotfiles from the yadm repository into the container's Emacs config sandbox.

## Arguments

- `--force`: Overwrite local changes without prompting
- `--branch`: Branch to pull from (default: `lyra-experiments`)

## Instructions

1. **Check the current state** of the Emacs config sandbox at `.devcontainer/.emacs-config/`:
   - Note any local modifications (files that differ from the last sync)
   - List modified files for the user

2. **If there are local modifications and `--force` is not set:**
   - Ask the user whether to:
     - Stash local changes
     - Overwrite local changes
     - Abort

3. **Fetch and apply updates:**
   - The sandbox is a copy, not a git worktree, so we need to:
     - Fetch the latest from the yadm repo on the host (if accessible)
     - Or note that manual sync from host is required

4. **Since the container has a copied config (not mounted):**
   - Inform the user that to get fresh dotfiles, they should:
     - Exit the container
     - Run `jolo --new` to recreate with fresh config copy
   - Or if host yadm directory is mounted, pull changes directly

5. **Post-sync:**
   - Restart Emacs daemon if running: `emacsclient -e '(kill-emacs)'` then `emacs --daemon`
   - Report what changed

## Notes

This skill handles the complexity of the sandboxed Emacs config. The container gets a *copy* of the config at launch, so true "sync" requires container recreation or manual file copying.

## Example Usage

```
/sync-dotfiles
/sync-dotfiles --force
```
