from pathlib import Path

import pytest

from code_automations.configuration import load_configuration
from code_automations.models.configuration import FragmentDirectories, LoadedConfiguration


@pytest.fixture
def fragment_directories(tmp_path: Path) -> FragmentDirectories:
    """Provide independent prompt and skill directories."""

    return FragmentDirectories(
        prompts=tmp_path / "example/prompts",
        skills=tmp_path / "example/skills",
    )


@pytest.fixture
def automation_config_path(tmp_path: Path, fragment_directories: FragmentDirectories) -> Path:
    """Provide a valid automation configuration file."""

    prompt = fragment_directories.prompts / "hello-world.md"
    skill = fragment_directories.skills / "example-skill.md"
    prompt.parent.mkdir(parents=True)
    skill.parent.mkdir(parents=True)

    prompt.write_text("Say hello.\n", encoding="utf-8")
    skill.write_text("Be concise.\n", encoding="utf-8")

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
    fragment_directories: FragmentDirectories,
) -> LoadedConfiguration:
    """Provide a scheduled automation configuration."""

    prompt = fragment_directories.prompts / "task.md"
    fragment_directories.skills.mkdir(parents=True)
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

    return load_configuration(config_path, fragment_directories)
