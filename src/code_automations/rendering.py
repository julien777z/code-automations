import logging
from importlib.resources import files
from pathlib import Path
from string import Template
from typing import Final

from code_automations.configuration import read_prompt
from code_automations.models.configuration import AutomationTarget, LoadedConfiguration
from code_automations.models.runtime import PreparedRepository

logger = logging.getLogger(__name__)

TASK_PROMPT_PATH: Final[str] = "prompts/task.md"

__all__: Final[tuple[str, ...]] = ("render_target",)


def render_target(
    loaded: LoadedConfiguration,
    target: AutomationTarget,
    repositories: list[PreparedRepository] | None = None,
) -> str:
    """Render one self-publishing automation task."""

    prepared_repositories = repositories or [
        PreparedRepository(
            repository=repository.repository,
            branch=repository.branch,
            path=Path("/workspace/repositories") / str(index),
        )
        for index, repository in enumerate(target.repositories)
    ]
    repository_lines = "\n".join(
        f"  - {repository.repository}: {repository.path} (base branch: {repository.branch})"
        for repository in prepared_repositories
    )
    template = Template(files("code_automations").joinpath(TASK_PROMPT_PATH).read_text(encoding="utf-8"))

    return (
        template.substitute(
            automation_name=target.name,
            project_name=target.project,
            repositories=repository_lines,
            automation_branch=f"automation/{target.name}",
            prompt=read_prompt(loaded.prompts_directory, target.automation.prompt),
        ).rstrip()
        + "\n"
    )
