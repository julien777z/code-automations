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

## Dependency Installation

- Declare project dependencies used by workflows in the repository's dependency manifests and commit their lockfiles.
- Run project-level installation commands such as `poetry install` or `npm install` in workflows.
- Do not install individual project packages or embed their versions directly in workflow commands.

## README Titles

- Write the top-level heading in every `README.md` in title case.
- Convert slug-style project names into readable words, such as `example-service` becoming `Example Service`.
