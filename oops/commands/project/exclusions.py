#!/usr/bin/env python3
import sys

import click

from oops.core.config import config
from oops.core.messages import commit_messages
from oops.git.core import GitRepository
from oops.utils.io import find_addons, write_text_file


@click.command(name="exclude")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
def main(no_commit: bool):  # noqa: C901, PLR0912
    repo = GitRepository()

    if not repo.has_gitmodules:
        click.echo("No .gitmodules found.", file=sys.stderr)
        return 1

    names = []
    for addon in find_addons(repo.path, shallow=True):
        if addon.symlink:
            names.append(f"{addon.technical_name}/")

    if not names:
        click.echo("No symlinked addons found.")
        return 0

    click.echo(f"Found {len(names)} symlinked addon(s) to exclude from pre-commit")

    filepath = repo.path / config.pre_commit_exclude_file
    res = "|".join(sorted([f"{name}/" for name in names]))
    write_text_file(filepath, [res])

    repo.add([str(filepath)])
    if not no_commit:
        repo.commit(
            commit_messages.pre_commit_exclude,
            skip_hook=True,
        )
