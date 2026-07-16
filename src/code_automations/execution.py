import json
import logging
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from code_automations.errors import DispatchError
from code_automations.models.execution import AgentResult, AutomationWorkspace, RepositoryWorkspace
from code_automations.models.processes import CommandEnvironment, CommandRequest
from code_automations.models.runtime import DispatchRuntime
from code_automations.processes import run_command

logger = logging.getLogger(__name__)

__all__: Final[tuple[str, ...]] = (
    "container_repositories",
    "run_automation",
    "validate_agent_result",
)

CONTAINER_AUTH_HOME: Final[Path] = Path("/codex-home")
CONTAINER_WORKSPACE: Final[Path] = Path("/workspace")


def container_path(workspace: AutomationWorkspace, path: Path) -> Path:
    """Translate an automation workspace path to its container path."""

    return CONTAINER_WORKSPACE / path.relative_to(workspace.root)


def container_repositories(workspace: AutomationWorkspace) -> list[RepositoryWorkspace]:
    """Map repository workspaces to their paths inside the agent container."""

    return [
        repository.model_copy(update={"path": container_path(workspace, repository.path)})
        for repository in workspace.repositories
    ]


def run_automation(workspace: AutomationWorkspace, runtime: DispatchRuntime, prompt: str) -> AgentResult:
    """Run one Codex session across every prepared repository."""

    schema_path = workspace.root / "result.schema.json"
    output_path = workspace.root / "result.json"
    schema_path.write_text(json.dumps(AgentResult.model_json_schema()), encoding="utf-8")

    command = [
        "docker",
        "run",
        "--rm",
        "--init",
        "--interactive",
        "--user",
        runtime.runner_user,
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--read-only",
        "--pids-limit=256",
        "--network=bridge",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=512m",
        "--mount",
        f"type=bind,source={workspace.root},target={CONTAINER_WORKSPACE}",
        "--mount",
        f"type=bind,source={runtime.codex_home},target={CONTAINER_AUTH_HOME}",
        "--env",
        f"CODEX_HOME={CONTAINER_AUTH_HOME}",
        "--env",
        f"HOME={container_path(workspace, workspace.home)}",
        runtime.runner_image,
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--sandbox",
        "workspace-write",
        "-C",
        str(container_path(workspace, workspace.repositories[0].path)),
    ]

    for repository in workspace.repositories[1:]:
        command.extend(["--add-dir", str(container_path(workspace, repository.path))])

    command.extend(
        [
            "--output-schema",
            str(container_path(workspace, schema_path)),
            "--output-last-message",
            str(container_path(workspace, output_path)),
            "-",
        ]
    )

    environment = CommandEnvironment(
        HOME=str(workspace.home),
        PATH=runtime.command_path,
    )

    run_command(
        CommandRequest(
            command=command,
            cwd=workspace.root,
            environment=environment,
            input_text=prompt,
        )
    )

    try:
        return AgentResult.model_validate_json(output_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValidationError) as error:
        raise DispatchError(f"Codex did not produce a valid structured result: {error}") from error


def validate_agent_result(result: AgentResult, changed_repositories: list[str]) -> None:
    """Require result metadata to exactly describe changed repositories."""

    result_repositories = [metadata.repository for metadata in result.repositories]

    if len(result_repositories) != len(set(result_repositories)):
        raise DispatchError("Codex returned duplicate pull request metadata")

    if set(result_repositories) != set(changed_repositories):
        raise DispatchError("Codex result repositories do not exactly match repositories with changes")
