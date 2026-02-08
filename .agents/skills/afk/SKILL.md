---
name: afk
description: Work autonomously while the user is away. Create multiple feature branches sequentially, each with a self-contained improvement.
---

# /afk

Work autonomously while the user is away. Create multiple feature branches sequentially, each with a self-contained improvement.

## Arguments

- `count` (optional): Number of branches to create (default: 5)
- `--prefix`: Branch prefix (default: `yolo`)
- `--from`: Base branch (default: current branch)

## Instructions

**CRITICAL: Do everything SEQUENTIALLY. Never run parallel agents or background tasks. Token limits are a real concern.**

1. **Check TODO.org** for existing tasks. Also review the codebase for improvement opportunities (failing tests, missing features, code quality, documentation gaps, etc.).

2. **Build a plan** of `count` independent, self-contained improvements. Each should be completable in a single branch. Prioritize:
   - Fixing failing tests
   - Items from TODO.org
   - Code quality improvements (lint fixes, type errors, dead code)
   - Small useful features
   - Test coverage gaps

3. **For each improvement, sequentially:**

   a. Check out the base branch:
      ```bash
      git checkout <from>
      ```

   b. Create a new branch:
      ```bash
      git checkout -b <prefix>/<descriptive-name>
      ```

   c. Implement the change. Write tests if applicable. Run `just test` (or `python -m pytest tests/`) to verify nothing is broken.

   d. Run `just lint` if available. Fix any issues in code you touched.

   e. Commit with a clear message describing what and why.

   f. Go back to the base branch before starting the next one:
      ```bash
      git checkout <from>
      ```

4. **After all branches are created**, print a summary:
   - Branch name + one-line description for each
   - Any branches that had issues
   - Suggestions for what to review first

## Rules

- **One branch = one concern.** Don't mix unrelated changes.
- **Don't touch the base branch.** All work happens on feature branches.
- **Don't push.** Just create local branches for the user to review.
- **Don't modify CLAUDE.md or AGENTS.md** unless that's the specific improvement.
- **Run tests after each change.** If tests fail because of your change, fix it before committing. If tests were already failing, that's fine.
- **Keep commits small and focused.** The user needs to review these quickly.
- **Sequential only.** Finish one branch completely before starting the next.

## Example Usage

```
/afk
/afk 3
/afk 5 --prefix experiment
/afk 3 --from develop
```
