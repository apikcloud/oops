# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: compare.py — oops/commands/addons/compare.py

"""
Compare a provided addon list against the local root addons.

Prints addons missing locally (prefixed with -) and extra local addons not in
the list (prefixed with +). With --delete, extra local symlinks are removed.
"""

import click
from git import Repo

from oops.core.messages import commit_messages
from oops.core.paths import WORKING_DIR
from oops.utils.helpers import str_to_list
from oops.utils.io import find_addons


@click.command("compare", help=__doc__)
@click.argument("addons_list")
@click.option(
    "--delete",
    is_flag=True,
    help="Remove extra local symlinks not in the provided list.",
)
@click.option(
    "--no-commit",
    is_flag=True,
    help="Do not commit changes",
)
def main(addons_list: str, delete: bool, no_commit: bool):

    repo = Repo()

    provided = set(str_to_list(addons_list))
    local = {a.technical_name for a in find_addons(WORKING_DIR, shallow=True)}

    missing = sorted(provided - local)  # in args, not local
    additionals = sorted(local - provided)  # local, not in args
    common = provided & local
    changes = []

    for name in missing:
        click.echo(click.style(f"- {name}", fg="red"))
    for name in additionals:
        click.echo(click.style(f"+ {name}", fg="green"))
        if delete:
            (WORKING_DIR / name).unlink()
            changes.append(name)

    click.echo(
        f"\n  {len(common)} matching, {len(missing)} missing locally, "
        f"{len(additionals)} extra locally"
    )

    if delete and changes and not no_commit:
        click.echo(f"{len(changes)} addon(s) removed, committing changes...")
        repo.index.remove(changes)
        repo.index.commit(commit_messages.addons_synchronize)
