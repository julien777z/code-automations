import json
from pathlib import Path

import pytest

from code_automations.configuration import (
    find_target,
    load_configuration,
    read_fragment,
    validate_configuration,
)
from code_automations.errors import ConfigurationError
from code_automations.models.configuration import AutomationsConfig, FragmentDirectories
from code_automations.rendering import render_target


class TestConfiguration:
    """Test configuration loading, schema, and prompt rendering."""

    def test_valid_configuration_renders_cloud_publication_contract(
        self,
        automation_config_path: Path,
        fragment_directories: FragmentDirectories,
    ) -> None:
        """Resolve repositories, fragments, and exact merge workflows."""

        loaded = load_configuration(automation_config_path, fragment_directories)
        target = find_target(loaded, "owner/repository", "hello-world")
        rendered = render_target(loaded, target)

        assert [repository.repository for repository in target.repositories] == [
            "owner/repository",
            "owner/secondary",
        ]
        assert "../repository (base branch: main)" in rendered
        assert "../secondary (base branch: develop)" in rendered
        assert "Use the branch automation/hello-world" in rendered
        assert "Only these exact GitHub Actions workflows gate merging: `Run Tests`." in rendered
        assert "Ignore every other workflow" in rendered
        assert rendered.index("# Skill: example-skill") < rendered.index("# Prompt")

    def test_duplicate_resolved_repositories_are_rejected(
        self,
        automation_config_path: Path,
        fragment_directories: FragmentDirectories,
    ) -> None:
        """Reject a repository repeated through self."""

        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace("owner/secondary:", "owner/repository:"),
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError, match="duplicate resolved repository"):
            validate_configuration(automation_config_path, fragment_directories, "owner/repository")

    def test_duplicate_merge_workflows_are_rejected(
        self,
        automation_config_path: Path,
        fragment_directories: FragmentDirectories,
    ) -> None:
        """Reject ambiguous repeated workflow gates."""

        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace("- Run Tests", "- Run Tests\n            - Run Tests"),
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError, match="must be unique"):
            load_configuration(automation_config_path, fragment_directories)

    @pytest.mark.parametrize("reference", ["../secret", "/secret", "foo\\bar", "foo//bar"])
    def test_unsafe_references_are_rejected(
        self,
        automation_config_path: Path,
        fragment_directories: FragmentDirectories,
        reference: str,
    ) -> None:
        """Reject unsafe prompt and skill references."""

        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace("prompt: hello-world", f"prompt: {reference}"),
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError):
            load_configuration(automation_config_path, fragment_directories)

    def test_missing_fragment_is_rejected(
        self,
        automation_config_path: Path,
        fragment_directories: FragmentDirectories,
    ) -> None:
        """Reject missing prompt and skill files."""

        (fragment_directories.skills / "example-skill.md").unlink()

        with pytest.raises(ConfigurationError, match="missing or non-regular"):
            load_configuration(automation_config_path, fragment_directories)

    def test_non_utf8_fragment_is_rejected(self, tmp_path: Path) -> None:
        """Reject fragment content that cannot be decoded."""

        directory = tmp_path / "prompts"
        directory.mkdir()
        (directory / "invalid.md").write_bytes(b"\xff")

        with pytest.raises(ConfigurationError, match="not UTF-8"):
            read_fragment(directory, "prompt", "invalid")

    def test_tracked_schema_matches_configuration_model(self) -> None:
        """Keep the public JSON schema synchronized with Pydantic."""

        schema_path = Path(__file__).parents[1] / "automations.schema.json"
        tracked = json.loads(schema_path.read_text(encoding="utf-8"))

        assert tracked == AutomationsConfig.model_json_schema()
