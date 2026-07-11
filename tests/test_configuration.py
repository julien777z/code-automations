from pathlib import Path
from typing import Final

import pytest

from cloud_automations.configuration import (
    find_target,
    load_configuration,
    read_fragment,
    schema_text,
    validate_repository,
)
from cloud_automations.errors import ConfigurationError
from cloud_automations.rendering import render_target

VALID_CONFIG: Final[str] = """version: 1
repositories:
  self:
    branch: main
    automations:
      hello-world:
        prompt: examples/hello-world
        skills:
          - examples/concise
"""


def write_valid_repository(root: Path) -> Path:
    """Create a minimal valid automation repository."""
    prompt = root / "prompts/examples/hello-world.md"
    skill = root / "skills/examples/concise.md"
    prompt.parent.mkdir(parents=True)
    skill.parent.mkdir(parents=True)
    prompt.write_text("Say hello.\n", encoding="utf-8")
    skill.write_text("Be concise.\n", encoding="utf-8")
    config = root / "automations.yaml"
    config.write_text(VALID_CONFIG, encoding="utf-8")
    return config


def test_valid_nested_configuration_renders_deterministically(tmp_path: Path) -> None:
    """Resolve nested fragments and preserve rendering order."""
    config_path = write_valid_repository(tmp_path)
    loaded = load_configuration(config_path)
    target = find_target(loaded, "owner/repository", "hello-world")

    first = render_target(loaded, target)
    second = render_target(loaded, target)

    assert first == second
    assert first.index("# Automation metadata") < first.index("# Skill: examples/concise")
    assert first.index("# Skill: examples/concise") < first.index("# Prompt")
    assert "- Repository: owner/repository" in first


def test_explicit_repository_and_optional_fields_are_supported(tmp_path: Path) -> None:
    """Load an explicit repository with environment, branch, attempts, and schedule fields."""
    config_path = write_valid_repository(tmp_path)
    config_path.write_text(
        VALID_CONFIG.replace("self:", "owner/repository:")
        .replace("branch: main", "environment: Build Runner\n    branch: release/next")
        .replace(
            "prompt: examples/hello-world",
            "prompt: examples/hello-world\n"
            "        attempts: 4\n"
            "        schedule:\n"
            "          cron: '17 * * * *'\n"
            "          timezone: America/Los_Angeles",
        ),
        encoding="utf-8",
    )

    loaded = load_configuration(config_path)
    target = find_target(loaded, "unused/self", "hello-world")

    assert target.repository == "owner/repository"
    assert target.environment == "Build Runner"
    assert target.branch == "release/next"
    assert target.automation.attempts == 4


def test_missing_fragment_is_rejected(tmp_path: Path) -> None:
    """Reject a missing prompt or skill file."""
    config_path = write_valid_repository(tmp_path)
    (tmp_path / "skills/examples/concise.md").unlink()

    with pytest.raises(ConfigurationError, match="missing or non-regular"):
        load_configuration(config_path)


