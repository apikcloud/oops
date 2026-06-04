# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: check.py — oops/commands/requirements/check.py

"""
Check the differences between the existing requirements and the expected ones.

The expected requirements are computed by scanning every root addon manifest and
collecting their ``external_dependencies["python"]`` entries.

In case of changes, it will be displayed like this:

    Changes for requirements.txt:

    - astor
    + pandas
    + python-stdnum
    - pytz
    + pytz==2023.3

See the requirements documentation for merging rules
and name-mapping details.
"""

from __future__ import annotations

from pathlib import Path

import click
from oops.commands.base import command, render_and_exit
from oops.core.checks import CheckOutcome
from oops.core.config import config
from oops.core.metadata import get_metadata
from oops.core.models import ResultCollection
from oops.output.formatters import (
    FormatterRegistry,
    JsonFormatter,
    OutputFormatter,
    PreCommitFormatter,
    SimpleSummaryConsoleFormatter,
)
from oops.output.presenters import DefaultCheckPresenter
from oops.services.git import require_repository

from .common import ImportsCheck, RequirementsCheck, RequirementsCheckContext

FORMATTERS: FormatterRegistry = {
    "text": SimpleSummaryConsoleFormatter,
    "json": JsonFormatter,
}


@command(name="check", help=__doc__)
@click.option(
    "--no-fail",
    is_flag=True,
    default=False,
    help="Exit 0 even when changes are detected.",
)
@click.option(
    "--hook",
    is_flag=True,
    help="Minimal output for pre-commit hooks.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format",
)
@click.option(
    "--output-path",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the output to this path instead of stdout (json) or a temp file (html).",
)
def main(no_fail: bool, hook: bool, output_format: str, output_path: Path):

    metadata = get_metadata()

    _, repo_path = require_repository()

    formatter: OutputFormatter = FORMATTERS[output_format]()
    if hook:
        formatter = PreCommitFormatter()

    results: ResultCollection[CheckOutcome] = ResultCollection(title="Check Requirements")

    ctx: RequirementsCheckContext = RequirementsCheckContext(
        requirement_file=Path(config.project.file_requirements),
        path=repo_path,
        enabled=["external_dep"],
    )

    # TODO: add a test to identify dependencies that cannot be resolved by the algorithm
    results.add(RequirementsCheck(ctx).run())
    results.add(ImportsCheck(ctx).run())

    results.aggregate()

    output = DefaultCheckPresenter().prepare(results, target=formatter.target, metadata=metadata)
    render_and_exit(results, formatter, output, output_format, output_path, bypass=no_fail)
