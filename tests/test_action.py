from pathlib import Path

import yaml


class TestAction:
    """Test the reusable GitHub Action contract."""

    def test_composite_action_launches_cloud_task(self) -> None:
        """Expose Cloud dispatch and durable authentication inputs."""

        action_path = Path(__file__).parents[1] / "action.yml"
        action_script_path = Path(__file__).parents[1] / ".github/scripts/action.py"
        bootstrap_script_path = Path(__file__).parents[1] / ".github/scripts/bootstrap.py"
        config_script_path = Path(__file__).parents[1] / ".github/scripts/config.py"
        action = yaml.safe_load(action_path.read_text(encoding="utf-8"))
        inputs = action["inputs"]
        rendered = action_path.read_text(encoding="utf-8")
        action_script = action_script_path.read_text(encoding="utf-8")
        bootstrap_script = bootstrap_script_path.read_text(encoding="utf-8")
        config_script = config_script_path.read_text(encoding="utf-8")

        assert action["runs"]["using"] == "composite"
        assert set(inputs) == {
            "automations-file-path",
            "codex-auth-json",
            "codex-environment-id",
            "github-token",
            "mode",
            "prompts-directory-path",
            "run-automation-name",
        }
        assert inputs["github-token"]["required"] is False
        assert inputs["github-token"]["default"] == ""
        assert "docker build" not in rendered
        assert 'case "$AUTOMATION_MODE"' not in rendered
        assert "automation_command=(" not in rendered
        assert 'python "$GITHUB_ACTION_PATH/.github/scripts/action.py"' in rendered
        assert '"npm", "ci", "--omit=dev", "--prefix"' in bootstrap_script
        assert "environment_value" not in action_script
        assert "BaseSettings" in config_script
        assert "Persist Automation Authentication" in rendered
        assert "inputs.github-token || github.token" in rendered
        assert '"--environment",' in action_script
        assert '"--branch",' in action_script
        assert "cwd=config.github_workspace" in action_script
        assert "CODEX_ENVIRONMENT_ID" in rendered
        assert "codex_environment_id" in config_script
        assert 'gh", "secret", "set", "CODEX_AUTH_JSON' in action_script
        assert "scheduled dispatch is only allowed from the default branch" in config_script
        assert 'github_event_name != "workflow_dispatch"' in config_script

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
