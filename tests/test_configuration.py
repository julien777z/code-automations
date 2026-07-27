import json
from pathlib import Path

import pytest

from code_automations.configuration import (
    find_target,
    load_configuration,
    read_prompt,
    resolve_targets,
)
from code_automations.errors import ConfigurationError
from code_automations.models.configuration import AutomationsConfig
from code_automations.rendering import render_target


class TestConfiguration:
    """Test configuration loading, schema, and prompt rendering."""

    def test_valid_configuration_renders_cloud_publication_contract(
        self,
        automation_config_path: Path,
        prompts_directory: Path,
    ) -> None:
        """Resolve repositories, fragments, and exact merge workflows."""

        loaded = load_configuration(automation_config_path, prompts_directory)
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
        assert "# Required skills" in rendered
        assert "`example-skill`" in rendered
        assert "Be concise." not in rendered
        assert rendered.index("# Required skills") < rendered.index("# Prompt")

    def test_duplicate_resolved_repositories_are_rejected(
        self,
        automation_config_path: Path,
        prompts_directory: Path,
    ) -> None:
        """Reject a repository repeated through self."""

        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace("owner/secondary:", "owner/repository:"),
            encoding="utf-8",
        )

        loaded = load_configuration(automation_config_path, prompts_directory)

        with pytest.raises(ConfigurationError, match="duplicate resolved repository"):
            resolve_targets(loaded, "owner/repository")

    def test_duplicate_merge_workflows_are_rejected(
        self,
        automation_config_path: Path,
        prompts_directory: Path,
    ) -> None:
        """Reject ambiguous repeated workflow gates."""

        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace("- Run Tests", "- Run Tests\n            - Run Tests"),
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError, match="must be unique"):
            load_configuration(automation_config_path, prompts_directory)

    @pytest.mark.parametrize("reference", ["../secret", "/secret", "foo\\bar", "foo//bar"])
    def test_unsafe_references_are_rejected(
        self,
        automation_config_path: Path,
        prompts_directory: Path,
        reference: str,
    ) -> None:
        """Reject unsafe prompt and skill references."""

        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace("prompt: hello-world", f"prompt: {reference}"),
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError):
            load_configuration(automation_config_path, prompts_directory)

    def test_missing_native_skill_is_rejected(
        self,
        automation_config_path: Path,
        prompts_directory: Path,
    ) -> None:
        """Reject a configured skill absent from the canonical agent directory."""

        (automation_config_path.parent / ".agents/skills/example-skill/SKILL.md").unlink()

        with pytest.raises(ConfigurationError, match="Missing SKILL.md"):
            load_configuration(automation_config_path, prompts_directory)

    def test_non_utf8_fragment_is_rejected(self, tmp_path: Path) -> None:
        """Reject fragment content that cannot be decoded."""

        directory = tmp_path / "prompts"
        directory.mkdir()
        (directory / "invalid.md").write_bytes(b"\xff")

        with pytest.raises(ConfigurationError, match="not UTF-8"):
            read_prompt(directory, "invalid")

    def test_tracked_schema_matches_configuration_model(self) -> None:
        """Keep the public JSON schema synchronized with Pydantic."""

        schema_path = Path(__file__).parents[1] / "automations.schema.json"
        tracked = json.loads(schema_path.read_text(encoding="utf-8"))

        assert tracked == AutomationsConfig.model_json_schema()
