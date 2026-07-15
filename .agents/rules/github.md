---
description: Do not manually specify options like python-version in workflows; use shared action defaults unless an edge case requires otherwise.
alwaysApply: true
---

# GitHub Rules

## Branch Safety

- Never commit or push agent-authored changes directly to the repository's default branch. If the current branch is the default branch or HEAD is detached, create a new descriptive non-default branch before editing; otherwise retain the existing non-default branch. Deliver changes through that branch and a pull request.

## Configuration Options

- Do not manually specify options like `python-version` in workflows.
- Use the defaults from shared actions or reusable workflows unless there is a specific edge case requiring a different version.
- If an edge case requires a specific version, add a comment explaining why.

## Action Versions

- Use version-tagged GitHub Actions such as `actions/checkout@v4` and `actions/setup-python@v5`.
- Do not pin actions to full commit SHAs.

## Branch Continuity

- When the user assigns additional work while the current checkout is on a non-default branch, treat it as a continuation: retain that branch and add the work to its pull request.
- Before creating a pull request, query the current branch's existing pull request. Reuse it when it is open; if none exists, create one from the current branch rather than splitting the work.
- Do not create a separate branch or pull request merely because the additional task differs or could be reviewed independently. Do so only when the user explicitly asks, or when the current branch represents an already-merged pull request; in the latter case, start the new work from the default branch.
