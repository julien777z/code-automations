import logging
from typing import Final

from code_automations.configuration import read_prompt
from code_automations.models.configuration import AutomationTarget, LoadedConfiguration

logger = logging.getLogger(__name__)

__all__: Final[tuple[str, ...]] = ("render_target",)


def render_target(
    loaded: LoadedConfiguration,
    target: AutomationTarget,
) -> str:
    """Render one self-publishing Cloud automation prompt."""

    sections = [
        "# Automation metadata",
        "",
        f"- Name: {target.name}",
        f"- Project: {target.project}",
        "- Repositories:",
    ]

    for repository in target.repositories:
        directory = repository.repository.rsplit("/", maxsplit=1)[1]
        sections.append(f"  - {repository.repository}: ../{directory} (base branch: {repository.branch})")

    sections.extend(
        [
            "",
            "# Execution contract",
            "",
            "Work directly in the prepared repository paths above.",
            "Do not modify the automation repository that launched this task.",
            "Git and GitHub CLI authentication are already configured for the authorized repositories.",
            "Never display, copy, or persist authentication credentials in repository content or logs.",
            "Inspect every configured repository and modify only repositories that need "
            "the requested change.",
            f"Use the branch automation/{target.name} in each changed repository.",
            "Reuse its open pull request when one exists and its history belongs to this automation.",
            "Create the branch from the configured base branch when no safe automation branch exists.",
            "Never force-push or overwrite unrelated branch history.",
            "Run the repository-native checks relevant to the changes before publication.",
        ]
    )

    if target.automation.skills:
        sections.extend(
            [
                "",
                "# Required skills",
                "",
                "Use these repository-native skills for this task:",
            ]
        )
        sections.extend(f"- `{skill}`" for skill in target.automation.skills)

    sections.extend(
        [
            "",
            "# Prompt",
            "",
            read_prompt(loaded.prompts_directory, target.automation.prompt),
            "",
            "# Publication contract",
            "",
            "For each changed repository, commit the complete change, push the automation branch, "
            "and open or update one pull request.",
            "Use a concise conventional-commit title and explain the dependency changes "
            "and validation in the body.",
            "Skip publication for repositories with no changes.",
            "Treat each repository independently so one repository failure does not block "
            "a successful repository.",
            "",
            "# System policy",
            "",
            "Do not merge any pull request unless the user explicitly asks you to merge it "
            "in the task prompt above.",
        ]
    )

    return "\n".join(sections) + "\n"
