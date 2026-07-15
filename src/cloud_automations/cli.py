import argparse
import logging
import sys
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter

from cloud_automations.configuration import (
    find_target,
    load_configuration,
    resolve_self_repository,
    targets,
    validate_repository,
)
from cloud_automations.dispatching import (
    ScheduledDispatch,
    SubmittedAutomation,
    dispatch_due,
    dispatch_target,
)
from cloud_automations.errors import ConfigurationError, DispatchError
from cloud_automations.models.cli import CliArguments, DueRecord
from cloud_automations.models.runtime import GitHubRuntime
from cloud_automations.rendering import render_target
from cloud_automations.scheduling import DueAutomation, due_automations
from cloud_automations.state import load_state
from cloud_automations.utils import parse_datetime

__all__: Final[tuple[str, ...]] = ("main",)

logger = logging.getLogger(__name__)


def write_summary(path: Path | None, submission: SubmittedAutomation) -> None:
    """Append a submitted task link to the GitHub Actions summary."""

    if path is not None:
        with path.open("a", encoding="utf-8") as summary:
            summary.write(f"- [{submission.name}]({submission.result.task_url})\n")


def due_payload(items: list[DueAutomation]) -> str:
    """Serialize due automations for inspection."""

    records = [
        DueRecord(
            automation=item.target.name,
            repository=item.target.repository,
            branch=item.target.branch,
            environment=item.target.environment,
            scheduled_for=item.scheduled_for,
        )
        for item in items
    ]

    return TypeAdapter(list[DueRecord]).dump_json(records, indent=2).decode()


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""

    parser = argparse.ArgumentParser(prog="cloud-automations")
    parser.add_argument("--config", type=Path, default=Path("automations.yaml"))

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")

    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("automation")

    due_parser = subparsers.add_parser("due")
    due_parser.add_argument("--state", type=Path)
    due_parser.add_argument("--now")

    dispatch_parser = subparsers.add_parser("dispatch")
    selection = dispatch_parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--automation")
    selection.add_argument("--scheduled", action="store_true")
    dispatch_parser.add_argument("--state", type=Path)
    dispatch_parser.add_argument("--now")

    return parser


def run(arguments: CliArguments) -> int:
    """Run a parsed CLI command."""

    runtime = GitHubRuntime()
    summary_path = Path(runtime.github_step_summary) if runtime.github_step_summary else None

    if arguments.command == "validate":
        validate_repository(arguments.config, arguments.config.resolve().parent / "automations.schema.json")

        logger.info("Configuration is valid.")

        return 0

    loaded = load_configuration(arguments.config)
    self_repository = resolve_self_repository(loaded.root, runtime.github_repository)

    if arguments.command == "render":
        if arguments.automation is None:
            raise ConfigurationError("render requires an automation name")

        target = find_target(loaded, self_repository, arguments.automation)
        logger.info(render_target(loaded, target).removesuffix("\n"))

        return 0

    state = load_state(arguments.state)
    now = parse_datetime(arguments.now)

    if arguments.command == "due":
        logger.info(due_payload(due_automations(targets(loaded, self_repository), state, now)))

        return 0

    if arguments.automation is not None:
        target = find_target(loaded, self_repository, arguments.automation)
        result = dispatch_target(loaded, target)
        submission = SubmittedAutomation(name=target.name, result=result)

        write_summary(summary_path, submission)

        logger.info(result.task_url)

        return 0

    if not arguments.scheduled or arguments.state is None:
        raise ConfigurationError("scheduled dispatch requires --state")

    due = due_automations(targets(loaded, self_repository), state, now)
    scheduled_dispatch = ScheduledDispatch(
        loaded=loaded,
        due=due,
        state=state,
        state_path=arguments.state,
    )

    outcome = dispatch_due(scheduled_dispatch)

    for submission in outcome.submissions:
        write_summary(summary_path, submission)

        logger.info(submission.result.task_url)

    if outcome.failures:
        raise DispatchError("; ".join(outcome.failures))

    return 0


def configure_logging() -> None:
    """Configure command-line output logging."""

    logging.basicConfig(format="%(message)s", level=logging.INFO, stream=sys.stdout)


def main() -> int:
    """Run the cloud-automations CLI."""

    configure_logging()

    arguments = CliArguments.model_validate(vars(build_parser().parse_args()))

    try:
        return run(arguments)
    except (ConfigurationError, DispatchError, ValueError) as error:
        logger.error(error)

        return 1
