# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: show.py — oops/commands/submodules/show.py

"""
Display a table of all submodules with their details.

Shows name, URL, upstream branch, pull-request flag, last commit date,
commit age, and SHA for each submodule. Filter to PR-only submodules
with --pull-request.
"""

import click

from oops.commands.base import command
from oops.services.git import get_last_commit, get_local_repo, is_pull_request
from oops.utils.net import get_public_repo_url
from oops.utils.render import format_datetime, human_readable, render_boolean, render_table


@command("show", help=__doc__)
@click.option(
    "--pull-request",
    is_flag=True,
    help="Show pull request submodules only",
)
def main(pull_request: bool):

    repo, repo_path = get_local_repo()

    if not repo.submodules:
        raise click.UsageError("No submodules found.")

    rows = []
    for sub in repo.submodules:
        if pull_request and not is_pull_request(sub):
            continue

        try:
            canonical_url = get_public_repo_url(sub.url)
        except (ValueError, AttributeError):
            canonical_url = sub.url or ""

        try:
            branch = sub.branch_name
        except Exception:
            branch = ""

        row = [
            human_readable(sub.name, width=50),
            canonical_url,
            branch,
            render_boolean(is_pull_request(sub)),
        ]

        last_commit = get_last_commit(str(repo_path / sub.path))
        if last_commit:
            row += [format_datetime(last_commit.date), last_commit.age, last_commit.sha]
        else:
            row += ["no commit found", "--", "--"]

        rows.append(row)

    if not rows:
        raise click.UsageError("No matching submodules found.")

    rows.sort(key=lambda x: x[0].lower())

    click.echo(
        render_table(
            rows,
            headers=["Name", "Url", "Upstream", "PR", "Last Commit", "Age", "SHA"],
            index=False,
        )
    )
