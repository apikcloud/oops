#!/usr/bin/env python3

import logging
import shutil

import click

from oops.core.config import config
from oops.git.core import GitRepository
from oops.git.submodules import GitSubmodules


@click.command(name="clean")
@click.option("--reset", is_flag=True, help="Do a hard reset before")
def main(reset: bool):
    """Clean old submodule paths and update submodules."""

    repo = GitRepository()
    submodules = GitSubmodules()

    if not repo.has_gitmodules:
        click.echo("No .gitmodules found.")
        return 0

    if reset:
        repo.reset_hard()

    # FIXME: parse_gitmodules is a generator now
    # not subs anymore
    # subs = repo.parse_gitmodules()
    # if not subs:
    #     click.echo("No submodules found.")
    #     return 0

    for path in [config.old_submodule_path, config.new_submodule_path]:
        old_base_path = repo.path / path

        if old_base_path.exists():
            click.echo(f"[prune] removing empty dir: {old_base_path}")
            try:
                shutil.rmtree(old_base_path)
            except OSError as error:
                logging.error(error)

    submodules.update()
