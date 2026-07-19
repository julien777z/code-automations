import logging
from pathlib import Path
from typing import Final, Literal

import yaml
from pydantic import ValidationError
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from code_automations.errors import ConfigurationError
from code_automations.models.configuration import (
    AutomationsConfig,
    FragmentDirectories,
    LoadedConfiguration,
)
from code_automations.targets import has_self_repository, resolve_self_repository, resolve_targets

logger = logging.getLogger(__name__)

type FragmentType = Literal["prompt", "skill"]

__all__: Final[tuple[str, ...]] = (
    "load_configuration",
    "read_fragment",
    "validate_configuration",
)


def read_fragment(directory: Path, fragment_type: FragmentType, reference: str) -> str:
    """Read one validated Markdown instruction fragment."""

    base = directory.resolve()

    filename = reference if reference.endswith(".md") else f"{reference}.md"
    candidate = (base / filename).resolve()

    if not candidate.is_relative_to(base):
        raise ConfigurationError(f"{fragment_type} reference escapes its directory: {reference}")

    if not candidate.is_file():
        raise ConfigurationError(f"missing or non-regular {fragment_type} file: {reference}")

    try:
        content = candidate.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ConfigurationError(f"{fragment_type} file is not UTF-8: {reference}") from error

    if not content.strip():
        raise ConfigurationError(f"{fragment_type} file is empty: {reference}")

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


def load_configuration(path: Path, fragment_directories: FragmentDirectories) -> LoadedConfiguration:
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

    resolved_directories = FragmentDirectories(
        prompts=fragment_directories.prompts.resolve(),
        skills=fragment_directories.skills.resolve(),
    )

    for fragment_type, directory in (
        ("prompt", resolved_directories.prompts),
        ("skill", resolved_directories.skills),
    ):
        if not directory.is_dir():
            raise ConfigurationError(f"{fragment_type} directory does not exist: {directory}")

    loaded = LoadedConfiguration(
        root=path.resolve().parent,
        fragment_directories=resolved_directories,
        config=config,
    )

    for project in config.projects.values():
        for automation in project.automations.values():
            read_fragment(loaded.fragment_directories.prompts, "prompt", automation.prompt)
            for skill in automation.skills:
                read_fragment(loaded.fragment_directories.skills, "skill", skill)

    return loaded


def validate_configuration(
    config_path: Path,
    fragment_directories: FragmentDirectories,
    github_repository: str | None = None,
) -> None:
    """Validate one automation configuration and its referenced resources."""

    loaded = load_configuration(config_path, fragment_directories)
    self_repository = (
        resolve_self_repository(loaded.root, github_repository) if has_self_repository(loaded) else None
    )

    resolve_targets(loaded, self_repository)
