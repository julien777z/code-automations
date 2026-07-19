from pathlib import Path

import yaml


class TestAction:
    """Test the reusable GitHub Action contract."""

    def test_composite_action_exposes_the_consumer_inputs(self) -> None:
        """Keep the public inputs focused on configuration and dispatch."""

        action_path = Path(__file__).parents[1] / "action.yml"
        action = yaml.safe_load(action_path.read_text(encoding="utf-8"))
        inputs = action["inputs"]

        assert action["runs"]["using"] == "composite"

        assert set(inputs) == {
            "codex-auth-json",
            "automations-file-path",
            "github-token",
            "mode",
            "prompts-directory-path",
            "run-automation",
            "skills-directory-path",
        }
        assert inputs["automations-file-path"]["default"] == "automations.yaml"
        assert inputs["prompts-directory-path"]["required"] is True
        assert "default" not in inputs["prompts-directory-path"]
        assert inputs["skills-directory-path"]["required"] is True
        assert "default" not in inputs["skills-directory-path"]
        assert inputs["mode"]["default"] == "dispatch"
        assert "GITHUB_EVENT_NAME" in action["runs"]["steps"][0]["env"]
        assert "schedule|workflow_dispatch" in action["runs"]["steps"][0]["run"]
        assert (
            "automation resources must resolve inside the checked-out repository"
            in action["runs"]["steps"][0]["run"]
        )

        rendered = action_path.read_text(encoding="utf-8")

        assert "actions/setup-node" not in rendered
        assert "npm ci --prefix" not in rendered
        assert "docker build" in rendered
        assert "AUTOMATION_RUNNER_IMAGE" in rendered
        assert "AUTOMATION_RUNNER_USER" in rendered
        assert '--prompts-directory "$GITHUB_WORKSPACE/$PROMPTS_DIRECTORY_PATH"' in rendered
        assert '--skills-directory "$GITHUB_WORKSPACE/$SKILLS_DIRECTORY_PATH"' in rendered
        assert ".github/actionlint" not in rendered

        dockerfile = (action_path.parent / "docker/Dockerfile").read_text(encoding="utf-8")

        assert "COPY package.json package-lock.json" in dockerfile
        assert "npm ci --omit=dev" in dockerfile

    def test_documented_dispatch_disables_checkout_credentials(self) -> None:
        """Keep the consumer workflow free of checkout credentials during agent execution."""

        readme_path = Path(__file__).parents[1] / "README.md"

        assert "persist-credentials: false" in readme_path.read_text(encoding="utf-8")
