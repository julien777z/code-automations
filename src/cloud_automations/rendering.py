from typing import Final

from cloud_automations.configuration import AutomationTarget, LoadedConfiguration, read_fragment

__all__: Final[tuple[str, ...]] = ("render_target",)


def render_target(loaded: LoadedConfiguration, target: AutomationTarget) -> str:
    """Render automation metadata, ordered skills, and prompt."""
    sections = [
        "# Automation metadata",
        "",
        f"- Name: {target.name}",
        f"- Repository: {target.repository}",
        f"- Branch: {target.branch}",
        f"- Environment: {target.environment}",
        f"- Attempts: {target.automation.attempts}",
    ]

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
