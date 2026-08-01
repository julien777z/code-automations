from pathlib import Path

import pytest

from code_automations.__main__ import run
from code_automations.models.configuration import ModelConfig
from code_automations.models.runtime import CliArguments


class TestRuntime:
    """Test command-line dispatch orchestration."""

    def test_manual_dispatch_runs_selected_target_locally(
        self,
        automation_config_path: Path,
        prompts_directory: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Prepare and run the selected automation on the runner."""

        runs: list[tuple[str, ModelConfig, Path, Path]] = []

        def run_selected(loaded, target, workspace, agent_home, summary_path) -> None:
            """Capture one local automation run."""

            runs.append((target.name, target.model, workspace, agent_home))

        monkeypatch.setattr("code_automations.__main__.run_target", run_selected)
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repository")

        result = run(
            CliArguments(
                config=automation_config_path,
                prompts_directory=prompts_directory,
                command="dispatch",
                automation="hello-world",
                workspace=tmp_path / "workspace",
                agent_home=tmp_path / "agent-home",
            )
        )

        assert result == 0
        assert runs == [
            (
                "hello-world",
                ModelConfig(name="gpt-5.6-terra", reasoning_effort="high"),
                tmp_path / "workspace",
                tmp_path / "agent-home",
            )
        ]

    def test_scheduled_dispatch_uses_dispatcher_occurrence(
        self,
        scheduled_configuration,
        prompts_directory: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Evaluate delayed workflow events at their scheduled instant."""

        config_path = scheduled_configuration.root / "automations.yaml"
        submitted: list[str] = []

        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repository")
        monkeypatch.setattr(
            "code_automations.__main__.run_target",
            lambda loaded, target, workspace, agent_home, summary_path: submitted.append(target.name),
        )

        result = run(
            CliArguments(
                config=config_path,
                prompts_directory=prompts_directory,
                command="dispatch",
                scheduled=True,
                now="2025-07-15T18:05:00Z",
                dispatcher_schedule="0 * * * *",
                workspace=tmp_path / "workspace",
                agent_home=tmp_path / "agent-home",
            )
        )

        assert result == 0
        assert submitted == ["scheduled"]
