from pathlib import Path

import pytest

from code_automations.errors import DispatchError
from code_automations.models.execution import (
    AgentResult,
    AutomationWorkspace,
    PublishedPullRequest,
    PullRequestMetadata,
    RepositoryWorkspace,
)
from code_automations.models.processes import CommandEnvironment, CommandRequest
from code_automations.models.runtime import DispatchRuntime
from code_automations.publication import publish_pull_request, publish_pull_requests
from code_automations.workspace import prepare_branch


class TestPublication:
    """Test create-only branch and pull request publication."""

    def test_existing_output_branch_fails_before_checkout(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Treat a generated branch collision as a terminal conflict."""

        requests: list[CommandRequest] = []
        environment = CommandEnvironment(HOME=str(tmp_path), PATH="/bin")

        def run(request: CommandRequest) -> str:
            """Report an existing remote branch."""

            requests.append(request)

            return "commit\trefs/heads/automation/review/hash\n"

        monkeypatch.setattr("code_automations.workspace.run_command", run)

        with pytest.raises(DispatchError, match="already exists"):
            prepare_branch(tmp_path, "main", "automation/review/hash", environment)

        assert len(requests) == 1
        assert "ls-remote" in requests[0].command

    def test_pull_request_is_created_without_lookup_or_edit(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Create one new pull request against the configured base branch."""

        repository = self.repository(tmp_path, branch="develop")
        workspace = self.workspace(tmp_path, repository)
        metadata = PullRequestMetadata(
            repository=repository.repository,
            title="Update repository",
            body="Summary",
        )

        environment = CommandEnvironment(GH_TOKEN="token", HOME=str(tmp_path), PATH="/bin")
        requests: list[CommandRequest] = []

        def run(request: CommandRequest) -> str:
            """Capture the pull request creation command."""

            requests.append(request)

            return "https://github.com/owner/repository/pull/1\n"

        monkeypatch.setattr("code_automations.publication.run_command", run)

        pull_request = publish_pull_request(tmp_path, workspace, repository, metadata, environment)

        assert str(pull_request.url) == "https://github.com/owner/repository/pull/1"
        assert requests[0].command[:3] == ["gh", "pr", "create"]
        assert requests[0].command[requests[0].command.index("--base") + 1] == "develop"
        assert "edit" not in requests[0].command
        assert "list" not in requests[0].command

    def test_publication_pushes_before_creating_from_the_clean_checkout(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Keep GitHub credentials and publication outside the agent checkout."""

        repository = self.repository(tmp_path / "agent")
        workspace = self.workspace(tmp_path, repository)
        runtime = self.runtime(tmp_path)
        result = AgentResult(
            summary="Completed.",
            repositories=[
                PullRequestMetadata(
                    repository="owner/repository",
                    title="Update repository",
                    body="Summary",
                )
            ],
        )

        clean_repository = repository.model_copy(update={"path": tmp_path / "publication"})
        events: list[str] = []

        def commit(
            received_repository: RepositoryWorkspace,
            metadata: PullRequestMetadata,
            environment: CommandEnvironment,
        ) -> None:
            """Require uncredentialed commits in both workspaces."""

            assert received_repository in (repository, clean_repository)
            assert metadata.repository == repository.repository
            assert "GH_TOKEN" not in environment

        def create_patch(
            publication_root: Path,
            received_repository: RepositoryWorkspace,
            environment: CommandEnvironment,
        ) -> Path:
            """Return an uncredentialed patch path."""

            assert publication_root.parent == tmp_path
            assert received_repository is repository
            assert "GH_TOKEN" not in environment

            return tmp_path / "changes.patch"

        def create_checkout(
            publication_root: Path,
            received_workspace: AutomationWorkspace,
            received_runtime: DispatchRuntime,
            received_repository: RepositoryWorkspace,
        ) -> RepositoryWorkspace:
            """Return the clean publication checkout."""

            assert publication_root.parent == tmp_path
            assert received_workspace is workspace
            assert received_runtime is runtime
            assert received_repository is repository

            return clean_repository

        def apply(
            received_repository: RepositoryWorkspace,
            patch_path: Path,
            environment: CommandEnvironment,
        ) -> None:
            """Require uncredentialed patch application."""

            assert received_repository is clean_repository
            assert patch_path == tmp_path / "changes.patch"
            assert "GH_TOKEN" not in environment

        def run(request: CommandRequest) -> str:
            """Capture the authenticated push command."""

            assert request.cwd == clean_repository.path
            assert request.environment["GH_TOKEN"] == "token"
            events.append("push")

            return ""

        def publish(
            publication_root: Path,
            received_workspace: AutomationWorkspace,
            received_repository: RepositoryWorkspace,
            metadata: PullRequestMetadata,
            environment: CommandEnvironment,
        ) -> PublishedPullRequest:
            """Create the pull request after its branch is pushed."""

            assert events == ["push"]
            assert publication_root.parent == tmp_path
            assert received_workspace is workspace
            assert received_repository is clean_repository
            assert metadata.repository == repository.repository
            assert environment["GH_TOKEN"] == "token"
            events.append("pull-request")

            return PublishedPullRequest(
                repository=repository.repository,
                url="https://github.com/owner/repository/pull/1",
            )

        monkeypatch.setattr("code_automations.publication.commit_repository", commit)
        monkeypatch.setattr("code_automations.publication.create_patch", create_patch)
        monkeypatch.setattr("code_automations.publication.create_publication_repository", create_checkout)
        monkeypatch.setattr("code_automations.publication.apply_patch", apply)
        monkeypatch.setattr("code_automations.publication.run_command", run)
        monkeypatch.setattr("code_automations.publication.publish_pull_request", publish)

        pull_requests = publish_pull_requests(workspace, runtime, result, [repository])

        assert events == ["push", "pull-request"]
        assert pull_requests[0].repository == repository.repository

    def test_no_change_publication_returns_no_pull_requests(self, tmp_path: Path) -> None:
        """Succeed without publication when no repository changed."""

        repository = self.repository(tmp_path)
        workspace = self.workspace(tmp_path, repository)
        result = AgentResult(summary="Completed.", repositories=[])

        assert publish_pull_requests(workspace, self.runtime(tmp_path), result, []) == []

    def test_all_branches_are_pushed_before_any_pull_request(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Finish multi-repository branch publication before opening pull requests."""

        repositories = [
            self.repository(tmp_path / "first").model_copy(update={"repository": "owner/first"}),
            self.repository(tmp_path / "second").model_copy(update={"repository": "owner/second"}),
        ]
        workspace = AutomationWorkspace(
            root=tmp_path,
            home=tmp_path / "home",
            branch="automation/review/hash",
            repositories=repositories,
        )

        result = AgentResult(
            summary="Completed.",
            repositories=[
                PullRequestMetadata(repository=repository.repository, title="Update", body="Summary")
                for repository in repositories
            ],
        )

        runtime = self.runtime(tmp_path)
        events: list[str] = []

        def commit(
            repository: RepositoryWorkspace,
            metadata: PullRequestMetadata,
            environment: CommandEnvironment,
        ) -> None:
            """Accept uncredentialed commits during publication setup."""

            assert metadata.repository == repository.repository
            assert "GH_TOKEN" not in environment

        def create_patch(
            publication_root: Path,
            repository: RepositoryWorkspace,
            environment: CommandEnvironment,
        ) -> Path:
            """Return the agent patch path for each repository."""

            assert publication_root.parent == tmp_path
            assert repository in repositories
            assert "GH_TOKEN" not in environment

            return tmp_path / "changes.patch"

        def create_checkout(
            publication_root: Path,
            received_workspace: AutomationWorkspace,
            received_runtime: DispatchRuntime,
            repository: RepositoryWorkspace,
        ) -> RepositoryWorkspace:
            """Return one clean publication checkout."""

            assert publication_root.parent == tmp_path
            assert received_workspace is workspace
            assert received_runtime is runtime

            return repository.model_copy(
                update={"path": tmp_path / "publication" / repository.repository.replace("/", "--")}
            )

        def apply(
            repository: RepositoryWorkspace,
            patch_path: Path,
            environment: CommandEnvironment,
        ) -> None:
            """Accept patch application in the clean repository checkout."""

            assert repository.path.parent == tmp_path / "publication"
            assert patch_path == tmp_path / "changes.patch"
            assert "GH_TOKEN" not in environment

        def run(request: CommandRequest) -> str:
            """Record each branch push."""

            events.append(f"push:{request.cwd.name}")

            return ""

        def publish(
            publication_root: Path,
            received_workspace: AutomationWorkspace,
            repository: RepositoryWorkspace,
            metadata: PullRequestMetadata,
            environment: CommandEnvironment,
        ) -> PublishedPullRequest:
            """Require both pushes before pull request publication."""

            assert len([event for event in events if event.startswith("push:")]) == 2
            assert publication_root.parent == tmp_path
            assert received_workspace is workspace
            assert metadata.repository == repository.repository
            assert environment["GH_TOKEN"] == "token"
            events.append(f"pull-request:{repository.repository}")

            return PublishedPullRequest(
                repository=repository.repository,
                url=f"https://github.com/{repository.repository}/pull/1",
            )

        monkeypatch.setattr("code_automations.publication.commit_repository", commit)
        monkeypatch.setattr("code_automations.publication.create_patch", create_patch)
        monkeypatch.setattr("code_automations.publication.create_publication_repository", create_checkout)
        monkeypatch.setattr("code_automations.publication.apply_patch", apply)
        monkeypatch.setattr("code_automations.publication.run_command", run)
        monkeypatch.setattr("code_automations.publication.publish_pull_request", publish)

        pull_requests = publish_pull_requests(workspace, runtime, result, repositories)

        assert events[:2] == ["push:owner--first", "push:owner--second"]
        assert [pull_request.repository for pull_request in pull_requests] == [
            "owner/first",
            "owner/second",
        ]

    def repository(self, path: Path, branch: str = "main") -> RepositoryWorkspace:
        """Build a repository workspace."""

        return RepositoryWorkspace(
            repository="owner/repository",
            branch=branch,
            path=path,
            starting_commit="commit",
        )

    def workspace(self, root: Path, repository: RepositoryWorkspace) -> AutomationWorkspace:
        """Build an automation workspace."""

        return AutomationWorkspace(
            root=root,
            home=root / "home",
            branch="automation/review/hash",
            repositories=[repository],
        )

    def runtime(self, tmp_path: Path) -> DispatchRuntime:
        """Build a complete dispatch runtime."""

        return DispatchRuntime(
            github_token="token",
            command_path="/bin",
            github_home=tmp_path / "github-home",
            codex_home=tmp_path / "codex-home",
            runner_image="code-automations-runner:123",
            runner_user="1001:1001",
            runner_temp=tmp_path,
            github_run_id="123",
            github_run_attempt="1",
        )
