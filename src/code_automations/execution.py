import json
from typing import Final

from pydantic import ValidationError

from code_automations.errors import DispatchError
from code_automations.models.execution import AgentResult, AutomationWorkspace
from code_automations.models.processes import CommandRequest
from code_automations.models.runtime import DispatchRuntime
from code_automations.processes import run_command

__all__: Final[tuple[str, ...]] = ("run_automation", "validate_agent_result")


def run_automation(workspace: AutomationWorkspace, runtime: DispatchRuntime, prompt: str) -> AgentResult:
    """Run one Codex session across every prepared repository."""

    schema_path = workspace.root / "result.schema.json"
    output_path = workspace.root / "result.json"
    schema_path.write_text(json.dumps(AgentResult.model_json_schema()), encoding="utf-8")

    command = [
        "codex",
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--sandbox",
        "workspace-write",
        "-C",
        str(workspace.repositories[0].path),
    ]

    for repository in workspace.repositories[1:]:
        command.extend(["--add-dir", str(repository.path)])

    command.extend(
        [
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
            "-",
        ]
    )

    environment = {
        "CODEX_HOME": str(runtime.codex_home),
        "HOME": runtime.home,
        "PATH": runtime.command_path,
    }
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