@pytest.mark.parametrize(
    "reference",
    ["../secret", "foo/../secret", "/secret", "foo\\bar", "foo/bar.md", "foo//bar"],
)
def test_unsafe_references_are_rejected(tmp_path: Path, reference: str) -> None:
    """Reject traversal, absolute, backslash, suffix, and empty path segments."""
    config_path = write_valid_repository(tmp_path)
    config_path.write_text(VALID_CONFIG.replace("examples/hello-world", reference), encoding="utf-8")

    with pytest.raises(ConfigurationError):
        load_configuration(config_path)


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    """Reject a reference whose symlink resolves outside its fragment directory."""
    config_path = write_valid_repository(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("External.\n", encoding="utf-8")
    link = tmp_path / "prompts/examples/link.md"
    link.symlink_to(outside)
    config_path.write_text(VALID_CONFIG.replace("examples/hello-world", "examples/link"), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="escapes"):
        load_configuration(config_path)


def test_fragment_directory_symlink_escape_is_rejected(tmp_path: Path) -> None:
    """Reject a prompt directory that resolves outside the repository root."""
    config_path = write_valid_repository(tmp_path)
    external = tmp_path.parent / f"{tmp_path.name}-external"
    external_examples = external / "examples"
    external_examples.mkdir(parents=True)
    (external_examples / "hello-world.md").write_text("External.\n", encoding="utf-8")
    prompt = tmp_path / "prompts/examples/hello-world.md"
    prompt.unlink()
    prompt.parent.rmdir()
    (tmp_path / "prompts").rmdir()
    (tmp_path / "prompts").symlink_to(external, target_is_directory=True)

    with pytest.raises(ConfigurationError, match="directory escapes"):
        load_configuration(config_path)


def test_non_utf8_empty_and_non_regular_fragments_are_rejected(tmp_path: Path) -> None:
    """Reject invalid fragment content and file types."""
    directory = tmp_path / "prompts"
    directory.mkdir()
    invalid = directory / "invalid.md"
    invalid.write_bytes(b"\xff")
    with pytest.raises(ConfigurationError, match="not UTF-8"):
        read_fragment(tmp_path, "prompts", "invalid")
    invalid.write_text("  \n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="empty"):
        read_fragment(tmp_path, "prompts", "invalid")
    invalid.unlink()
    invalid.mkdir()
    with pytest.raises(ConfigurationError, match="non-regular"):
        read_fragment(tmp_path, "prompts", "invalid")


def test_malformed_yaml_is_rejected(tmp_path: Path) -> None:
    """Reject malformed YAML."""
    config = tmp_path / "automations.yaml"
    config.write_text("repositories: [\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="unable to parse"):
        load_configuration(config)


def test_unknown_fields_are_rejected(tmp_path: Path) -> None:
    """Reject fields outside the strict schema."""
    config_path = write_valid_repository(tmp_path)
    config_path.write_text(
        VALID_CONFIG.replace("    branch", "    unexpected: true\n    branch"), encoding="utf-8"
    )

    with pytest.raises(ConfigurationError, match="extra_forbidden"):
        load_configuration(config_path)


def test_duplicate_global_names_are_rejected(tmp_path: Path) -> None:
    """Reject automation names repeated across repositories."""
    config_path = write_valid_repository(tmp_path)
    duplicate = (
        VALID_CONFIG
        + """  owner/other:
    automations:
      hello-world:
        prompt: examples/hello-world
"""
    )
    config_path.write_text(duplicate, encoding="utf-8")

    with pytest.raises(ConfigurationError, match="duplicate automation name"):
        load_configuration(config_path)


def test_duplicate_yaml_mapping_keys_are_rejected(tmp_path: Path) -> None:
    """Reject keys that PyYAML would otherwise silently overwrite."""
    config_path = write_valid_repository(tmp_path)
    config_path.write_text(
        """version: 1
repositories:
  self:
    automations:
      hello-world:
        prompt: examples/hello-world
      hello-world:
        prompt: examples/hello-world
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="duplicate YAML key"):
        load_configuration(config_path)


@pytest.mark.parametrize(
    "old,new",
    [
        ("self:", "invalid:"),
        ("self:", "owner_name/repository:"),
        ("self:", "owner.name/repository:"),
        ("self:", "owner-/repository:"),
        ("self:", "owner--name/repository:"),
        ("branch: main", "branch: bad branch"),
        ("branch: main", "branch: foo/.hidden"),
        ("branch: main", "branch: foo.lock/bar"),
        ("branch: main", "environment: ' bad environment'\n    branch: main"),
        ("prompt: examples/hello-world", "attempts: 5\n        prompt: examples/hello-world"),
        (
            "prompt: examples/hello-world",
            "schedule:\n"
            "          cron: invalid\n"
            "          timezone: UTC\n"
            "        prompt: examples/hello-world",
        ),
        (
            "prompt: examples/hello-world",
            "schedule:\n"
            "          cron: '0 9 * * *'\n"
            "          timezone: Mars/Base\n"
            "        prompt: examples/hello-world",
        ),
    ],
)
def test_invalid_semantic_values_are_rejected(tmp_path: Path, old: str, new: str) -> None:
    """Reject invalid repository, branch, environment, attempts, cron, and timezone values."""
    config_path = write_valid_repository(tmp_path)
    config_path.write_text(VALID_CONFIG.replace(old, new), encoding="utf-8")

    with pytest.raises(ConfigurationError):
        load_configuration(config_path)


@pytest.mark.parametrize("cron", ["0 0 L * *", "0 0 ? * *", "0 0 * * 5#3", "*/61 * * * *"])
def test_croniter_extensions_are_rejected(tmp_path: Path, cron: str) -> None:
    """Reject non-POSIX cron extensions accepted by croniter."""
    config_path = write_valid_repository(tmp_path)
    config_path.write_text(
        VALID_CONFIG.replace(
            "prompt: examples/hello-world",
            "schedule:\n"
            f"          cron: '{cron}'\n"
            "          timezone: UTC\n"
            "        prompt: examples/hello-world",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError):
        load_configuration(config_path)


def test_stale_schema_is_rejected(tmp_path: Path) -> None:
    """Reject a committed schema that differs from the generated model schema."""
    config_path = write_valid_repository(tmp_path)
    schema_path = tmp_path / "automations.schema.json"
    schema_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="stale generated schema"):
        validate_repository(config_path, schema_path)

    schema_path.write_text(schema_text(), encoding="utf-8")
    assert validate_repository(config_path, schema_path).config.version == 1
