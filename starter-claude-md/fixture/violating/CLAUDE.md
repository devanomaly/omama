# CLAUDE.md — violation fixture (planted, do not copy)

## Where to put it

This file exists only for the checker's fixture to exercise the two kinds of
violation. It is not an example of real content.

## Code conventions

- Rule with a tag outside the closed set. [99]

- When creating a new file, keep it under 500 lines. [07]
- Pilar P7 requires every rule to have a failure-map before it becomes a team habit.

## Bugfix requires a work order

- Before implementing a production bugfix, request the task's
  `work-order.yaml`. [02]

## Hooks installed in this repo

- This repo has a privacy `pre-commit` hook. If it blocks a commit, review the
  staged content instead of bypassing it. [01]
