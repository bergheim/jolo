# /deploy-preview

Package the current project and prepare for preview deployment.

## Arguments

- `--branch`: Target branch name (default: `preview/<current-branch>`)
- `--message`: Commit message for the deployment commit

## Instructions

1. **Pre-flight checks:**
   - Ensure working directory is clean (no uncommitted changes)
   - Ensure all tests pass: `pnpm test` or `make test` or equivalent
   - Ensure build succeeds: `pnpm build` or `make build` or equivalent

2. **Prepare the deployment:**
   - Create or update the preview branch from current HEAD
   - If there are build artifacts that need to be committed (check for `dist/`, `build/`), add them

3. **Push and report:**
   - Push the preview branch to origin with `--force-with-lease`
   - Output the branch name and any relevant URLs

4. **If a CI/CD config exists** (`.github/workflows/`, `.gitlab-ci.yml`, etc.):
   - Note which workflows will be triggered
   - Provide a link to view the workflow status if possible (using `gh` CLI)

5. **Create a draft PR** if one doesn't exist:
   ```bash
   gh pr create --draft --title "Preview: <description>" --body "Preview deployment from <branch>"
   ```

## Notes

- This skill assumes the project has a build step. If not, it will just push the branch.
- Never force push to `main` or `master`.

## Example Usage

```
/deploy-preview
/deploy-preview --branch preview/feature-x --message "Preview new auth flow"
```
