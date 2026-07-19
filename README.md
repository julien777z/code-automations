# Code Automations

Run repository-owned, multi-repository automations from one reusable GitHub Action.

## Setup

Keep `automations.yaml` and the prompt and skill directories in the consumer repository. The included example
uses `examples/prompts/` and `examples/skills/`. Configure these Actions secrets for every consumer repository:

```shell
gh secret set CODEX_AUTH_JSON < ~/.codex/auth.json
gh secret set AUTOMATION_GITHUB_TOKEN
```

`AUTOMATION_GITHUB_TOKEN` must be a GitHub App installation token or fine-grained personal access token
with access to the consumer repository and every configured target repository. It needs contents and pull
request write permission. The standard `GITHUB_TOKEN` does not normally grant access to sibling repositories.

## Configuration

```yaml
version: 1
projects:
  example:
    repositories:
      self:
        branch: main
      owner/related-repository:
        branch: develop
    automations:
      hello-world:
        prompt: hello-world
        skills:
          - concise
```

Project keys are arbitrary. Repository mapping order defines the primary repository; each following repository
is writable by the same Codex session. `self` resolves to the repository running the workflow. A repository
branch defaults to `main`. Prompt and skill references omit `.md` and resolve independently against the directories
passed to the action. For example, `prompt: foo/bar` with `prompts-directory-path: examples/prompts` loads
`examples/prompts/foo/bar.md`. Add `schedule.cron` and `schedule.timezone` for scheduled runs; other automations
are manual-only.

Each run is a single attempt. It creates the same `automation/<name>/...` branch in every changed repository and
opens a separate pull request targeting each configured base branch. GitHub rejects an existing remote branch when
the workflow pushes it. Partial publication remains for manual cleanup after a failure.

Codex runs in a hardened Docker container with access only to the automation workspace and its authentication
directory. The GitHub token remains on the runner, where cloning and publication occur. GitHub-hosted Ubuntu
runners include Docker; self-hosted runners must provide a compatible Docker daemon.

## Validate Configuration

```yaml
name: Validate Automations

on:
  push:

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: owner/code-automations@v0
        with:
          mode: validate
          automations-file-path: automations.yaml
          prompts-directory-path: examples/prompts
          skills-directory-path: examples/skills
```

## Run Automations

```yaml
name: Run Automations

on:
  schedule:
    - cron: "17 * * * *"
  workflow_dispatch:
    inputs:
      run-automation:
        description: Globally unique automation name
        required: false
        type: string

concurrency:
  group: ${{ github.repository }}-automation-dispatcher
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  dispatch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          persist-credentials: false
      - uses: owner/code-automations@v0
        with:
          automations-file-path: automations.yaml
          prompts-directory-path: examples/prompts
          skills-directory-path: examples/skills
          run-automation: ${{ inputs.run-automation }}
          codex-auth-json: ${{ secrets.CODEX_AUTH_JSON }}
          github-token: ${{ secrets.AUTOMATION_GITHUB_TOKEN }}
```

An empty `run-automation` dispatches every due scheduled automation and persists successful occurrences on the
consumer repository's `automation-state` branch. Scheduled workflows require `contents: write` and a full
checkout. Do not run this authenticated workflow for pull-request events.

## Local Development

```shell
poetry install
poetry run pytest
poetry run ruff check .
poetry run ruff format --check .
poetry run code-automations \
  --prompts-directory examples/prompts \
  --skills-directory examples/skills \
  validate
```

## License

MIT
