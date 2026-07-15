from pathlib import Path

import pytest

from cloud_automations.configuration import load_configuration
from cloud_automations.models.configuration import LoadedConfiguration


@pytest.fixture
def automation_config_path(tmp_path: Path) -> Path:
    """Provide a valid automation configuration file."""

    prompt = tmp_path / "prompts/examples/hello-world.md"
    skill = tmp_path / "skills/examples/concise.md"
    prompt.parent.mkdir(parents=True)
    skill.parent.mkdir(parents=True)

    prompt.write_text("Say hello.\n", encoding="utf-8")
    skill.write_text("Be concise.\n", encoding="utf-8")

    config_path = tmp_path / "automations.yaml"
    config_path.write_text(
        """version: 1
repositories:
  self:
    branch: main
    automations:
      hello-world:
        prompt: examples/hello-world
        skills:
          - examples/concise
""",
        encoding="utf-8",
    )

    return config_path


@pytest.fixture
def scheduled_configuration(tmp_path: Path) -> LoadedConfiguration:
    """Provide a scheduled automation configuration."""

    prompt = tmp_path / "prompts/examples/task.md"
    prompt.parent.mkdir(parents=True)

    prompt.write_text("Run the task.\n", encoding="utf-8")

    config_path = tmp_path / "automations.yaml"
    config_path.write_text(
        """version: 1
repositories:
  self:
    automations:
      scheduled:
        prompt: examples/task
        schedule:
          cron: "0 * * * *"
          timezone: America/Los_Angeles
""",
        encoding="utf-8",
    )

    return load_configuration(config_path)
