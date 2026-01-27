# /new-worktree

Create a new git worktree with a devcontainer, following naming conventions and optionally creating a draft PR.

## Arguments

- `name` (required): Feature/branch name (will be prefixed appropriately)
- `--from`: Base branch to create from (default: `main`)
- `--type`: `feature`, `fix`, `chore`, `experiment` (default: `feature`)
- `--pr`: Create a draft PR immediately
- `--prompt`: AI prompt to pass to the new container

## Instructions

1. **Construct the branch name** based on type:
   - `feature` -> `feature/<name>`
   - `fix` -> `fix/<name>`
   - `chore` -> `chore/<name>`
   - `experiment` -> `experiment/<name>`

2. **Create the worktree and container** using jolo:
   ```bash
   jolo --tree <name> --from <base>
   ```

3. **If `--pr` is specified**, create a draft PR:
   ```bash
   gh pr create --draft \
     --title "<type>: <name>" \
     --body "## Summary\n\nWork in progress.\n\n## Test Plan\n\n- [ ] TODO"
   ```
   - Add appropriate labels based on type:
     - `feature` -> label `enhancement`
     - `fix` -> label `bug`
     - `chore` -> label `chore`
     - `experiment` -> label `experimental`

4. **If `--prompt` is specified**, pass it through to jolo:
   ```bash
   jolo --tree <name> --from <base> -p "<prompt>"
   ```

5. **Report:**
   - Worktree location
   - Branch name
   - PR URL (if created)
   - How to attach: `jolo --attach` from the worktree directory

## Example Usage

```
/new-worktree auth-refactor
/new-worktree login-bug --type fix --pr
/new-worktree dark-mode --type feature --pr --prompt "implement dark mode toggle"
```
