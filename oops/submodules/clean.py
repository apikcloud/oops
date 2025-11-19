#!/usr/bin/env python3

import logging
import shutil

import click

from oops.gitutils import git_reset_hard, git_top, parse_submodules, submodule_update
from oops.settings import NEW_SUBMODULES_PATH, OLD_SUBMODULES_PATH


@click.command(name="clean")
@click.option("--reset", is_flag=True, help="Do a hard reset before")
def main(reset: bool):
    """Clean old submodule paths and update submodules."""

    repo = git_top()
    gm = repo / ".gitmodules"
    if not gm.exists():
        click.echo("No .gitmodules found.")
        return 0

    if reset:
        git_reset_hard()

    subs = parse_submodules(gm)
    if not subs:
        click.echo("No submodules found.")
        return 0

    for path in [OLD_SUBMODULES_PATH, NEW_SUBMODULES_PATH]:
        old_base_path = repo / path

        if old_base_path.exists():
            click.echo(f"[prune] removing empty dir: {old_base_path}")
            try:
                shutil.rmtree(old_base_path)
            except OSError as error:
                logging.error(error)

    submodule_update()
