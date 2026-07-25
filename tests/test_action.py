from pathlib import Path

import yaml


class TestAction:
    """Test the reusable GitHub Action contract."""

    def test_composite_action_launches_codex_cloud(self) -> None:
        """Expose only the configuration and Cloud dispatch inputs."""

        action_path = Path(__file__).parents[1] / "action.yml"
        action = yaml.safe_load(action_path.read_text(encoding="utf-8"))
        inputs = action["inputs"]
        rendered = action_path.read_text(encoding="utf-8")

        assert action["runs"]["using"] == "composite"
        assert set(inputs) == {
            "automations-file-path",
            "codex-auth-json",
            "codex-environment-id",
            "mode",
            "prompts-directory-path",
            "run-automation-name",
            "skills-directory-path",
        }
        assert inputs["codex-environment-id"]["required"] is True
        assert "github-token" not in inputs
        assert "docker build" not in rendered
        assert "npm ci --omit=dev --prefix" in rendered
        assert "codex cloud" not in rendered
        assert '--environment "$CODEX_ENVIRONMENT_ID"' in rendered
        assert '--branch "$GITHUB_REF_NAME"' in rendered
        assert "scheduled dispatch is only allowed from the default branch" in rendered
        assert "workflow_dispatch) ;;" in rendered

    def test_release_workflow_publishes_v0_alpha_tags(self) -> None:
        """Publish immutable patch tags and update the moving v0 tag."""

        workflow_path = Path(__file__).parents[1] / ".github/workflows/publish-release.yml"
        workflow = workflow_path.read_text(encoding="utf-8")

        assert '"v0.0.*"' in workflow
        assert "git tag -f v0" in workflow
        assert "git push origin -f v0" in workflow
        assert "workflow_dispatch" not in workflow

    def test_documentation_disables_checkout_credentials(self) -> None:
        """Keep consumer checkout credentials disabled."""

        readme_path = Path(__file__).parents[1] / "README.md"

        assert "persist-credentials: false" in readme_path.read_text(encoding="utf-8")
