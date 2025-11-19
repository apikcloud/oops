#!/usr/bin/env python3
import sys

import click

from oops.core.config import config
from oops.core.messages import commit_messages
from oops.git.gitutils import commit, git_add, git_top
from oops.utils.io import find_addons, write_text_file


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

    filepath = repo / config.pre_commit_exclude_file
    res = "|".join(sorted([f"{name}/" for name in names]))
    write_text_file(filepath, [res])

    git_add([str(filepath)])
    if not no_commit:
        commit(
            commit_messages.pre_commit_exclude,
            skip_hook=True,
        )
