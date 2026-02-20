---
name: feature-workflow
description: "Structured workflow for feature-sized or risky changes: short intake questions, create a branch, use TDD where applicable, commit frequently, get an external agent review, fix issues, then get a second external review and optionally open a PR. Use when the user says a task is big, multi-step, high-risk, or explicitly wants TDD, frequent commits, or multi-agent review."
---

# Feature Workflow

## Overview

Use this skill to handle large changes safely: a quick intake to clarify ambiguity, then branch isolation, test-driven iterations, frequent commits, and two external reviews before merge or PR.

## Intake (Ask First If Ambiguous)

Ask 2–4 short questions if the task has unclear scope or risk.

- What outcome defines “done”?
- Any files/areas to avoid or prioritize?
- Expected tests or constraints?
- Any deadline or review expectations?

## Workflow

1. Create a feature branch named for the task
1. If feasible, start with a failing test (TDD)
1. Implement in small increments and commit often
1. Run pragmatic tests before each review
1. Get a first external agent review (focus on correctness). Ask for the highest reasoning model
1. Apply fixes and commit
1. Get a second external agent review - again, ask for the highest reasoning model
1. Apply fixes, commit, and optionally open a PR

## Branching

- Create a branch from `main` (or the user’s target base).
- Keep history linear on the branch; rebase onto base before merge.

## TDD Guidance

- Prefer small testable slices.
- If TDD is impractical (e.g., infra or docs), explain why and proceed with targeted checks.

## Commit Discipline

- Commit after each coherent slice of work.
- Use clear, descriptive messages (e.g., `feat: add sync hooks`, `fix: handle dangling symlink`).

## Reviews

- Review 1: External agent, correctness-focused.
- Fix issues, commit.
- Review 2: External agent, correctness-focused.
- Fix issues, commit.

## Optional PR

- If the user wants a PR: open a draft PR after the second review is clean.
- Include summary, test results, and any remaining risks.

## Notes

- Use the `review` skill for external agent reviews when available.
- Keep each review prompt terse and focused on bugs/regressions.
