# Code Automations

Validate and run repository-owned automations across one or more GitHub repositories.

## Features

- Repository-owned configuration, prompts, and skills
- Configuration validation before execution
- Manual and scheduled automation runs
- Multi-repository changes and pull request creation
- Docker-isolated execution
- Managed runtime dependencies

## Examples

### Configure Automations

Define projects, repositories, prompts, skills, and optional schedules in an automation configuration file.

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
        schedule:
          cron: "0 9 * * 1" # Every Monday at 09:00 UTC
          timezone: UTC
```

Prompt and skill references may include `.md` or omit it.

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
          skills-directory-path: skills
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
          skills-directory-path: skills
          run-automation: ${{ inputs.automation_name }}
          codex-auth-json: ${{ secrets.CODEX_AUTH_JSON }}
          github-token: ${{ secrets.AUTOMATION_GITHUB_TOKEN }}
```

## Inputs

| Input | Default | Purpose |
| --- | --- | --- |
| `automations-file-path` | Required | Locates the automation configuration in the checked-out repository. |
| `prompts-directory-path` | Required | Locates prompt Markdown files in the checked-out repository. |
| `skills-directory-path` | Required | Locates skill Markdown files in the checked-out repository. |
| `mode` | `dispatch` | Selects configuration validation or automation dispatch. |
| `run-automation` | `""` | Selects a manual automation; an empty value evaluates configured schedules. |
| `codex-auth-json` | `""` | Provides the authentication document required for dispatch. |
| `github-token` | `""` | Provides repository access required for dispatch. |

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
