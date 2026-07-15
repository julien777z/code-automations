from pathlib import Path

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


class TestConfiguration:
    """Test automation configuration loading and validation."""

    def test_valid_nested_configuration_renders_deterministically(self, automation_config_path: Path) -> None:
        """Resolve nested fragments and preserve rendering order."""
        loaded = load_configuration(automation_config_path)
        target = find_target(loaded, "owner/repository", "hello-world")

        first = render_target(loaded, target)
        second = render_target(loaded, target)

        assert first == second
        assert first.index("# Automation metadata") < first.index("# Skill: examples/concise")
        assert first.index("# Skill: examples/concise") < first.index("# Prompt")
        assert "- Repository: owner/repository" in first

    def test_explicit_repository_and_optional_fields_are_supported(
        self, automation_config_path: Path
    ) -> None:
        """Load an explicit repository with environment, branch, attempts, and schedule fields."""
        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace("self:", "owner/repository:")
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

        loaded = load_configuration(automation_config_path)
        target = find_target(loaded, "unused/self", "hello-world")

        assert target.repository == "owner/repository"
        assert target.environment == "Build Runner"
        assert target.branch == "release/next"
        assert target.automation.attempts == 4

    def test_missing_fragment_is_rejected(self, automation_config_path: Path) -> None:
        """Reject a missing prompt or skill file."""
        (automation_config_path.parent / "skills/examples/concise.md").unlink()

        with pytest.raises(ConfigurationError, match="missing or non-regular"):
            load_configuration(automation_config_path)

    @pytest.mark.parametrize(
        "reference",
        ["../secret", "foo/../secret", "/secret", "foo\\bar", "foo/bar.md", "foo//bar"],
    )
    def test_unsafe_references_are_rejected(self, automation_config_path: Path, reference: str) -> None:
        """Reject traversal, absolute, backslash, suffix, and empty path segments."""
        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace("examples/hello-world", reference),
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError):
            load_configuration(automation_config_path)

    def test_symlink_escape_is_rejected(self, automation_config_path: Path) -> None:
        """Reject a reference whose symlink resolves outside its fragment directory."""
        root = automation_config_path.parent
        outside = root / "outside.md"
        outside.write_text("External.\n", encoding="utf-8")
        link = root / "prompts/examples/link.md"
        link.symlink_to(outside)

        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace("examples/hello-world", "examples/link"),
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError, match="escapes"):
            load_configuration(automation_config_path)

    def test_fragment_directory_symlink_escape_is_rejected(self, automation_config_path: Path) -> None:
        """Reject a prompt directory that resolves outside the repository root."""
        root = automation_config_path.parent
        external = root.parent / f"{root.name}-external"
        external_examples = external / "examples"
        external_examples.mkdir(parents=True)
        (external_examples / "hello-world.md").write_text("External.\n", encoding="utf-8")

        prompt = root / "prompts/examples/hello-world.md"
        prompt.unlink()
        prompt.parent.rmdir()
        (root / "prompts").rmdir()
        (root / "prompts").symlink_to(external, target_is_directory=True)

        with pytest.raises(ConfigurationError, match="directory escapes"):
            load_configuration(automation_config_path)

    def test_non_utf8_empty_and_non_regular_fragments_are_rejected(self, tmp_path: Path) -> None:
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

    def test_malformed_yaml_is_rejected(self, tmp_path: Path) -> None:
        """Reject malformed YAML."""
        config_path = tmp_path / "automations.yaml"
        config_path.write_text("repositories: [\n", encoding="utf-8")

        with pytest.raises(ConfigurationError, match="unable to parse"):
            load_configuration(config_path)

    def test_unknown_fields_are_rejected(self, automation_config_path: Path) -> None:
        """Reject fields outside the strict schema."""
        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace("    branch", "    unexpected: true\n    branch"),
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError, match="extra_forbidden"):
            load_configuration(automation_config_path)

    def test_duplicate_global_names_are_rejected(self, automation_config_path: Path) -> None:
        """Reject automation names repeated across repositories."""
        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration
            + """  owner/other:
    automations:
      hello-world:
        prompt: examples/hello-world
""",
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError, match="duplicate automation name"):
            load_configuration(automation_config_path)

    def test_duplicate_yaml_mapping_keys_are_rejected(self, automation_config_path: Path) -> None:
        """Reject keys that PyYAML would otherwise silently overwrite."""
        automation_config_path.write_text(
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
            load_configuration(automation_config_path)

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
    def test_invalid_semantic_values_are_rejected(
        self, automation_config_path: Path, old: str, new: str
    ) -> None:
        """Reject invalid repository, branch, environment, attempts, cron, and timezone values."""
        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(configuration.replace(old, new), encoding="utf-8")

        with pytest.raises(ConfigurationError):
            load_configuration(automation_config_path)

    @pytest.mark.parametrize("cron", ["0 0 L * *", "0 0 ? * *", "0 0 * * 5#3", "*/61 * * * *"])
    def test_croniter_extensions_are_rejected(self, automation_config_path: Path, cron: str) -> None:
        """Reject non-POSIX cron extensions accepted by croniter."""
        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace(
                "prompt: examples/hello-world",
                "schedule:\n"
                f"          cron: '{cron}'\n"
                "          timezone: UTC\n"
                "        prompt: examples/hello-world",
            ),
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError):
            load_configuration(automation_config_path)

    def test_stale_schema_is_rejected(self, automation_config_path: Path) -> None:
        """Reject a committed schema that differs from the generated model schema."""
        schema_path = automation_config_path.parent / "automations.schema.json"
        schema_path.write_text("{}\n", encoding="utf-8")

        with pytest.raises(ConfigurationError, match="stale generated schema"):
            validate_repository(automation_config_path, schema_path)

        schema_path.write_text(schema_text(), encoding="utf-8")

        assert validate_repository(automation_config_path, schema_path).config.version == 1
