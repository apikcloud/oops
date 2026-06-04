# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: check.py — oops/commands/submodules/check.py

"""
Check all submodules for common issues.

Verifies path conventions, URL scheme, branch presence, deprecated repository
references, unused submodules (no symlink points to them), broken symlinks,
and pull-request submodules not under the configured PR directory.
Exits non-zero if any issue is found.
"""

from pathlib import Path

import click
from oops.commands.base import command, render_and_exit
from oops.core.checks import CheckOutcome
from oops.core.config import config
from oops.core.metadata import get_metadata
from oops.core.models import ResultCollection
from oops.io.file import list_symlinks
from oops.output.formatters import (
    FormatterRegistry,
    JsonFormatter,
    OutputFormatter,
    PreCommitFormatter,
    SimpleSummaryConsoleFormatter,
)
from oops.output.presenters import DefaultCheckPresenter
from oops.services.git import read_gitmodules, require_repository, require_submodules

from .common import CHECKS, SubmoduleCheckContext

FORMATTERS: FormatterRegistry = {
    "text": SimpleSummaryConsoleFormatter,
    "json": JsonFormatter,
}


@command(name="check", help=__doc__)
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
def main(hook: bool, output_format: str, output_path: Path):

    repo, repo_path = require_repository()
    submodules = require_submodules(repo)

    metadata = get_metadata()

    formatter: OutputFormatter = FORMATTERS[output_format]()
    if hook:
        formatter = PreCommitFormatter()

    ctx = SubmoduleCheckContext(
        repo=repo,
        repo_path=repo_path,
        submodules=submodules,
        symlinks=list_symlinks(repo_path),
        broken_symlinks=list_symlinks(repo_path, broken_only=True),
        gitmodules=read_gitmodules(repo),
        enabled=config.submodules.checks,
    )

    results: ResultCollection[CheckOutcome] = ResultCollection(title="Check submodules")
    for check_cls in CHECKS:
        results.add(check_cls(ctx).run())

    results.aggregate()

    output = DefaultCheckPresenter().prepare(results, target=formatter.target, metadata=metadata)
    render_and_exit(results, formatter, output, output_format, output_path)
