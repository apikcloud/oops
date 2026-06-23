# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""List pull requests from a GitHub repository."""

from __future__ import annotations

import click
from oops.commands.base import command, render_and_exit
from oops.core.compat import List, Optional
from oops.core.config import config
from oops.core.exceptions import OopsError
from oops.core.logger import live_progress
from oops.core.metadata import get_metadata
from oops.core.models import PullRequest, Result
from oops.output.formatters import (
    FormatterRegistry,
    JsonFormatter,
    OutputFormatter,
    SimpleSummaryConsoleFormatter,
)
from oops.services.github import list_pull_requests
from oops.utils.net import parse_repository_url, resolve_repository_url

from .presenters.explore import ExplorePresenter

FORMATTERS: FormatterRegistry = {
    "text": SimpleSummaryConsoleFormatter,
    "json": JsonFormatter,
}


def _default_filter() -> "Optional[str]":
    """Return `[<major>][MIG]` from project version, or None on any failure."""
    try:
        from oops.io.file import parse_odoo_version
        from oops.services.git import require_repository

        _, repo_path = require_repository()
        version = parse_odoo_version(repo_path).major_version
        return f"[{version}][MIG]"
    except Exception:  # noqa: BLE001
        return None


@command("explore", help=__doc__)
@click.argument("repo")
@click.option(
    "--filter",
    "title_filter",
    default=None,
    metavar="TEXT",
    help=(
        "Filter PRs by case-insensitive title substring. "
        "Defaults to [<odoo major version>][MIG] inside a project. Pass '' to disable."
    ),
)
@click.option(
    "--version",
    "odoo_version",
    default=None,
    metavar="VERSION",
    help="Odoo major version (e.g. 17.0). Sets the filter to [VERSION][MIG]. "
    "Overridden by --filter.",
)
@click.option(
    "--state",
    type=click.Choice(["open", "closed", "all"]),
    default="open",
    show_default=True,
    help="PR state to list.",
)
@click.option(
    "--token",
    envvar=["GH_TOKEN", "GITHUB_TOKEN"],
    default=None,
    help="GitHub token (or envvar GH_TOKEN / GITHUB_TOKEN). Optional for public repos.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format.",
)
def main(
    repo: str,
    title_filter: "Optional[str]",
    odoo_version: "Optional[str]",
    state: str,
    token: "Optional[str]",
    output_format: str,
):
    try:
        full_url = resolve_repository_url(repo, default_owner=config.github.owner)
        _, owner, repo_name = parse_repository_url(full_url)
    except ValueError as exc:
        raise OopsError(str(exc)) from exc

    if title_filter is not None:
        effective_filter = title_filter
    elif odoo_version is not None:
        effective_filter = f"[{odoo_version}][MIG]"
    else:
        effective_filter = _default_filter()

    formatter: OutputFormatter = FORMATTERS[output_format]()
    result: Result[List[PullRequest]] = Result()

    with live_progress("Fetching pull requests..."):
        prs = list_pull_requests(owner, repo_name, token=token, state=state)

        if effective_filter is not None:
            prs = [pr for pr in prs if effective_filter.lower() in pr.title.lower()]

        prs.sort(key=lambda pr: pr.number, reverse=True)
        result.data = prs

        if not prs:
            msg = f"No pull requests found in {owner}/{repo_name}"
            if effective_filter is not None:
                msg += f" matching {effective_filter!r}"
            result.add_warning(msg + ".")

    output = ExplorePresenter().prepare(result, target=formatter.target, metadata=get_metadata())
    render_and_exit(result, formatter, output, output_format)
