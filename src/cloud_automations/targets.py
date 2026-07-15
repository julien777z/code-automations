import re
import subprocess
from pathlib import Path
from typing import Final

from cloud_automations.errors import ConfigurationError
from cloud_automations.models.configuration import (
    REPOSITORY_PATTERN,
    AutomationTarget,
    LoadedConfiguration,
)

GITHUB_ORIGIN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"github\.com(?::|/)([A-Za-z0-9._-]+/[A-Za-z0-9._-]+?)(?:\.git)?$"
)

__all__: Final[tuple[str, ...]] = ("find_target", "resolve_self_repository", "resolve_targets")


def resolve_self_repository(root: Path, github_repository: str | None = None) -> str:
    """Resolve the reserved self repository identifier."""

    if github_repository is not None:
        if not REPOSITORY_PATTERN.fullmatch(github_repository):
            raise ConfigurationError("GITHUB_REPOSITORY is not a valid owner/repository identifier")

        return github_repository

    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise ConfigurationError("self requires GITHUB_REPOSITORY or a GitHub origin remote")

    match = GITHUB_ORIGIN_PATTERN.search(result.stdout.strip())

    if match is None or not REPOSITORY_PATTERN.fullmatch(match.group(1)):
        raise ConfigurationError("origin is not a supported GitHub repository URL")

    return match.group(1)


def resolve_targets(loaded: LoadedConfiguration, self_repository: str) -> list[AutomationTarget]:
    """Resolve all configured automation targets."""

    automation_targets: list[AutomationTarget] = []

    for repository_key, repository in loaded.config.repositories.items():
        repository_name = self_repository if repository_key == "self" else repository_key
        environment = repository.environment or repository_name

        for name, automation in repository.automations.items():
            automation_targets.append(
                AutomationTarget(
                    name=name,
                    repository=repository_name,
                    environment=environment,
                    branch=repository.branch,
                    automation=automation,
                )
            )

    return automation_targets


def find_target(loaded: LoadedConfiguration, self_repository: str, name: str) -> AutomationTarget:
    """Find an automation by its globally unique name."""

    target = next((item for item in resolve_targets(loaded, self_repository) if item.name == name), None)

    if target is None:
        raise ConfigurationError(f"unknown automation: {name}")

    return target
