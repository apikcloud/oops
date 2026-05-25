# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: show.py — oops/commands/release/show.py

"""
List all releases (semver tags) with their date and commit count.

Shows each vX.Y.Z tag sorted from newest to oldest, with the tag date,
author, and the number of commits between that release and the previous one.
"""

from pathlib import Path

import click
from oops.commands.base import command
from oops.core.exceptions import NotFoundError
from oops.core.logger import live_progress
from oops.core.models import Result
from oops.output.formatters import (
    FormatterRegistry,
    JsonFormatter,
    OutputFormatter,
    ReleasesReportFormatter,
    SimpleSummaryConsoleFormatter,
)
from oops.output.sinks import deliver
from oops.services.git import require_repository
from oops.utils.versioning import count_release_types, read_releases

from .presenters.show import prepare

FORMATTERS: FormatterRegistry = {
    "text": SimpleSummaryConsoleFormatter,
    "json": JsonFormatter,
    "html": ReleasesReportFormatter,
}


@command(name="show", help=__doc__)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "html"]),
    default="text",
    show_default=True,
    help="Output format. 'json' is suited for downstream LLM agent consumption.",
)
@click.option(
    "--output-path",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the output to this path instead of stdout (json) or a temp file (html).",
)
def main(output_format: str, output_path: Path):
    repo, _ = require_repository()

    formatter: OutputFormatter = FORMATTERS[output_format]()
    outer: Result[None] = Result()

    # 1. Long-running processing — produces a typed Result of domain dataclasses.

    with live_progress("Reading project releases..."):
        result: Result = read_releases(repo, changelog=True)

        if not result.data:
            raise NotFoundError("No releases found.")
        releases = result.data

        stats: Result = Result(
            {
                "total": len(releases),
                "commits": sum(item.commits for item in releases),
                "first_release": releases[-1].date,
                "last_release": releases[0].date,
                "delta": (releases[0].date - releases[-1].date).days,
                "types": count_release_types(releases),
            }
        )

    # 2. Presenter prepares neutral dicts according to the formatter's audience.
    output = prepare(result, stats, outer, target=formatter.target)
    deliver(formatter, output, output_format, output_path)
