# Cloud Automations

Validate and dispatch repository-owned Codex Cloud automations with one reusable GitHub Action.

## Consumer Setup

Keep `automations.yaml`, `prompts/`, and `skills/` in the consumer repository. Add the Codex
authentication document as an Actions secret:

```shell
gh secret set CODEX_AUTH_JSON < ~/.codex/auth.json
```

Create a Codex Cloud environment whose label matches each configured `owner/repository`, or set an
explicit `environment` in `automations.yaml`.

## Configuration

```yaml
version: 1
repositories:
  self:
    branch: main
    automations:
      hello-world:
        prompt: examples/hello-world
        skills:
          - examples/concise
```

`self` resolves to the repository running the workflow. Prompt and skill references such as
`foo/bar` load `prompts/foo/bar.md` and `skills/foo/bar.md` relative to the configuration file. Add
`schedule.cron` and `schedule.timezone` for scheduled runs; automations without a schedule remain
manual-only. The canonical schema is available in
[`automations.schema.json`](automations.schema.json).

## Validate Configuration

```yaml
name: Validate Automations

on:
  push:
    paths:
      - automations.yaml
      - "prompts/**"
      - "skills/**"

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
          config-path: automations.yaml
```

Consumers do not copy the Python package, Node dependencies, tests, or generated schema. Validation
uses the models shipped with the selected action version.

## Dispatch Automations

```yaml
name: Dispatch Automations

on:
  schedule:
    - cron: "17 * * * *"
  workflow_dispatch:
    inputs:
      automation:
        description: Globally unique automation name
        required: true
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
      - uses: julien777z/code-automations@v0
        with:
          config-path: automations.yaml
          automation: ${{ inputs.automation }}
          codex-auth-json: ${{ secrets.CODEX_AUTH_JSON }}
```

An empty `automation` input dispatches every due scheduled automation and persists successful
occurrences on the consumer repository's `automation-state` branch. Scheduled workflows therefore
need `contents: write` and a full checkout. Manual-only workflows may use `contents: read`.

The action validates configuration before every dispatch, installs its own Python and Node
dependencies, stores Codex authentication in a permission-restricted temporary `CODEX_HOME`, and
links submitted tasks in the GitHub Actions job summary.

## Inputs

- `config-path` — configuration path relative to the checked-out consumer repository; defaults to
  `automations.yaml`.
- `mode` — `dispatch` by default, or `validate` for configuration-only checks.
- `automation` — globally unique automation name for manual dispatch; empty dispatches scheduled
  automations.
- `codex-auth-json` — complete Codex `auth.json`; required for dispatch and unused for validation.

## Versioning

Use the moving major tag to receive compatible fixes:

```yaml
- uses: julien777z/code-automations@v0
```

## Local Development

```shell
poetry install
npm ci
poetry run pytest
poetry run ruff check .
poetry run ruff format --check .
poetry run cloud-automations validate
```

## License

MIT
