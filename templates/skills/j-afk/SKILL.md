---
name: j-afk
description: Work autonomously while the user is away. Create multiple feature branches sequentially, each with a self-contained improvement.
---

# /j-afk

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

3. **For each improvement, run the full /j-feature-workflow sequence.** The user is away, so the quality bar is higher: branch isolation, TDD where applicable, frequent commits, and *two* external agent reviews before declaring done. The workflow is:

   a. Check out the base branch (`git checkout <from>`).
   b. Create a feature branch (`git checkout -b <prefix>/<descriptive-name>`).
   c. If feasible, write a failing test first.
   d. Implement in small increments; commit after each coherent slice.
   e. Run `just test` (or `python -m pytest tests/`) and `just lint` (if available); fix anything you broke.
   f. **First external review** — pipe the diff to codex (or gemini, claude, etc.); use the lean invocation pattern from AGENTS.md "Cross-Agent Reviews"; ask for the highest reasoning model.
   g. Apply review fixes; commit.
   h. **Second external review** — pipe again; different reviewer is fine.
   i. Apply fixes; commit. Optionally open a draft PR if a remote is configured.
   j. If this completes a TODO.org item, mark it `DONE`.
   k. Return to the base branch before starting the next improvement (`git checkout <from>`).

   Two reviews matter here precisely *because* the user is not in the loop. Skipping a review to save time defeats the point of /j-afk.

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
/j-afk
/j-afk 3
/j-afk 5 --prefix experiment
/j-afk 3 --from develop
```
