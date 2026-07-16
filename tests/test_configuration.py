from pathlib import Path

import pytest

from code_automations.cli import run
from code_automations.configuration import (
    load_configuration,
    read_fragment,
    schema_text,
    validate_configuration,
)
from code_automations.errors import ConfigurationError
from code_automations.models.cli import CliArguments
from code_automations.rendering import render_target
from code_automations.targets import find_target


class TestConfiguration:
    """Test automation configuration loading and validation."""

    def test_valid_nested_configuration_renders_deterministically(self, automation_config_path: Path) -> None:
        """Resolve ordered repository and fragment configuration."""

        loaded = load_configuration(automation_config_path)
        target = find_target(loaded, "owner/repository", "hello-world")

        first = render_target(loaded, target)
        second = render_target(loaded, target)

        assert first == second

        assert [repository.repository for repository in target.repositories] == [
            "owner/repository",
            "owner/secondary",
        ]
        assert [repository.branch for repository in target.repositories] == ["main", "develop"]
        assert first.index("# Skill: examples/concise") < first.index("# Prompt")
        assert "owner/secondary: owner/secondary (base branch: develop)" in first

    def test_repository_branches_default_independently(self, automation_config_path: Path) -> None:
        """Default each omitted repository branch to main."""

        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace("owner/secondary:\n        branch: develop", "owner/secondary: {}"),
            encoding="utf-8",
        )

        loaded = load_configuration(automation_config_path)
        target = find_target(loaded, "owner/repository", "hello-world")

        assert [repository.branch for repository in target.repositories] == ["main", "main"]

    def test_explicit_repositories_do_not_require_a_local_origin(
        self,
        automation_config_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Render explicit repositories without resolving the reserved self value."""

        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace("      self:\n        branch: main\n", "      owner/primary: {}\n"),
            encoding="utf-8",
        )
        monkeypatch.chdir(automation_config_path.parent)

        result = run(
            CliArguments(
                config=automation_config_path,
                command="render",
                automation="hello-world",
            )
        )

        assert result == 0

    def test_duplicate_resolved_repositories_are_rejected(self, automation_config_path: Path) -> None:
        """Reject a self repository repeated as an explicit repository."""

        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace("owner/secondary:", "owner/repository:"),
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError, match="duplicate resolved repository"):
            validate_configuration(automation_config_path, "owner/repository")

    @pytest.mark.parametrize("repository", ["owner/.", "owner/..", "owner/repository.git"])
    def test_invalid_repository_path_segments_are_rejected(
        self,
        automation_config_path: Path,
        repository: str,
    ) -> None:
        """Reject repository names GitHub cannot clone or publish."""

        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace("owner/secondary", repository),
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError, match="invalid repository identifier"):
            load_configuration(automation_config_path)

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
        config_path.write_text("projects: [\n", encoding="utf-8")

        with pytest.raises(ConfigurationError, match="unable to parse"):
            load_configuration(config_path)

    @pytest.mark.parametrize(
        "invalid",
        [
            "environment: Cloud",
            "attempts: 2",
            "branch: bad branch",
            "branch: HEAD",
            "unknown: true",
        ],
    )
    def test_removed_and_unknown_fields_are_rejected(
        self,
        automation_config_path: Path,
        invalid: str,
    ) -> None:
        """Reject obsolete Cloud fields and unrecognized configuration."""

        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace("branch: main", f"branch: main\n        {invalid}", 1),
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError):
            load_configuration(automation_config_path)

    @pytest.mark.parametrize("name", ["foo..bar", "foo.lock"])
    def test_unsafe_automation_names_are_rejected(
        self,
        automation_config_path: Path,
        name: str,
    ) -> None:
        """Reject names that would create invalid automation branches."""

        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace("hello-world:", f"{name}:"),
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError, match="invalid automation name"):
            load_configuration(automation_config_path)

    def test_duplicate_global_names_are_rejected(self, automation_config_path: Path) -> None:
        """Reject automation names repeated across projects."""

        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration
            + """  other:
    repositories:
      owner/other: {}
    automations:
      hello-world:
        prompt: examples/hello-world
""",
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError, match="duplicate automation name"):
            load_configuration(automation_config_path)

    def test_configuration_validation_does_not_require_a_local_schema(
        self, automation_config_path: Path
    ) -> None:
        """Validate consumer resources without requiring a copied schema file."""

        validate_configuration(automation_config_path, "owner/repository")

        assert not (automation_config_path.parent / "automations.schema.json").exists()

    def test_committed_schema_matches_the_configuration_model(self) -> None:
        """Keep the action repository's published schema synchronized with its model."""

        schema_path = Path(__file__).parents[1] / "automations.schema.json"

        assert schema_path.read_text(encoding="utf-8") == schema_text()
