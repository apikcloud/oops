# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: clean.py — oops/commands/submodules/clean.py

"""
Remove stale submodule base directories and re-initialise submodules.

Deletes the old and new submodule base directories (third-party and
.third-party) if they exist on disk, then runs git submodule update --init
to restore them from .gitmodules. Use --reset to hard-reset the repo first.
"""

import shutil

import click
from oops.commands.base import command
from oops.core.config import config
from oops.services.git import get_local_repo
from oops.utils.render import print_error


@command(name="clean", help=__doc__)
@click.option("--reset", is_flag=True, help="Do a hard reset before")
def main(reset: bool):

    repo, repo_path = get_local_repo()

    if not (repo_path / ".gitmodules").exists():
        click.echo("No .gitmodules found.")
        raise click.Abort()

    if reset:
        repo.head.reset(index=True, working_tree=True)

    for path in [config.submodules.old_paths[0], config.submodules.current_path]:
        base_path = repo_path / path

        if base_path.exists():
            click.echo(f"[prune] removing directory: {base_path}")
            try:
                shutil.rmtree(base_path)
            except OSError as e:
                print_error(str(e))

    repo.git.submodule("update", "--init", "--recursive")
