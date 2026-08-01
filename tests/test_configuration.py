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
from code_automations.models.configuration import AutomationsConfig, ModelConfig
from code_automations.models.runtime import PreparedRepository
from code_automations.rendering import render_target


class TestConfiguration:
    """Test configuration loading, schema, and prompt rendering."""

    def test_valid_configuration_renders_local_publication_task(
        self,
        automation_config_path: Path,
        prompts_directory: Path,
    ) -> None:
        """Resolve repositories, prepared paths, and task instructions."""

        loaded = load_configuration(automation_config_path, prompts_directory)
        target = find_target(loaded, "owner/repository", "hello-world")
        rendered = render_target(
            loaded,
            target,
            [
                PreparedRepository(
                    repository="owner/repository",
                    branch="main",
                    path=Path("/runner/repositories/0"),
                ),
                PreparedRepository(
                    repository="owner/secondary",
                    branch="develop",
                    path=Path("/runner/repositories/1"),
                ),
            ],
        )

        assert [repository.repository for repository in target.repositories] == [
            "owner/repository",
            "owner/secondary",
        ]
        assert target.model == ModelConfig(name="gpt-5.6-terra", reasoning_effort="high")
        assert "/runner/repositories/0 (base branch: main)" in rendered
        assert "/runner/repositories/1 (base branch: develop)" in rendered
        assert "Use the branch `automation/hello-world`" in rendered
        assert "Do not merge any pull request" not in rendered
        assert "Required skills" not in rendered
        assert "example-skill" not in rendered
        assert "Be concise." not in rendered
        assert rendered.endswith("Say hello.\n")

    def test_root_model_applies_without_an_automation_override(self, scheduled_configuration) -> None:
        """Use the root model for automations that do not override it."""

        target = find_target(scheduled_configuration, "owner/repository", "scheduled")

        assert target.model == ModelConfig(name="gpt-5.6-terra", reasoning_effort="low")

    def test_global_agent_prompt_is_a_markdown_resource(self) -> None:
        """Keep agent prompt prose out of application code."""

        repository_root = Path(__file__).parents[1]
        rendering_source = (repository_root / "src/code_automations/rendering.py").read_text(encoding="utf-8")
        global_rule_path = repository_root / "src/code_automations/prompts/global.md"
        global_rule = global_rule_path.read_text(encoding="utf-8")

        assert "Do not merge any pull request" not in rendering_source
        assert "Do not merge any pull request" in global_rule

    def test_legacy_automation_model_is_rejected(
        self,
        automation_config_path: Path,
        prompts_directory: Path,
    ) -> None:
        """Require the explicit per-automation override field name."""

        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace("        model_override:", "        model:"),
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError, match="Extra inputs are not permitted"):
            load_configuration(automation_config_path, prompts_directory)

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

    def test_repository_names_are_deferred_to_github(
        self,
        automation_config_path: Path,
        prompts_directory: Path,
    ) -> None:
        """Leave repository identifier validation to GitHub."""

        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace("owner/secondary:", "not-a-github-repository:"),
            encoding="utf-8",
        )

        loaded = load_configuration(automation_config_path, prompts_directory)
        target = find_target(loaded, "owner/repository", "hello-world")
        assert target.repositories[1].repository == "not-a-github-repository"

    def test_merge_configuration_is_rejected(
        self,
        automation_config_path: Path,
        prompts_directory: Path,
    ) -> None:
        """Keep pull request merging outside consumer configuration."""

        configuration = automation_config_path.read_text(encoding="utf-8")
        automation_config_path.write_text(
            configuration.replace(
                "        prompt: hello-world",
                "        prompt: hello-world\n        merge:\n          workflows:\n            - Run Tests",
            ),
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError, match="Extra inputs are not permitted"):
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
