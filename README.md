# Code Automations

Validate and run repository-owned automations across one or more GitHub repositories.

## Features

- Repository-owned configuration, prompts, and skills
- Configuration validation before execution
- Manual and scheduled automation runs
- One coordinating Codex Cloud task across multiple repositories
- Agent-owned pull request creation and CI monitoring, with merging only when the task explicitly requests it
- Managed runtime dependencies

## Examples

### Configure Automations

Define projects, repositories, prompts, skills, and optional schedules in an automation configuration file.
This example runs `hello-world` every Monday at 09:00 UTC across the current repository and
`owner/related-repository`.

Skills are canonical Agent Skills under `.agents/skills/<name>/SKILL.md`. The Cloud environment
should run Agent Sync during setup and maintenance so each supported coding agent receives its
native skill layout.

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
          codex-environment-id: ${{ vars.CODEX_ENVIRONMENT_ID }}
          prompts-directory-path: prompts
          codex-auth-json: ${{ secrets.CODEX_AUTH_JSON }}
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
```

The Cloud environment must prepare each configured repository as a sibling directory named after
the repository, such as `../related-repository`. Configure Git and `gh` authentication inside that
environment when an automation should publish pull requests.

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
