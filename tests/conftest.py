from pathlib import Path

import pytest

from code_automations.configuration import load_configuration
from code_automations.models.configuration import LoadedConfiguration


@pytest.fixture
def prompts_directory(tmp_path: Path) -> Path:
    """Provide an independent prompt directory."""

    return tmp_path / "prompts"


@pytest.fixture
def automation_config_path(tmp_path: Path, prompts_directory: Path) -> Path:
    """Provide a valid automation configuration file."""

    prompt = prompts_directory / "hello-world.md"
    skill = tmp_path / ".agents/skills/example-skill/SKILL.md"
    prompt.parent.mkdir(parents=True)
    skill.parent.mkdir(parents=True)

    prompt.write_text("Say hello.\n", encoding="utf-8")
    skill.write_text(
        "---\nname: example-skill\ndescription: Keep automation output concise.\n---\n\nBe concise.\n",
        encoding="utf-8",
    )

    config_path = tmp_path / "automations.yaml"
    config_path.write_text(
        """version: 1
projects:
  example:
    repositories:
      self:
        branch: main
      owner/secondary:
        branch: develop
    automations:
      hello-world:
        prompt: hello-world
        skills:
          - example-skill
        model:
          name: gpt-5.6-terra
          reasoning_effort: high
        merge:
          workflows:
            - Run Tests
          method: squash
          timeout_minutes: 120
""",
        encoding="utf-8",
    )

    return config_path


@pytest.fixture
def scheduled_configuration(
    tmp_path: Path,
    prompts_directory: Path,
) -> LoadedConfiguration:
    """Provide a scheduled automation configuration."""

    prompt = prompts_directory / "task.md"
    prompt.parent.mkdir(parents=True)

    prompt.write_text("Run the task.\n", encoding="utf-8")

    config_path = tmp_path / "automations.yaml"
    config_path.write_text(
        """version: 1
projects:
  example:
    repositories:
      self: {}
    automations:
      scheduled:
        prompt: task
        schedule:
          cron: "0 * * * *"
          timezone: America/Los_Angeles
""",
        encoding="utf-8",
    )

    return load_configuration(config_path, prompts_directory)
