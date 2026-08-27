# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: check.py — src/oops/commands/pr/check.py

"""
Check the state of GitHub pull requests backing PR-convention submodules.

Raises an error if a resolved pull request is closed or merged. Skipped if
no pull request could be resolved for any PR-convention submodule.
"""

from pathlib import Path

import click
from oops.commands.base import command, render_and_exit
from oops.core.checks import CheckOutcome
from oops.core.logger import live_progress, log
from oops.core.metadata import get_metadata
from oops.core.models import ResultCollection
from oops.output.formatters import (
    FormatterRegistry,
    JsonFormatter,
    OutputFormatter,
    SimpleSummaryConsoleFormatter,
)
from oops.output.presenters import DefaultCheckPresenter
from oops.services.git import require_repository, require_submodules

from .common import CHECKS, PullRequestCheckContext

FORMATTERS: FormatterRegistry = {
    "text": SimpleSummaryConsoleFormatter,
    "json": JsonFormatter,
}


@command(name="check", help=__doc__)
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

    ctx = PullRequestCheckContext(
        repo=repo,
        repo_path=repo_path,
        submodules=submodules,
        token=token,
        enabled=[c.name for c in CHECKS],
    )

    results: ResultCollection[CheckOutcome] = ResultCollection(title="Check pull requests")

    with live_progress("Starting..."):
        for check_cls in CHECKS:
            log.info(f"Running `{check_cls.label}` check")
            results.add(check_cls(ctx).run())

    results.aggregate()

    output = DefaultCheckPresenter().prepare(results, target=formatter.target, metadata=metadata)
    render_and_exit(results, formatter, output, output_format, output_path)
