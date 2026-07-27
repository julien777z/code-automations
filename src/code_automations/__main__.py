import argparse
import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from code_automations.cloud import submit_cloud_task, wait_for_cloud_task
from code_automations.configuration import (
    find_target,
    load_configuration,
    resolve_self_repository,
    resolve_targets,
    validate_configuration,
)
from code_automations.errors import ConfigurationError, DispatchError
from code_automations.models.configuration import AutomationTarget, LoadedConfiguration
from code_automations.models.runtime import ActionsContext, CliArguments, CloudTask
from code_automations.rendering import render_target
from code_automations.scheduling import dispatcher_occurrence, due_automations

logger = logging.getLogger(__name__)

__all__: Final[tuple[str, ...]] = ("main", "run")


def parse_datetime(value: str | None) -> datetime:
    """Parse one timezone-aware timestamp or return the current instant."""

    if value is None:
        return datetime.now(UTC)

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ConfigurationError(f"invalid timestamp: {value}") from error

    if parsed.tzinfo is None:
        raise ConfigurationError("timestamps must include a timezone offset")

    return parsed.astimezone(UTC)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""

    parser = argparse.ArgumentParser(prog="code-automations")
    parser.add_argument("--config", type=Path, default=Path("automations.yaml"))
    parser.add_argument("--prompts-directory", type=Path, required=True)

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")

    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("automation")

    due_parser = subparsers.add_parser("due")
    due_parser.add_argument("--now")
    due_parser.add_argument("--dispatcher-schedule")

    dispatch_parser = subparsers.add_parser("dispatch")
    selection = dispatch_parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--automation")
    selection.add_argument("--scheduled", action="store_true")
    dispatch_parser.add_argument("--now")
    dispatch_parser.add_argument("--dispatcher-schedule")
    dispatch_parser.add_argument("--environment", required=True)
    dispatch_parser.add_argument("--branch", required=True)
    dispatch_parser.add_argument("--task-timeout-minutes", type=int, default=150)

    return parser


def report_task(summary_path: Path | None, name: str, task: CloudTask) -> None:
    """Report a submitted task to logs and the Actions summary."""

    logger.info(task.url)

    if summary_path is None:
        return

    with summary_path.open("a", encoding="utf-8") as summary:
        summary.write(f"## {name}\n\n- [Codex Cloud task]({task.url})\n")


def submit_target(
    loaded: LoadedConfiguration,
    target: AutomationTarget,
    environment: str,
    branch: str,
    timeout: timedelta,
    summary_path: Path | None,
) -> None:
    """Submit and monitor one configured automation target."""

    task = submit_cloud_task(
        environment,
        branch,
        render_target(loaded, target),
        target.automation.model,
    )

    report_task(summary_path, target.name, task)
    wait_for_cloud_task(task, timeout)


def run(arguments: CliArguments) -> int:
    """Run a parsed CLI command."""

    context = ActionsContext()

    if arguments.command == "validate":
        validate_configuration(arguments.config, arguments.prompts_directory, context.github_repository)

        logger.info("Configuration is valid.")

        return 0

    loaded = load_configuration(arguments.config, arguments.prompts_directory)
    self_repository = resolve_self_repository(loaded, context.github_repository)

    if arguments.command == "render":
        if arguments.automation is None:
            raise ConfigurationError("render requires an automation name")

        target = find_target(loaded, self_repository, arguments.automation)
        logger.info(render_target(loaded, target).removesuffix("\n"))

        return 0

    now = parse_datetime(arguments.now)
    occurrence = (
        dispatcher_occurrence(arguments.dispatcher_schedule, now) if arguments.dispatcher_schedule else now
    )
    targets = resolve_targets(loaded, self_repository)

    if arguments.command == "due":
        due = due_automations(targets, occurrence)
        logger.info(
            json.dumps(
                [
                    {
                        "automation": item.name,
                        "scheduled_for": item.scheduled_for.isoformat(),
                    }
                    for item in due
                ],
                indent=2,
            )
        )

        return 0

    if arguments.environment is None or arguments.branch is None:
        raise ConfigurationError("dispatch requires a Cloud environment and branch")

    timeout = timedelta(minutes=arguments.task_timeout_minutes)

    if timeout <= timedelta(0):
        raise ConfigurationError("task timeout must be positive")

    selected_targets = (
        [find_target(loaded, self_repository, arguments.automation)]
        if arguments.automation is not None
        else [find_target(loaded, self_repository, due.name) for due in due_automations(targets, occurrence)]
    )

    for target in selected_targets:
        submit_target(
            loaded,
            target,
            arguments.environment,
            arguments.branch,
            timeout,
            context.github_step_summary,
        )

    return 0


def main() -> int:
    """Run the code-automations CLI."""

    logging.basicConfig(format="%(message)s", level=logging.INFO, stream=sys.stdout)

    arguments = CliArguments.model_validate(vars(build_parser().parse_args()))

    try:
        return run(arguments)
    except (ConfigurationError, DispatchError, ValueError) as error:
        logger.error(error)

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
