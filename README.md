# Code Automations

Validate and run repository-owned automations across one or more GitHub repositories.

## Features

- Repository-owned configuration, prompts, and skills
- Configuration validation before execution
- Manual and scheduled automation runs
- One persistent Codex Cloud task across multiple repositories
- Agent-owned pull request creation and CI monitoring, with merging only when the task explicitly requests it
- Managed runtime dependencies

## Examples

### Configure Automations

Define projects, repositories, prompts, skills, and optional schedules in an automation configuration file.
This example runs `hello-world` every Monday at 09:00 UTC across the current repository and
`owner/related-repository`.

Skills are canonical Agent Skills under `.agents/skills/<name>/SKILL.md`. The action uses Agent Sync
to make selected skills available through the agent's native skill layout.

```yaml
version: 1
model:
  name: gpt-5.6-sol
  reasoning_effort: medium
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
        model_override:
          reasoning_effort: high
        schedule:
          cron: "0 9 * * 1" # Every Monday at 09:00 UTC
          timezone: UTC
```

> Note: Prompt and skill references may include `.md` or omit it.
> The root model configuration applies to every automation and defaults to `gpt-5.6-sol` with
> `medium` reasoning. An automation may set `model_override` to replace either or both values.

### Validate Configuration

Validate the configuration and referenced Markdown files.

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
      - uses: julien777z/code-automations@v0
        with:
          mode: validate
          automations-file-path: automations.yaml
          prompts-directory-path: prompts
          codex-auth-json: ${{ secrets.CODEX_AUTH_JSON }}
          codex-environment-id: ${{ vars.CODEX_ENVIRONMENT_ID }}
```

### Run Automations

Run a selected automation manually or run configured automations on their schedules.

```yaml
name: Run Automations

on:
  schedule:
    - cron: "0 9 * * 1" # Every Monday at 09:00 UTC
  workflow_dispatch:
    inputs:
      automation_name:
        description: Automation name
        required: false
        type: string

permissions:
  contents: read

jobs:
  dispatch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - uses: julien777z/code-automations@v0
        with:
          automations-file-path: automations.yaml
          prompts-directory-path: prompts
          run-automation-name: ${{ inputs.automation_name }}
          codex-auth-json: ${{ secrets.CODEX_AUTH_JSON }}
          codex-environment-id: ${{ vars.CODEX_ENVIRONMENT_ID }}
          github-token: ${{ secrets.AUTOMATION_GITHUB_TOKEN }}
```

Create the coordinating environment once in the Codex Cloud UI and expose its identifier as
`CODEX_ENVIRONMENT_ID`. Its setup and maintenance commands should install this package and run
`prepare-workspace`; Codex does not expose a supported environment-management CLI or API. Add
`AUTOMATION_GITHUB_TOKEN` as a setup-only environment secret and grant it access only to configured
repositories.

The action submits one persistent task that can be opened and continued in Codex. It writes refreshed
Codex authentication back to `CODEX_AUTH_JSON` after every dispatch, so the GitHub token must also be
able to update Actions secrets in the consumer repository. Dispatch workflows must serialize runs to
prevent simultaneous refresh-token rotation.

## Modes

| Mode | Behavior |
| --- | --- |
| `validate` | Validates the automation configuration and referenced prompt and skill files. |
| `dispatch` | Runs `run-automation-name` when provided; otherwise runs automations scheduled for the current minute. Pull requests remain open unless the task prompt explicitly requests merging. |

## Inputs

| Input | Default | Purpose |
| --- | --- | --- |
| `automations-file-path` | Required | Locates the automation configuration in the checked-out repository. |
| `prompts-directory-path` | Required | Locates prompt Markdown files in the checked-out repository. |
| `mode` | `dispatch` | Selects the `validate` or `dispatch` behavior. |
| `run-automation-name` | `""` | Selects a manual automation; an empty value evaluates configured schedules. |
| `codex-auth-json` | Required | Provides the authentication document required for dispatch. |
| `codex-environment-id` | Required | Selects the coordinating Codex Cloud environment. |
| `github-token` | `${{ github.token }}` | Clones repositories and publishes automation branches and pull requests. |

## Cloud Environment Commands

Use the same commands for initial setup and cached-environment maintenance, changing the Git branch
only while testing an open producer pull request:

```shell
python -m pip install --upgrade "code-automations @ git+https://github.com/julien777z/code-automations.git@v0"
python -m code_automations \
  --config /workspace/code-automations/automations.yaml \
  --prompts-directory /workspace/code-automations/prompts \
  prepare-workspace --workspace /workspace
```

## Alpha Releases

Alpha releases use immutable `v0.0.N` tags. The moving `v0` tag points to the latest alpha. A
release may be tagged from the active WIP branch before its pull request is merged.

## Local Development

```shell
poetry install
poetry run pytest
poetry run ruff check .
poetry run ruff format --check .
poetry run python -m code_automations \
  --config example/automations.yaml \
  --prompts-directory example/prompts \
  validate
```

## License

MIT
