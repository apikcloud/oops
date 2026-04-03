# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: clean.py — oops/commands/submodules/clean.py

"""
Remove stale submodule base directories and re-initialise submodules.

Deletes the old and new submodule base directories (third-party and
.third-party) if they exist on disk, then runs git submodule update --init
to restore them from .gitmodules. Use --reset to hard-reset the repo first.
"""

import logging
import shutil

import click

from oops.commands.base import command
from oops.core.config import config
from oops.git.core import GitRepository
from oops.git.submodules import GitSubmodules


@command(name="clean", help=__doc__)
@click.option("--reset", is_flag=True, help="Do a hard reset before")
def main(reset: bool):

    # FIXME: use Repo from gitpython
    repo = GitRepository()
    submodules = GitSubmodules()

    if not repo.has_gitmodules:
        click.echo("No .gitmodules found.")
        raise click.Abort()

    if reset:
        repo.reset_hard()

    # FIXME: parse_gitmodules is a generator now
    # not subs anymore
    # subs = repo.parse_gitmodules()
    # if not subs:
    #     click.echo("No submodules found.")
    #     return 0

    for path in [config.submodules.old_paths[0], config.submodules.current_path]:
        old_base_path = repo.path / path

        if old_base_path.exists():
            click.echo(f"[prune] removing empty dir: {old_base_path}")
            try:
                shutil.rmtree(old_base_path)
            except OSError as error:
                logging.error(error)

    submodules.update()
