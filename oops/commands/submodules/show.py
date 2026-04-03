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

from oops.git import get_last_commit
from oops.git.core import GitRepository
from oops.utils.net import get_public_repo_url
from oops.utils.render import format_datetime, human_readable, render_boolean, render_table


@command("show", help=__doc__)
@click.option(
    "--pull-request",
    is_flag=True,
    help="Show pull request submodules only",
)
def main(pull_request: bool):

    # FIXME: use Repo from gitpython
    repo = GitRepository()

    if not repo.has_gitmodules:
        raise click.UsageError("No .gitmodules found.")

    rows = []
    for submodule in repo.parse_gitmodules():
        if pull_request is True and not submodule.pr:
            continue
        canonical_url = get_public_repo_url(submodule.url) if submodule.url else ""
        row = [
            human_readable(submodule.name, width=50),
            canonical_url,
            submodule.branch,
            render_boolean(submodule.pr) or "",
        ]
        last_commit = get_last_commit(submodule.path)
        if last_commit:
            row += [
                format_datetime(last_commit.date),
                last_commit.age,
                # last_commit.author,
                last_commit.sha,
            ]
        else:
            row += ["no commit found", "--", "--", "--"]
        rows.append(row)

    if not rows:
        raise click.UsageError("No submodules found.")

    rows = sorted(rows, key=lambda x: x[0].lower())

    click.echo(
        render_table(
            rows,
            headers=["Name", "Url", "Upstream", "PR", "Last Commit", "Age", "SHA"],
            index=False,
        )
    )
