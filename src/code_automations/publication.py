from typing import Final

from pydantic import TypeAdapter, ValidationError

from code_automations.errors import DispatchError
from code_automations.models.execution import (
    AgentResult,
    AutomationWorkspace,
    ExistingPullRequest,
    PublishedPullRequest,
    PullRequestMetadata,
    PullRequestState,
    RepositoryWorkspace,
)
from code_automations.models.processes import CommandEnvironment, CommandRequest
from code_automations.models.runtime import DispatchRuntime
from code_automations.processes import run_command
from code_automations.workspace import (
    GIT_CREDENTIAL_OPTIONS,
    github_environment,
    verify_origin,
    workspace_environment,
)

__all__: Final[tuple[str, ...]] = ("changed_repositories", "publish_pull_requests")


def changed_repositories(
    workspace: AutomationWorkspace,
    runtime: DispatchRuntime,
) -> list[RepositoryWorkspace]:
    """Return repositories changed without agent-created commits."""

    environment = workspace_environment(workspace, runtime)
    changed: list[RepositoryWorkspace] = []

    for repository in workspace.repositories:
        verify_origin(repository, environment)
        current_commit = run_command(
            CommandRequest(
                command=["git", "rev-parse", "HEAD"],
                cwd=repository.path,
                environment=environment,
            )
        ).strip()

        if current_commit != repository.starting_commit:
            raise DispatchError(f"Codex created a commit in {repository.repository}")

        status = run_command(
            CommandRequest(
                command=["git", "status", "--porcelain"],
                cwd=repository.path,
                environment=environment,
            )
        )

        if status.strip():
            changed.append(repository)

    return changed


def publish_pull_requests(
    workspace: AutomationWorkspace,
    runtime: DispatchRuntime,
    result: AgentResult,
    changed: list[RepositoryWorkspace],
) -> list[PublishedPullRequest]:
    """Commit, push, and create or update pull requests for changed repositories."""

    metadata = {item.repository: item for item in result.repositories}
    environment = workspace_environment(workspace, runtime)
    github = github_environment(runtime)

    recovery = recovery_repositories(workspace, changed, github)
    repositories = [*changed, *recovery]

    for repository in changed:
        commit_repository(repository, metadata[repository.repository], environment)
        run_command(
            CommandRequest(
                command=[
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    *GIT_CREDENTIAL_OPTIONS,
                    "push",
                    f"https://github.com/{repository.repository}.git",
                    f"HEAD:refs/heads/{workspace.branch}",
                ],
                cwd=repository.path,
                environment=github,
            )
        )

    pull_requests: list[PublishedPullRequest] = []

    for repository in repositories:
        repository_metadata = metadata.get(repository.repository) or recovery_metadata(
            repository, environment
        )

        pull_requests.append(
            publish_pull_request(
                workspace,
                repository,
                repository_metadata,
                github,
            )
        )

    return pull_requests


def recovery_repositories(
    workspace: AutomationWorkspace,
    changed: list[RepositoryWorkspace],
    environment: CommandEnvironment,
) -> list[RepositoryWorkspace]:
    """Find previously pushed branches whose pull request was not created."""

    changed_names = {repository.repository for repository in changed}
    recovery: list[RepositoryWorkspace] = []

    for repository in workspace.repositories:
        if not repository.existing_branch or repository.repository in changed_names:
            continue

        existing = existing_pull_request(repository, workspace.branch, environment)

        if existing is None:
            recovery.append(repository)
        elif existing.state is not PullRequestState.OPEN:
            raise DispatchError(
                f"automation pull request for {repository.repository} is {existing.state.value.lower()}"
            )

    return recovery


def recovery_metadata(
    repository: RepositoryWorkspace, environment: CommandEnvironment
) -> PullRequestMetadata:
    """Build pull request metadata for a previously published branch."""

    title = run_command(
        CommandRequest(
            command=["git", "log", "-1", "--format=%s"],
            cwd=repository.path,
            environment=environment,
        )
    ).strip()

    return PullRequestMetadata(
        repository=repository.repository,
        title=title,
        body="This pull request completes a previously published Code Automations branch.",
    )


def commit_repository(
    repository: RepositoryWorkspace,
    metadata: PullRequestMetadata,
    environment: CommandEnvironment,
) -> None:
    """Commit all changes for one repository."""

    run_command(
        CommandRequest(
            command=["git", "-c", "core.hooksPath=/dev/null", "add", "--all"],
            cwd=repository.path,
            environment=environment,
        )
    )

    run_command(
        CommandRequest(
            command=["git", "-c", "core.hooksPath=/dev/null", "commit", "--no-verify", "-m", metadata.title],
            cwd=repository.path,
            environment=environment,
        )
    )


def publish_pull_request(
    workspace: AutomationWorkspace,
    repository: RepositoryWorkspace,
    metadata: PullRequestMetadata,
    environment: CommandEnvironment,
) -> PublishedPullRequest:
    """Create or update one pull request for a pushed automation branch."""

    body_path = workspace.root / f"{repository.repository.replace('/', '--')}.md"
    body_path.write_text(f"{metadata.body.rstrip()}\n\nGenerated by Code Automations.\n", encoding="utf-8")

    existing = existing_pull_request(repository, workspace.branch, environment)

    if existing is None:
        output = run_command(
            CommandRequest(
                command=[
                    "gh",
                    "pr",
                    "create",
                    "--repo",
                    repository.repository,
                    "--base",
                    repository.branch,
                    "--head",
                    workspace.branch,
                    "--title",
                    metadata.title,
                    "--body-file",
                    str(body_path),
                ],
                cwd=repository.path,
                environment=environment,
            )
        ).strip()

        return PublishedPullRequest(repository=repository.repository, url=output)

    if existing.state is not PullRequestState.OPEN:
        raise DispatchError(
            f"automation pull request for {repository.repository} is {existing.state.value.lower()}"
        )

    run_command(
        CommandRequest(
            command=[
                "gh",
                "pr",
                "edit",
                str(existing.url),
                "--repo",
                repository.repository,
                "--title",
                metadata.title,
                "--body-file",
                str(body_path),
            ],
            cwd=repository.path,
            environment=environment,
        )
    )

    return PublishedPullRequest(repository=repository.repository, url=existing.url)


def existing_pull_request(
    repository: RepositoryWorkspace,
    output_branch: str,
    environment: CommandEnvironment,
) -> ExistingPullRequest | None:
    """Find the sole pull request associated with one automation branch."""

    output = run_command(
        CommandRequest(
            command=[
                "gh",
                "pr",
                "list",
                "--repo",
                repository.repository,
                "--head",
                output_branch,
                "--state",
                "all",
                "--json",
                "url,state",
            ],
            cwd=repository.path,
            environment=environment,
        )
    )

    try:
        pull_requests = TypeAdapter(list[ExistingPullRequest]).validate_json(output)
    except ValidationError as error:
        raise DispatchError(f"unable to read existing pull requests: {error}") from error

    if len(pull_requests) > 1:
        raise DispatchError(f"multiple pull requests exist for {repository.repository} and {output_branch}")

    return pull_requests[0] if pull_requests else None
