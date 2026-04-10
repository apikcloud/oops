# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: show.py — oops/commands/release/show.py

"""
List all releases (semver tags) with their date and commit count.

Shows each vX.Y.Z tag sorted from newest to oldest, with the tag date,
author, and the number of commits between that release and the previous one.
"""

import click

from oops.commands.base import command
from oops.services.git import get_local_repo
from oops.utils.render import render_table
from oops.utils.versioning import SEMVER_PATTERN


@command(name="show", help=__doc__)
def main():
    repo, _ = get_local_repo()

    releases = sorted(
        [t for t in repo.tags if SEMVER_PATTERN.match(t.name)],
        key=lambda t: t.commit.committed_datetime,
    )

    if not releases:
        raise click.ClickException("No releases found.")

    rows = []
    for i, tag in enumerate(reversed(releases)):
        tag_date = tag.commit.committed_datetime.date().isoformat()

        if i < len(releases) - 1:
            prev = releases[-(i + 2)]
            commit_count = len(list(repo.iter_commits(f"{prev.name}..{tag.name}")))
        else:
            commit_count = len(list(repo.iter_commits(tag.name)))

        author = tag.tag.tagger.name if tag.tag else tag.commit.author.name
        rows.append([tag.name, tag_date, author, commit_count])

    click.echo(render_table(rows, headers=["Release", "Date", "Author", "Commits"], index=False))
