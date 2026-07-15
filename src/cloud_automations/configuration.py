import json
import re
import subprocess
from pathlib import Path
from typing import Final, Literal

import yaml
from pydantic import ValidationError
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from cloud_automations.errors import ConfigurationError
from cloud_automations.models.configuration import (
    REPOSITORY_PATTERN,
    AutomationsConfig,
    AutomationTarget,
    LoadedConfiguration,
)

GITHUB_ORIGIN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"github\.com(?::|/)([A-Za-z0-9._-]+/[A-Za-z0-9._-]+?)(?:\.git)?$"
)

type FragmentDirectory = Literal["prompts", "skills"]

__all__: Final[tuple[str, ...]] = (
    "AutomationTarget",
    "LoadedConfiguration",
    "find_target",
    "load_configuration",
    "read_fragment",
    "resolve_self_repository",
    "schema_text",
    "targets",
    "validate_yaml_keys",
    "validate_repository",
)


def read_fragment(root: Path, directory: FragmentDirectory, reference: str) -> str:
    """Read one validated Markdown instruction fragment."""

    repository_root = root.resolve()
    base = (root / directory).resolve()

    if not base.is_relative_to(repository_root):
        raise ConfigurationError(f"{directory} directory escapes the repository root")

    candidate = (base / f"{reference}.md").resolve()

    if not candidate.is_relative_to(base):
        raise ConfigurationError(f"{directory} reference escapes its directory: {reference}")

    if not candidate.is_file():
        raise ConfigurationError(f"missing or non-regular {directory} file: {reference}")

    try:
        content = candidate.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ConfigurationError(f"{directory} file is not UTF-8: {reference}") from error

    if not content.strip():
        raise ConfigurationError(f"{directory} file is empty: {reference}")

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


def load_configuration(path: Path) -> LoadedConfiguration:
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

    loaded = LoadedConfiguration(root=path.resolve().parent, config=config)

    for repository in config.repositories.values():
        for automation in repository.automations.values():
            read_fragment(loaded.root, "prompts", automation.prompt)
            for skill in automation.skills:
                read_fragment(loaded.root, "skills", skill)

    return loaded


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


def targets(loaded: LoadedConfiguration, self_repository: str) -> list[AutomationTarget]:
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

    target = next((item for item in targets(loaded, self_repository) if item.name == name), None)

    if target is None:
        raise ConfigurationError(f"unknown automation: {name}")

    return target


def schema_text() -> str:
    """Render the canonical JSON Schema."""

    return json.dumps(AutomationsConfig.model_json_schema(), indent=2, sort_keys=True) + "\n"


def validate_repository(config_path: Path, schema_path: Path) -> LoadedConfiguration:
    """Validate configuration resources and committed schema freshness."""

    loaded = load_configuration(config_path)

    try:
        committed_schema = schema_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ConfigurationError(f"unable to read {schema_path}: {error}") from error

    if committed_schema != schema_text():
        raise ConfigurationError(f"stale generated schema: {schema_path}")

    return loaded
