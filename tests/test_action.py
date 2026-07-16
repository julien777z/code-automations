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
            "run-automation",
        }
        assert inputs["automations-file-path"]["default"] == "automations.yaml"
        assert inputs["mode"]["default"] == "dispatch"
        assert "GITHUB_EVENT_NAME" in action["runs"]["steps"][0]["env"]
        assert "schedule|workflow_dispatch" in action["runs"]["steps"][0]["run"]
        assert "automation file must resolve inside the checked-out repository" in action["runs"]["steps"][0]["run"]

    def test_documented_dispatch_disables_checkout_credentials(self) -> None:
        """Keep the consumer workflow free of checkout credentials during agent execution."""

        readme_path = Path(__file__).parents[1] / "README.md"

        assert "persist-credentials: false" in readme_path.read_text(encoding="utf-8")
