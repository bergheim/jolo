---
name: regression-triage
description: Fast commit-range regression triage. Given a known-good and known-bad commit, isolate likely culprit commits using focused diffs and reproducible probes.
---

# /regression-triage

Use this when behavior worked before and fails now.

## Inputs

- `GOOD_SHA` (last known good commit)
- `BAD_SHA` (first known bad commit or `HEAD`)
- Optional: failing command and expected behavior

## Workflow

1. Confirm range:
   - `git rev-parse --short GOOD_SHA BAD_SHA`
   - `git log --oneline GOOD_SHA..BAD_SHA`
2. Scope to likely files first:
   - `git diff --name-only GOOD_SHA..BAD_SHA`
   - Prioritize `Containerfile`, `container/*`, `_jolo/container.py`, `_jolo/constants.py`, `_jolo/setup.py`.
3. Produce minimal suspect set:
   - `git log --oneline GOOD_SHA..BAD_SHA -- <critical files>`
4. Reproduce with deterministic probes on both ends:
   - Build tagged images for both commits.
   - Run same probes in each image/container.
   - Example probe set for tmux/ruby failures:
     - `ruby -e "require 'thor'"`
     - `tmuxinator version`
5. Report only evidence-backed culprit(s):
   - commit SHA(s)
   - why they correlate with failure
   - direct fix option: revert, cherry-pick, or patch
6. Add a guard so it cannot regress silently:
   - Add build/test smoke checks for the failing path.

## Rules

- Do not guess root cause before commit-range evidence.
- Keep probes identical across good/bad commits.
- Prefer the smallest fix plus a guard.
