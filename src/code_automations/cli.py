import argparse
import logging
import sys
from functools import partial
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter

from code_automations.configuration import load_configuration, validate_configuration
from code_automations.dispatching import dispatch_due, dispatch_target
from code_automations.errors import ConfigurationError, DispatchError
from code_automations.models.cli import CliArguments, DueRecord, DueRepository
from code_automations.models.dispatching import (
    DueAutomation,
    ExecutionRequest,
    ScheduledDispatch,
    SubmittedAutomation,
)
from code_automations.models.runtime import ActionsRuntime, resolve_dispatch_runtime
from code_automations.rendering import render_target
from code_automations.scheduling import due_automations
from code_automations.state import load_state
from code_automations.targets import (
    find_target,
    has_self_repository,
    resolve_self_repository,
    resolve_targets,
)
from code_automations.utils import parse_datetime

logger = logging.getLogger(__name__)

__all__: Final[tuple[str, ...]] = ("main",)


def write_summary(path: Path | None, submission: SubmittedAutomation) -> None:
    """Append an automation result to the GitHub Actions summary."""

    if path is None:
        return

    with path.open("a", encoding="utf-8") as summary:
        summary.write(f"## {submission.name}\n\n{submission.result.summary}\n\n")

        if submission.result.pull_requests:
            for pull_request in submission.result.pull_requests:
                summary.write(f"- [{pull_request.repository}]({pull_request.url})\n")
        else:
            summary.write("- No repository changes\n")


def report_submission(path: Path | None, submission: SubmittedAutomation) -> None:
    """Report one completed automation to logs and the Actions summary."""

    write_summary(path, submission)

    for pull_request in submission.result.pull_requests:
        logger.info(pull_request.url)


def due_payload(items: list[DueAutomation]) -> str:
    """Serialize due automations for inspection."""

    records = [
        DueRecord(
            automation=item.target.name,
            project=item.target.project,
            repositories=[
                DueRepository(repository=repository.repository, branch=repository.branch)
                for repository in item.target.repositories
            ],
            scheduled_for=item.scheduled_for,
        )
        for item in items
    ]

    return TypeAdapter(list[DueRecord]).dump_json(records, indent=2).decode()


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""

    parser = argparse.ArgumentParser(prog="code-automations")
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

    runtime = ActionsRuntime()
    summary_path = Path(runtime.github_step_summary) if runtime.github_step_summary else None

    if arguments.command == "validate":
        validate_configuration(arguments.config, runtime.github_repository)

        logger.info("Configuration is valid.")

        return 0

    loaded = load_configuration(arguments.config)
    self_repository = (
        resolve_self_repository(loaded.root, runtime.github_repository)
        if has_self_repository(loaded)
        else None
    )

    if arguments.command == "render":
        if arguments.automation is None:
            raise ConfigurationError("render requires an automation name")

        target = find_target(loaded, self_repository, arguments.automation)
        logger.info(render_target(loaded, target).removesuffix("\n"))

        return 0

    state = load_state(arguments.state)
    now = parse_datetime(arguments.now)

    if arguments.command == "due":
        logger.info(due_payload(due_automations(resolve_targets(loaded, self_repository), state, now)))

        return 0

    dispatch_runtime = resolve_dispatch_runtime(runtime)

    if arguments.automation is not None:
        target = find_target(loaded, self_repository, arguments.automation)
        result = dispatch_target(ExecutionRequest(loaded=loaded, target=target), dispatch_runtime)
        submission = SubmittedAutomation(name=target.name, result=result)

        report_submission(summary_path, submission)

        return 0

    if not arguments.scheduled or arguments.state is None:
        raise ConfigurationError("scheduled dispatch requires --state")

    due = due_automations(resolve_targets(loaded, self_repository), state, now)
    scheduled_dispatch = ScheduledDispatch(
        loaded=loaded,
        due=due,
        state=state,
        state_path=arguments.state,
    )

    dispatch_due(
        scheduled_dispatch,
        dispatch_runtime,
        submission_handler=partial(report_submission, summary_path),
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
