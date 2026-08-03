import logging
from importlib.resources import files
from pathlib import Path
from string import Template
from typing import Final

from code_automations.configuration import read_prompt
from code_automations.models.configuration import AutomationTarget, LoadedConfiguration
from code_automations.models.runtime import PreparedRepository
from code_automations.workspace import repository_path

logger = logging.getLogger(__name__)

TASK_PROMPT_PATH: Final[str] = "prompts/task.md"
GLOBAL_RULE_PATH: Final[str] = "prompts/global.md"

__all__: Final[tuple[str, ...]] = ("render_target",)


def render_target(
    loaded: LoadedConfiguration,
    target: AutomationTarget,
    workspace_root: Path,
    self_repository: str | None,
) -> str:
    """Render one self-publishing Cloud automation prompt."""

    prepared_repositories = [
        PreparedRepository(
            repository=repository.repository,
            branch=repository.branch,
            path=(
                loaded.root
                if self_repository is not None
                and repository.repository.casefold() == self_repository.casefold()
                else repository_path(workspace_root, repository.repository)
            ),
        )
        for repository in target.repositories
    ]
    repository_lines = "\n".join(
        f"  - {repository.repository}: {repository.path} (base branch: {repository.branch})"
        for repository in prepared_repositories
    )
    skills = "\n".join(f"  - {skill}" for skill in target.automation.skills) or "  - None"
    task_template = Template(files("code_automations").joinpath(TASK_PROMPT_PATH).read_text(encoding="utf-8"))
    global_rule = files("code_automations").joinpath(GLOBAL_RULE_PATH).read_text(encoding="utf-8")

    return (
        global_rule.rstrip()
        + "\n\n"
        + task_template.substitute(
            automation_name=target.name,
            project_name=target.project,
            repositories=repository_lines,
            automation_branch=f"automation/{target.name}",
            skills=skills,
            prompt=read_prompt(loaded.prompts_directory, target.automation.prompt),
        ).rstrip()
        + "\n"
    )
