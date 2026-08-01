import logging
from importlib.resources import files
from string import Template
from typing import Final

from code_automations.configuration import read_prompt
from code_automations.models.configuration import AutomationTarget, LoadedConfiguration

logger = logging.getLogger(__name__)

GLOBAL_PROMPT_PATH: Final[str] = "prompts/global.md"

__all__: Final[tuple[str, ...]] = ("render_target",)


def render_target(
    loaded: LoadedConfiguration,
    target: AutomationTarget,
) -> str:
    """Render one self-publishing Cloud automation prompt."""

    repositories = "\n".join(
        f"  - {repository.repository}: ../{repository.repository.rsplit('/', maxsplit=1)[-1]} "
        f"(base branch: {repository.branch})"
        for repository in target.repositories
    )
    skills = "\n".join(f"- `{skill}`" for skill in target.automation.skills)
    template = Template(files("code_automations").joinpath(GLOBAL_PROMPT_PATH).read_text(encoding="utf-8"))

    return (
        template.substitute(
            automation_name=target.name,
            project_name=target.project,
            repositories=repositories,
            automation_branch=f"automation/{target.name}",
            skills=skills,
            prompt=read_prompt(loaded.prompts_directory, target.automation.prompt),
        ).rstrip()
        + "\n"
    )
