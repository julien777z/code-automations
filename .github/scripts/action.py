import argparse
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

ACTION_COMMANDS: Final[tuple[str, ...]] = (
    "cleanup-authentication",
    "dispatch",
    "install-dependencies",
    "read-node-version",
    "setup-authentication",
    "validate-inputs",
)


def environment_value(name: str) -> str:
    """Read one action environment value."""

    return os.environ.get(name, "")


def write_github_output(name: str, value: str) -> None:
    """Write one action output."""

    output_path = Path(environment_value("GITHUB_OUTPUT"))

    with output_path.open("a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")


def validate_inputs() -> None:
    """Validate action mode, event, credentials, and resource paths."""

    mode = environment_value("AUTOMATION_MODE")
    event_name = environment_value("GITHUB_EVENT_NAME")

    match mode:
        case "validate":
            pass
        case "dispatch":
            if event_name == "schedule":
                expected_ref = f"refs/heads/{environment_value('DEFAULT_BRANCH')}"

                if environment_value("GITHUB_REF") != expected_ref:
                    raise ValueError("scheduled dispatch is only allowed from the default branch")
            elif event_name != "workflow_dispatch":
                raise ValueError("dispatch is only allowed for scheduled and manual workflow runs")

            if not environment_value("CODEX_AUTH_JSON"):
                raise ValueError("codex-auth-json is required in dispatch mode")

            if not environment_value("CODEX_ENVIRONMENT_ID"):
                raise ValueError("codex-environment-id is required in dispatch mode")
        case _:
            raise ValueError("mode must be validate or dispatch")

    workspace_root = Path(environment_value("GITHUB_WORKSPACE")).resolve()
    resources = (
        ("automation file", environment_value("AUTOMATIONS_FILE_PATH"), False),
        ("prompt directory", environment_value("PROMPTS_DIRECTORY_PATH"), True),
    )

    for label, configured_path, is_directory in resources:
        resolved_path = (workspace_root / configured_path).resolve()

        if resolved_path == workspace_root or not resolved_path.is_relative_to(workspace_root):
            raise ValueError("automation resources must resolve inside the checked-out repository")

        if is_directory and not resolved_path.is_dir():
            raise ValueError(f"{label} does not exist: {configured_path}")

        if not is_directory and not resolved_path.is_file():
            raise ValueError(f"{label} does not exist: {configured_path}")

    subprocess.run(
        ["git", "config", "--local", "--unset-all", "http.https://github.com/.extraheader"],
        check=False,
    )


def read_node_version() -> None:
    """Expose the action-owned Node.js version."""

    action_path = Path(environment_value("GITHUB_ACTION_PATH"))
    version = (action_path / ".nvmrc").read_text(encoding="utf-8").strip()

    write_github_output("version", version)


def install_dependencies() -> None:
    """Install the action runtime dependencies."""

    action_path = environment_value("GITHUB_ACTION_PATH")

    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "poetry==2.2.0"],
        check=True,
    )
    subprocess.run(["poetry", "--directory", action_path, "install", "--only", "main"], check=True)
    subprocess.run(["npm", "ci", "--omit=dev", "--prefix", action_path], check=True)


def setup_authentication() -> None:
    """Write Codex authentication to a locked-down temporary directory."""

    authentication_home = Path(environment_value("RUNNER_TEMP")) / "automation-authentication"
    authentication_home.mkdir(mode=0o700, parents=True, exist_ok=True)
    authentication_home.chmod(0o700)

    authentication_path = authentication_home / "auth.json"
    descriptor = os.open(authentication_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)

    with os.fdopen(descriptor, "w", encoding="utf-8") as authentication_file:
        authentication_file.write(environment_value("CODEX_AUTH_JSON"))

    write_github_output("home", str(authentication_home))


def dispatch() -> None:
    """Dispatch one selected or scheduled automation."""

    action_path = environment_value("GITHUB_ACTION_PATH")
    environment = os.environ.copy()
    environment["PATH"] = f"{action_path}/node_modules/.bin{os.pathsep}{environment['PATH']}"
    command = [
        "poetry",
        "--directory",
        action_path,
        "run",
        "python",
        "-m",
        "code_automations",
        "--config",
        f"{environment_value('GITHUB_WORKSPACE')}/{environment_value('AUTOMATIONS_FILE_PATH')}",
        "--prompts-directory",
        f"{environment_value('GITHUB_WORKSPACE')}/{environment_value('PROMPTS_DIRECTORY_PATH')}",
        "dispatch",
        "--environment",
        environment_value("CODEX_ENVIRONMENT_ID"),
        "--branch",
        environment_value("GITHUB_REF_NAME"),
    ]
    automation = environment_value("RUN_AUTOMATION")

    if automation:
        command.extend(["--automation", automation])
    else:
        command.append("--scheduled")
        dispatcher_schedule = environment_value("GITHUB_EVENT_SCHEDULE")

        if dispatcher_schedule:
            command.extend(["--dispatcher-schedule", dispatcher_schedule])

    subprocess.run(command, env=environment, check=True)


def cleanup_authentication() -> None:
    """Remove the temporary Codex authentication directory."""

    configured_home = environment_value("AUTHENTICATION_HOME")

    if not configured_home:
        return

    runner_temp = Path(environment_value("RUNNER_TEMP")).resolve()
    authentication_home = Path(configured_home).resolve()

    if authentication_home == runner_temp or not authentication_home.is_relative_to(runner_temp):
        raise ValueError("authentication directory must resolve inside the runner temporary directory")

    if authentication_home.exists():
        shutil.rmtree(authentication_home)


if __name__ == "__main__":
    logging.basicConfig(format="%(message)s", level=logging.INFO, stream=sys.stdout)

    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=ACTION_COMMANDS)
    arguments = parser.parse_args()

    try:
        match arguments.command:
            case "cleanup-authentication":
                cleanup_authentication()
            case "dispatch":
                dispatch()
            case "install-dependencies":
                install_dependencies()
            case "read-node-version":
                read_node_version()
            case "setup-authentication":
                setup_authentication()
            case "validate-inputs":
                validate_inputs()
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        logger.error(error)

        raise SystemExit(1) from error
