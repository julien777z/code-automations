# Code Automations

Run repository-owned, multi-repository automations from one reusable GitHub Action.

## Features

- Consumer-owned automation configuration, prompts, and skills
- Configuration validation, manual runs, and scheduled runs
- Multi-repository changes and pull request creation
- Isolated automation execution in Docker
- Shared runtime and dependency management

## Setup

Keep the automation configuration and its prompt and skill directories in the consumer repository. The included
example uses `example/automations.yaml`, `example/prompts/`, and `example/skills/`. Configure the GitHub token
secret for every consumer repository:

```shell
gh secret set AUTOMATION_GITHUB_TOKEN
```

`AUTOMATION_GITHUB_TOKEN` must be a GitHub App installation token or fine-grained personal access token
with access to the consumer repository and every configured target repository. It needs contents and pull
request write permission.

## Example

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
          - example-skill
```

Prompt and skill references may include `.md` or omit it.

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
          automations-file-path: example/automations.yaml
          prompts-directory-path: example/prompts
          skills-directory-path: example/skills
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
          automations-file-path: example/automations.yaml
          prompts-directory-path: example/prompts
          skills-directory-path: example/skills
          run-automation: ${{ inputs.run-automation }}
          github-token: ${{ secrets.AUTOMATION_GITHUB_TOKEN }}
```

An empty `run-automation` dispatches every due scheduled automation and preserves successful scheduling state.

## Local Development

```shell
poetry install
poetry run pytest
poetry run ruff check .
poetry run ruff format --check .
poetry run code-automations \
  --config example/automations.yaml \
  --prompts-directory example/prompts \
  --skills-directory example/skills \
  validate
```

## License

MIT
