# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: show.py — oops/commands/submodules/show.py

"""
Display a table of all submodules with their details.

Shows name, URL, upstream branch, pull-request flag, last commit date,
commit age, and SHA for each submodule. Filter to PR-only submodules
with --pull-request.
"""

from pathlib import Path

import click
from oops.commands.base import command, render_and_exit
from oops.core.logger import live_progress, log
from oops.core.metadata import get_metadata
from oops.core.models import Result, SubmoduleInfo
from oops.output.formatters import (
    FormatterRegistry,
    JsonFormatter,
    OutputFormatter,
    SimpleSummaryConsoleFormatter,
)
from oops.services.git import get_last_commit, is_pull_request, require_repository, require_submodules
from oops.utils.net import get_public_repo_url

from .presenters.show import ShowPresenter

FORMATTERS: FormatterRegistry = {
    "text": SimpleSummaryConsoleFormatter,
    "json": JsonFormatter,
}


@command("show", help=__doc__)
@click.option(
    "--pull-request",
    is_flag=True,
    help="Show pull request submodules only",
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
def main(pull_request: bool, output_format: str, output_path: Path):

    repo, repo_path = require_repository()
    submodules = require_submodules(repo)

    metadata = get_metadata()

    formatter: OutputFormatter = FORMATTERS[output_format]()

    result: Result[list[SubmoduleInfo]] = Result()
    result.data = []

    with live_progress("Analysis..."):
        for sub in submodules:
            if pull_request and not is_pull_request(sub):
                continue

            log.info(f"{sub.name}")

            try:
                canonical_url = get_public_repo_url(sub.url)
            except (ValueError, AttributeError):
                canonical_url = sub.url or ""

            try:
                branch = sub.branch_name
            except Exception:
                branch = ""

            result.data.append(
                SubmoduleInfo(
                    name=sub.name,
                    url=canonical_url,
                    branch=branch,
                    pull_request=is_pull_request(sub),
                    last_commit=get_last_commit(str(repo_path / sub.path)),
                )
            )

        if not result.data:
            result.add_error("No matching submodules found.")
        else:
            result.data.sort(key=lambda x: x.name.lower())

    output = ShowPresenter().prepare(result, target=formatter.target, metadata=metadata)
    render_and_exit(result, formatter, output, output_format, output_path)
