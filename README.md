# cloud-automations

Run reusable Codex Cloud prompts from GitHub Actions.

## Setup

1. Create a Codex Cloud environment whose label matches each `owner/repository`, or set an explicit
   `environment` in `automations.yaml`.
2. Install Poetry and Python 3.13 for local validation.
3. Add the local Codex authentication document as an Actions secret:

   ```shell
   gh secret set CODEX_AUTH_JSON < ~/.codex/auth.json
   ```

Repositories created from this template must set their own secret.

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

`self` resolves to the current GitHub repository. Prompt and skill references such as `foo/bar` load
`prompts/foo/bar.md` and `skills/foo/bar.md`. Add `schedule.cron` and `schedule.timezone` for scheduled
runs; automations without a schedule remain manual-only.

## Usage

```shell
poetry install
poetry run ruff check .
poetry run pylint src tests linting/python-rules-lint/src linting/python-rules-lint/tests
poetry run cloud-automations validate
gh workflow run dispatch.yml -f automation=hello-world
```
