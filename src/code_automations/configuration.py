import logging
import re
import subprocess
from pathlib import Path
from typing import Final

import yaml
from agent_sync.errors import AgentSyncError
from agent_sync.skill import load_skills
from agent_sync.workspace import Workspace
from pydantic import ValidationError
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from code_automations.errors import ConfigurationError
from code_automations.models.configuration import (
    REPOSITORY_PATTERN,
    AutomationsConfig,
    AutomationTarget,
    LoadedConfiguration,
    ResolvedRepository,
)

logger = logging.getLogger(__name__)

GITHUB_ORIGIN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"github\.com(?::|/)([A-Za-z0-9._-]+/[A-Za-z0-9._-]+?)(?:\.git)?$"
)

__all__: Final[tuple[str, ...]] = (
    "find_target",
    "load_configuration",
    "read_prompt",
    "resolve_self_repository",
    "resolve_targets",
    "validate_configuration",
)


def read_prompt(directory: Path, reference: str) -> str:
    """Read one validated Markdown automation prompt."""

    base = directory.resolve()

    filename = reference if reference.endswith(".md") else f"{reference}.md"
    candidate = (base / filename).resolve()

    if not candidate.is_relative_to(base):
        raise ConfigurationError(f"prompt reference escapes its directory: {reference}")

    if not candidate.is_file():
        raise ConfigurationError(f"missing or non-regular prompt file: {reference}")

    try:
        content = candidate.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ConfigurationError(f"prompt file is not UTF-8: {reference}") from error

    if not content.strip():
        raise ConfigurationError(f"prompt file is empty: {reference}")

    return content.strip()


def validate_yaml_keys(node: Node | None, path: tuple[str, ...] = ()) -> None:
    """Reject duplicate YAML mapping keys before model validation."""

    if isinstance(node, MappingNode):
        mapping_keys: set[str] = set()

        for key_node, value_node in node.value:
            if isinstance(key_node, ScalarNode):
                key = key_node.value
                if key in mapping_keys:
                    location = ".".join((*path, key))

                    raise ConfigurationError(f"duplicate YAML key: {location}")

                mapping_keys.add(key)
                validate_yaml_keys(value_node, (*path, key))
            else:
                validate_yaml_keys(value_node, path)
    elif isinstance(node, SequenceNode):
        for value_node in node.value:
            validate_yaml_keys(value_node, path)


def load_configuration(path: Path, prompts_directory: Path) -> LoadedConfiguration:
    """Load and semantically validate an automation YAML file."""

    try:
        content = path.read_text(encoding="utf-8")
        validate_yaml_keys(yaml.compose(content))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise ConfigurationError(f"unable to parse {path}: {error}") from error

    try:
        config = AutomationsConfig.model_validate(yaml.safe_load(content))
    except ValidationError as error:
        raise ConfigurationError(str(error)) from error

    resolved_prompts_directory = prompts_directory.resolve()
    if not resolved_prompts_directory.is_dir():
        raise ConfigurationError(f"prompt directory does not exist: {resolved_prompts_directory}")

    root = path.resolve().parent

    try:
        skill_names = {skill.slug for skill in load_skills(Workspace(root=root))}
    except (AgentSyncError, OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError) as error:
        raise ConfigurationError(str(error)) from error

    loaded = LoadedConfiguration(
        root=root,
        prompts_directory=resolved_prompts_directory,
        config=config,
    )

    for project in config.projects.values():
        for automation in project.automations.values():
            read_prompt(loaded.prompts_directory, automation.prompt)
            for skill in automation.skills:
                if skill not in skill_names:
                    raise ConfigurationError(f"missing native skill: {skill}")

    return loaded


def resolve_self_repository(
    loaded: LoadedConfiguration,
    github_repository: str | None = None,
) -> str | None:
    """Resolve the reserved self repository when it is configured."""

    if not any("self" in project.repositories for project in loaded.config.projects.values()):
        return None

    if github_repository is not None:
        if not REPOSITORY_PATTERN.fullmatch(github_repository):
            raise ConfigurationError("GITHUB_REPOSITORY is not a valid owner/repository identifier")

        return github_repository

    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=loaded.root,
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


def resolve_targets(
    loaded: LoadedConfiguration,
    self_repository: str | None = None,
) -> list[AutomationTarget]:
    """Resolve every configured automation target."""

    automation_targets: list[AutomationTarget] = []

    for project_name, project in loaded.config.projects.items():
        repositories: list[ResolvedRepository] = []
        repository_names: set[str] = set()

        for repository_key, repository in project.repositories.items():
            if repository_key == "self" and self_repository is None:
                raise ConfigurationError("self requires GITHUB_REPOSITORY or a GitHub origin remote")

            repository_name = self_repository if repository_key == "self" else repository_key

            if repository_name is None:
                raise ConfigurationError("self requires a resolved repository")

            normalized_repository_name = repository_name.casefold()

            if normalized_repository_name in repository_names:
                raise ConfigurationError(f"duplicate resolved repository: {repository_name}")

            repository_names.add(normalized_repository_name)
            repositories.append(ResolvedRepository(repository=repository_name, branch=repository.branch))

        for name, automation in project.automations.items():
            automation_targets.append(
                AutomationTarget(
                    name=name,
                    project=project_name,
                    repositories=repositories,
                    automation=automation,
                )
            )

    return automation_targets


def find_target(
    loaded: LoadedConfiguration,
    self_repository: str | None,
    name: str,
) -> AutomationTarget:
    """Find an automation by its globally unique name."""

    target = next((item for item in resolve_targets(loaded, self_repository) if item.name == name), None)

    if target is None:
        raise ConfigurationError(f"unknown automation: {name}")

    return target


def validate_configuration(
    config_path: Path,
    prompts_directory: Path,
    github_repository: str | None = None,
) -> None:
    """Validate one automation configuration and its referenced resources."""

    loaded = load_configuration(config_path, prompts_directory)
    self_repository = resolve_self_repository(loaded, github_repository)

    resolve_targets(loaded, self_repository)
