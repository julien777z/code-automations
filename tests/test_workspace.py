from datetime import UTC, datetime
from pathlib import Path

from code_automations.models.configuration import (
    AutomationConfig,
    AutomationsConfig,
    AutomationTarget,
    LoadedConfiguration,
    ProjectConfig,
    RepositoryConfig,
    ResolvedRepository,
)
from code_automations.models.dispatching import ExecutionRequest
from code_automations.models.runtime import DispatchRuntime
from code_automations.workspace import output_branch


class TestWorkspace:
    """Test deterministic multi-repository workspace details."""

    def test_output_branch_uses_one_name_for_scheduled_and_manual_runs(self, tmp_path: Path) -> None:
        """Derive deterministic branch names without using a repository base branch."""

        target = AutomationTarget(
            name="weekly-review",
            project="example",
            repositories=[ResolvedRepository(repository="owner/repository", branch="main")],
            automation=AutomationConfig(prompt="examples/task"),
        )
        loaded = LoadedConfiguration(
            root=tmp_path,
            config=AutomationsConfig(
                version=1,
                projects={
                    "example": ProjectConfig(
                        repositories={"owner/repository": RepositoryConfig()},
                        automations={"weekly-review": AutomationConfig(prompt="examples/task")},
                    )
                },
            ),
        )
        runtime = DispatchRuntime(
            github_token="token",
            command_path="/bin",
            github_home=tmp_path / "github-home",
            codex_home=tmp_path,
            runner_temp=tmp_path,
            github_run_id="123",
        )
        scheduled = ExecutionRequest(
            loaded=loaded,
            target=target,
            scheduled_for=datetime(2025, 7, 15, 18, 0, tzinfo=UTC),
        )
        manual = ExecutionRequest(loaded=loaded, target=target)

        assert output_branch(scheduled, runtime) == "automation/weekly-review/20250715T180000Z"
        assert output_branch(manual, runtime) == "automation/weekly-review/run-123"
