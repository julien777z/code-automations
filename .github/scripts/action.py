import argparse
import logging
import os
import shutil
import subprocess
import sys
from typing import Final

from config import AuthenticationConfig, CleanupConfig, DispatchConfig, ValidationConfig
from pydantic import ValidationError

logger = logging.getLogger(__name__)

ACTION_COMMANDS: Final[tuple[str, ...]] = (
    "cleanup-runtime",
    "dispatch",
    "setup-authentication",
    "validate-inputs",
)


def validate_inputs() -> None:
    """Validate action mode, event, credentials, and resource paths."""

    config = ValidationConfig()
    workspace_root = config.github_workspace.resolve()
    resources = (
        ("automation file", config.automations_file_path, False),
        ("prompt directory", config.prompts_directory_path, True),
    )

    for label, configured_path, is_directory in resources:
        resolved_path = (workspace_root / configured_path).resolve()

        if resolved_path == workspace_root or not resolved_path.is_relative_to(workspace_root):
            raise ValueError("automation resources must resolve inside the checked-out repository")

        if is_directory and not resolved_path.is_dir():
            raise ValueError(f"{label} does not exist: {configured_path.as_posix()}")

        if not is_directory and not resolved_path.is_file():
            raise ValueError(f"{label} does not exist: {configured_path.as_posix()}")

    subprocess.run(
        ["git", "config", "--local", "--unset-all", "http.https://github.com/.extraheader"],
        check=False,
    )


def setup_authentication() -> None:
    """Write Codex authentication to a locked-down temporary directory."""

    config = AuthenticationConfig()
    authentication_home = config.runner_temp / "automation-authentication"
    authentication_home.mkdir(mode=0o700, parents=True, exist_ok=True)
    authentication_home.chmod(0o700)

    authentication_path = authentication_home / "auth.json"
    descriptor = os.open(authentication_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)

    with os.fdopen(descriptor, "w", encoding="utf-8") as authentication_file:
        authentication_file.write(config.codex_auth_json.get_secret_value())

    with config.github_output.open("a", encoding="utf-8") as output:
        output.write(f"home={authentication_home}\n")


def dispatch() -> None:
    """Dispatch one selected or scheduled automation."""

    config = DispatchConfig()
    os.environ["PATH"] = f"{config.github_action_path}/node_modules/.bin{os.pathsep}{config.path}"
    command = [
        "poetry",
        "--directory",
        str(config.github_action_path),
        "run",
        "python",
        "-m",
        "code_automations",
        "--config",
        str(config.github_workspace / config.automations_file_path),
        "--prompts-directory",
        str(config.github_workspace / config.prompts_directory_path),
        "dispatch",
        "--workspace",
        str(config.runner_temp / "code-automations-workspace"),
        "--agent-home",
        str(config.codex_home),
    ]

    if config.run_automation:
        command.extend(["--automation", config.run_automation])
    else:
        command.append("--scheduled")

        if config.github_event_schedule:
            command.extend(["--dispatcher-schedule", config.github_event_schedule])

    subprocess.run(command, check=True)


def cleanup_runtime() -> None:
    """Remove temporary automation runtime directories."""

    config = CleanupConfig()

    runner_temp = config.runner_temp.resolve()

    for configured_path in (config.authentication_home, config.automation_workspace):
        if configured_path is None:
            continue

        runtime_path = configured_path.resolve()

        if runtime_path == runner_temp or not runtime_path.is_relative_to(runner_temp):
            raise ValueError("runtime directory must resolve inside the runner temporary directory")

        if runtime_path.exists():
            shutil.rmtree(runtime_path)


if __name__ == "__main__":
    logging.basicConfig(format="%(message)s", level=logging.INFO, stream=sys.stdout)

    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=ACTION_COMMANDS)
    arguments = parser.parse_args()

    try:
        match arguments.command:
            case "cleanup-runtime":
                cleanup_runtime()
            case "dispatch":
                dispatch()
            case "setup-authentication":
                setup_authentication()
            case "validate-inputs":
                validate_inputs()
    except (OSError, subprocess.CalledProcessError, ValidationError, ValueError) as error:
        logger.error(error)

        raise SystemExit(1) from error
