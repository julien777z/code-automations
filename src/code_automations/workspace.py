import logging
import re
import tempfile
from datetime import UTC
from hashlib import sha256
from pathlib import Path
from typing import Final

from code_automations.errors import DispatchError
from code_automations.models.dispatching import ExecutionRequest
from code_automations.models.execution import AutomationWorkspace, RepositoryWorkspace
from code_automations.models.processes import CommandEnvironment, CommandRequest
from code_automations.models.runtime import DispatchRuntime
from code_automations.processes import run_command

logger = logging.getLogger(__name__)

__all__: Final[tuple[str, ...]] = (
    "GIT_CREDENTIAL_OPTIONS",
    "create_workspace",
    "github_environment",
    "output_branch",
    "verify_origin",
    "workspace_environment",
)

GIT_AUTHOR_NAME: Final[str] = "github-actions[bot]"
GIT_AUTHOR_EMAIL: Final[str] = "41898282+github-actions[bot]@users.noreply.github.com"
GIT_CREDENTIAL_OPTIONS: Final[tuple[str, ...]] = (
    "-c",
    "credential.helper=",
    "-c",
    "credential.https://github.com.helper=!gh auth git-credential",
)
GITHUB_ORIGIN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9._-]+/[A-Za-z0-9._-]+?)(?:\.git)?$"
)


def github_environment(runtime: DispatchRuntime) -> CommandEnvironment:
    """Build the restricted environment for GitHub CLI and Git commands."""

    return CommandEnvironment(
        GH_TOKEN=runtime.github_token,
        HOME=str(runtime.github_home),
        PATH=runtime.command_path,
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_NOSYSTEM="1",
    )


def workspace_environment(workspace: AutomationWorkspace, runtime: DispatchRuntime) -> CommandEnvironment:
    """Build the uncredentialed environment for agent-owned repository operations."""

    return CommandEnvironment(
        HOME=str(workspace.home),
        PATH=runtime.command_path,
    )


def output_branch(request: ExecutionRequest, runtime: DispatchRuntime) -> str:
    """Build a unique branch shared by every repository in one action attempt."""

    occurrence = (
        request.scheduled_for.astimezone(UTC).isoformat() if request.scheduled_for is not None else "manual"
    )

    branch_key = ":".join(
        (
            runtime.github_run_id,
            runtime.github_run_attempt,
            request.target.name,
            occurrence,
        )
    )

    branch_hash = sha256(branch_key.encode()).hexdigest()[:16]

    return f"automation/{request.target.name}/{branch_hash}"


def create_workspace(request: ExecutionRequest, runtime: DispatchRuntime) -> AutomationWorkspace:
    """Clone and prepare every repository for one automation execution."""

    root = Path(tempfile.mkdtemp(prefix=f"{request.target.name}-", dir=runtime.runner_temp))
    home = root / "home"
    home.mkdir(mode=0o700)

    branch = output_branch(request, runtime)
    environment = github_environment(runtime)

    repositories: list[RepositoryWorkspace] = []

    for index, repository in enumerate(request.target.repositories, start=1):
        path = root / f"{index}-{repository.repository.replace('/', '--')}"

        run_command(
            CommandRequest(
                command=[
                    "git",
                    *GIT_CREDENTIAL_OPTIONS,
                    "clone",
                    "--branch",
                    repository.branch,
                    "--single-branch",
                    f"https://github.com/{repository.repository}.git",
                    str(path),
                ],
                cwd=root,
                environment=environment,
            )
        )

        prepare_branch(path, repository.branch, branch, environment)

        starting_commit = run_command(
            CommandRequest(
                command=["git", "rev-parse", "HEAD"],
                cwd=path,
                environment=environment,
            )
        ).strip()

        repositories.append(
            RepositoryWorkspace(
                repository=repository.repository,
                branch=repository.branch,
                path=path,
                starting_commit=starting_commit,
            )
        )

    return AutomationWorkspace(root=root, home=home, branch=branch, repositories=repositories)


def prepare_branch(
    path: Path,
    base_branch: str,
    output: str,
    environment: CommandEnvironment,
) -> None:
    """Create an automation branch when its remote name is available."""

    branch_exists = run_command(
        CommandRequest(
            command=["git", *GIT_CREDENTIAL_OPTIONS, "ls-remote", "--heads", "origin", output],
            cwd=path,
            environment=environment,
        )
    ).strip()

    if branch_exists:
        raise DispatchError(f"automation branch already exists: {output}")

    run_command(
        CommandRequest(
            command=["git", "checkout", "-b", output, f"origin/{base_branch}"],
            cwd=path,
            environment=environment,
        )
    )

    run_command(
        CommandRequest(
            command=["git", "config", "user.name", GIT_AUTHOR_NAME],
            cwd=path,
            environment=environment,
        )
    )

    run_command(
        CommandRequest(
            command=["git", "config", "user.email", GIT_AUTHOR_EMAIL],
            cwd=path,
            environment=environment,
        )
    )


def verify_origin(repository: RepositoryWorkspace, environment: CommandEnvironment) -> None:
    """Require the repository origin to remain its configured GitHub remote."""

    origin = run_command(
        CommandRequest(
            command=["git", "remote", "get-url", "origin"],
            cwd=repository.path,
            environment=environment,
        )
    ).strip()

    match = GITHUB_ORIGIN_PATTERN.fullmatch(origin)

    if match is None or match.group(1).casefold() != repository.repository.casefold():
        raise DispatchError(f"repository origin changed for {repository.repository}")
