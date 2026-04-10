# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: compare.py — oops/commands/addons/compare.py

"""
Compare a provided addon list against the local root addons.

Prints addons missing locally (prefixed with -) and extra local addons not in
the list (prefixed with +). With --delete, extra local symlinks are removed.
"""

import click

from oops.commands.base import command
from oops.io.file import find_addons
from oops.services.git import commit, get_local_repo
from oops.utils.helpers import str_to_list
from oops.utils.render import print_error, print_success


@command("compare", help=__doc__)
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

    repo, repo_path = get_local_repo()

    provided = set(str_to_list(addons_list))
    local = {a.technical_name for a in find_addons(repo_path, shallow=True)}

    missing = sorted(provided - local)  # in args, not local
    additionals = sorted(local - provided)  # local, not in args
    common = provided & local
    changes = []

    for name in missing:
        print_error(name, "-")
    for name in additionals:
        print_success(name, "+")
        if delete:
            (repo_path / name).unlink()
            changes.append(name)

    click.echo(
        f"\n  {len(common)} matching, {len(missing)} missing locally, "
        f"{len(additionals)} extra locally"
    )

    if delete and changes and not no_commit:
        click.echo(f"{len(changes)} addon(s) removed, committing changes...")
        commit(
            repo,
            repo_path,
            changes,
            "addons_synchronize",
            remove=True,
        )
