# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: show.py — src/oops/commands/pr/show.py


"""
Display a table of all pull requests with their details.
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
from oops.services.github import find_pull_requests
from oops.utils.net import get_public_repo_url, parse_repository_url

from .presenters.show import ShowPresenter

FORMATTERS: FormatterRegistry = {
    "text": SimpleSummaryConsoleFormatter,
    "json": JsonFormatter,
}


@command("show", help=__doc__)
@click.option(
    "--token",
    envvar=["GH_TOKEN", "GITHUB_TOKEN"],
    required=True,
    help="Personal Access Token GitHub (or envvar GITHUB_TOKEN).",
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
def main(token: str, output_format: str, output_path: Path):

    repo, repo_path = require_repository()
    submodules = require_submodules(repo)

    metadata = get_metadata()

    formatter: OutputFormatter = FORMATTERS[output_format]()

    result: Result[list[SubmoduleInfo]] = Result()
    result.data = []

    with live_progress("Analysis..."):
        for sub in submodules:
            if not is_pull_request(sub):
                continue

            log.info(sub.name)

            try:
                canonical_url = get_public_repo_url(sub.url)
            except (ValueError, AttributeError):
                canonical_url = sub.url or ""

            try:
                branch = sub.branch_name
            except Exception:
                branch = ""

            _, fork_owner, fork_repo = parse_repository_url(canonical_url)

            sub_info = SubmoduleInfo(
                name=sub.name,
                url=canonical_url,
                branch=branch,
                pull_request=is_pull_request(sub),
                last_commit=get_last_commit(str(repo_path / sub.path)),
            )

            if branch:
                sub_info.pull_requests = find_pull_requests(fork_owner, fork_repo, branch, token=token)

            result.data.append(sub_info)

        if not result.data:
            result.add_warning("No pull requests found.")
        else:
            result.data.sort(key=lambda x: x.name.lower())

    output = ShowPresenter().prepare(result, target=formatter.target, metadata=metadata)
    render_and_exit(result, formatter, output, output_format, output_path)
