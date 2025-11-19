#!/usr/bin/env python3
import sys

import click

from oops.gitutils import commit, git_add, git_top
from oops.io import find_addons, write_text_file
from oops.messages import GIT_UPDATE_PRE_COMMIT_EXCLUDE
from oops.settings import PRE_COMMIT_EXCLUDE_FILE


@click.command(name="exclude")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
def main(no_commit: bool):  # noqa: C901, PLR0912
    repo = git_top()
    gm = repo / ".gitmodules"
    if not gm.exists():
        click.echo("No .gitmodules found.", file=sys.stderr)
        return 1

    names = []
    for addon in find_addons(repo, shallow=True):
        if addon.symlink:
            names.append(f"{addon.technical_name}/")

    if not names:
        click.echo("No symlinked addons found.")
        return 0

    click.echo(f"Found {len(names)} symlinked addon(s) to exclude from pre-commit")

    filepath = repo / PRE_COMMIT_EXCLUDE_FILE
    res = "|".join(sorted([f"{name}/" for name in names]))
    write_text_file(filepath, [res])

    git_add([str(filepath)])
    if not no_commit:
        commit(
            GIT_UPDATE_PRE_COMMIT_EXCLUDE,
            skip_hook=True,
        )
