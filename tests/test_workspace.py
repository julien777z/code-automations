from datetime import UTC, datetime
from pathlib import Path

from code_automations.models.configuration import (
    AutomationConfig,
    AutomationsConfig,
    AutomationTarget,
    FragmentDirectories,
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

    def test_output_branch_is_stable_within_one_action_attempt(self, tmp_path: Path) -> None:
        """Hash execution identity without using a repository base branch."""

        target = AutomationTarget(
            name="weekly-review",
            project="example",
            repositories=[ResolvedRepository(repository="owner/repository", branch="main")],
            automation=AutomationConfig(prompt="examples/task"),
        )

        loaded = LoadedConfiguration(
            root=tmp_path,
            fragment_directories=FragmentDirectories(
                prompts=tmp_path / "examples/prompts",
                skills=tmp_path / "examples/skills",
            ),
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
            runner_image="code-automations-runner:123",
            runner_user="1001:1001",
            runner_temp=tmp_path,
            github_run_id="123",
            github_run_attempt="1",
        )

        scheduled = ExecutionRequest(
            loaded=loaded,
            target=target,
            scheduled_for=datetime(2025, 7, 15, 18, 0, tzinfo=UTC),
        )

        manual = ExecutionRequest(loaded=loaded, target=target)

        scheduled_branch = output_branch(scheduled, runtime)

        assert scheduled_branch == output_branch(scheduled, runtime)
        assert scheduled_branch.startswith("automation/weekly-review/")
        assert len(scheduled_branch.rsplit("/", maxsplit=1)[1]) == 16
        assert output_branch(manual, runtime) != scheduled_branch
        assert (
            output_branch(scheduled, runtime.model_copy(update={"github_run_attempt": "2"}))
            != scheduled_branch
        )
