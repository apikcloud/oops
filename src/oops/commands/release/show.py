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
from oops.commands.base import command, render_and_exit
from oops.core.logger import live_progress
from oops.core.metadata import get_metadata
from oops.core.models import Result
from oops.output.formatters import (
    FormatterRegistry,
    JsonFormatter,
    OutputFormatter,
    SimpleSummaryConsoleFormatter,
    SpaReportFormatter,
)
from oops.services.git import require_repository
from oops.utils.versioning import count_release_types, read_releases

from .presenters.show import ShowPresenter

FORMATTERS: FormatterRegistry = {
    "text": SimpleSummaryConsoleFormatter,
    "json": JsonFormatter,
    "html": SpaReportFormatter,
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

    metadata = get_metadata()

    formatter: OutputFormatter = FORMATTERS[output_format]()
    result: Result[dict] = Result()
    result.data = {"releases": [], "metrics": {}}

    # 1. Long-running processing — produces a typed Result of domain dataclasses.

    with live_progress("Reading project releases..."):
        releases: Result = read_releases(repo, changelog=True)
        result.merge(releases)

        if not releases.data:
            result.add_error("No releases found.")

        first_release = releases.data[-1].date if releases.data else None
        last_release = releases.data[0].date if releases.data else None
        delta = (last_release - first_release).days if first_release and last_release else None

        result.data["releases"] = releases.data or []
        result.data["metrics"] = {
            "total": len(releases.data or []),
            "commits": sum(item.commits for item in releases.data or []),
            "first_release": first_release,
            "last_release": last_release,
            "delta": delta,
            "types": count_release_types(releases.data or []),
        }

    # 2. Presenter prepares neutral dicts according to the formatter's audience.
    output = ShowPresenter().prepare(result, target=formatter.target, metadata=metadata)
    render_and_exit(result, formatter, output, output_format, output_path)
