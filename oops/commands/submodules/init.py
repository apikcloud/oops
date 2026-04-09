# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: init.py — oops/commands/submodules/init.py

"""
Initialize and update all submodules recursively.

Runs ``git submodule update --init --recursive --jobs=N``, initializing
any unregistered submodules and checking out the recorded commits in
parallel across N worker jobs.
"""

import click

from oops.commands.base import command
from oops.services.git import get_local_repo
from oops.utils.render import print_success


@command(name="init", help=__doc__)
@click.option(
    "--jobs",
    "-j",
    default=4,
    show_default=True,
    type=click.IntRange(min=1),
    help="Number of parallel jobs.",
)
def main(jobs: int) -> None:
    repo, _ = get_local_repo()

    click.echo(f"Updating submodules ({jobs} parallel job(s))...")
    repo.git.submodule("update", "--init", "--recursive", f"--jobs={jobs}")
    print_success("Submodule update complete.")
