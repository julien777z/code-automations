from pathlib import Path

import pytest

from code_automations.models.configuration import ModelConfig
from code_automations.models.runtime import CliArguments, CloudTask
from code_automations.runtime import run


class TestRuntime:
    """Test command-line dispatch orchestration."""

    def test_manual_dispatch_submits_and_waits(
        self,
        automation_config_path: Path,
        prompts_directory: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Launch and monitor the selected automation."""

        task = CloudTask(
            task_id="task_example",
            url="https://chatgpt.com/codex/tasks/task_example",
        )
        submissions: list[tuple[str, str, str, ModelConfig]] = []
        waits: list[str] = []

        def submit(environment: str, branch: str, prompt: str, model: ModelConfig) -> CloudTask:
            """Capture one Cloud submission."""

            submissions.append((environment, branch, prompt, model))

            return task

        monkeypatch.setattr("code_automations.runtime.submit_cloud_task", submit)
        monkeypatch.setattr(
            "code_automations.runtime.wait_for_cloud_task",
            lambda received, timeout: waits.append(received.task_id),
        )
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repository")

        result = run(
            CliArguments(
                config=automation_config_path,
                prompts_directory=prompts_directory,
                command="dispatch",
                automation="hello-world",
                environment="environment_example",
                branch="alpha",
            )
        )

        assert result == 0
        assert submissions[0][:2] == ("environment_example", "alpha")
        assert "Say hello." in submissions[0][2]
        assert submissions[0][3] == ModelConfig(name="gpt-5.6-terra", reasoning_effort="high")
        assert waits == ["task_example"]

    def test_scheduled_dispatch_uses_dispatcher_occurrence(
        self,
        scheduled_configuration,
        prompts_directory: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Evaluate delayed workflow events at their scheduled instant."""

        config_path = scheduled_configuration.root / "automations.yaml"
        submitted: list[str] = []

        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repository")
        monkeypatch.setattr(
            "code_automations.runtime.submit_target",
            lambda loaded, target, environment, branch, timeout, summary_path: submitted.append(target.name),
        )

        result = run(
            CliArguments(
                config=config_path,
                prompts_directory=prompts_directory,
                command="dispatch",
                scheduled=True,
                now="2025-07-15T18:05:00Z",
                dispatcher_schedule="0 * * * *",
                environment="environment_example",
                branch="main",
            )
        )

        assert result == 0
        assert submitted == ["scheduled"]
