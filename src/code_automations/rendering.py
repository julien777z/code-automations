import logging
from pathlib import Path
from typing import Final

from code_automations.configuration import read_fragment
from code_automations.models.configuration import AutomationTarget, LoadedConfiguration
from code_automations.models.execution import RepositoryWorkspace

logger = logging.getLogger(__name__)

__all__: Final[tuple[str, ...]] = ("render_target",)


def render_target(
    loaded: LoadedConfiguration,
    target: AutomationTarget,
    repositories: list[RepositoryWorkspace] | None = None,
) -> str:
    """Render automation metadata, ordered skills, and prompt."""

    sections = [
        "# Automation metadata",
        "",
        f"- Name: {target.name}",
        f"- Project: {target.project}",
        "- Repositories:",
    ]

    paths = repositories or [
        RepositoryWorkspace(
            repository=repository.repository,
            branch=repository.branch,
            path=Path(repository.repository),
            starting_commit="unavailable",
        )
        for repository in target.repositories
    ]

    for repository in paths:
        sections.append(f"  - {repository.repository}: {repository.path} (base branch: {repository.branch})")

    sections.extend(
        [
            "",
            "# Execution contract",
            "",
            "Inspect every repository that is relevant to the task and modify only the repositories needed.",
            "Do not create commits, push branches, create pull requests, or modify automation configuration.",
            "Return the required structured result with PR metadata only for repositories that changed.",
        ]
    )

    for skill in target.automation.skills:
        sections.extend(
            [
                "",
                f"# Skill: {skill}",
                "",
                read_fragment(loaded.root, "skills", skill),
            ]
        )

    sections.extend(
        [
            "",
            "# Prompt",
            "",
            read_fragment(loaded.root, "prompts", target.automation.prompt),
        ]
    )

    return "\n".join(sections) + "\n"
