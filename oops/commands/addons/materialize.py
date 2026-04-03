# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: materialize.py — oops/commands/addons/materialize.py

"""
Replace addon symlinks with a real copy of the addon directory.

Useful when you need to modify a third-party addon locally. The symlink is
removed and its target directory is copied in place. Only symlinks are
processed; real directories are skipped.
"""

import click

from oops.commands.base import command
from oops.io.file import materialize_symlink
from oops.services.git import commit, get_local_repo
from oops.utils.helpers import str_to_list
from oops.utils.render import human_readable


@command("materialize", help=__doc__)
@click.argument("addons")
@click.option("--dry-run", is_flag=True, help="Show what would happen, do nothing.")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
def main(addons: str, dry_run: bool, no_commit: bool):

    # TODO: add option to materialize all symlinks under the addons directory

    repo, repo_path = get_local_repo()

    addons_list = str_to_list(addons)

    changes = []
    for addon in addons_list:
        if not addon:
            continue
        addon_path = repo_path / addon
        if not addon_path.exists():
            click.echo(f"[oops] skip: {addon_path} does not exist.")
            continue
        if not addon_path.is_symlink():
            click.echo(f"[oops] skip: {addon_path} is not a symlink.")
            continue

        try:
            materialize_symlink(addon_path, dry_run=dry_run)
        except Exception as error:
            click.echo(error)
            continue
        if not dry_run:
            click.echo(f"[oops] done: {addon_path} is now a real directory.")

        changes.append(addon_path)

    if not no_commit and changes and not dry_run:
        commit(
            repo,
            repo_path,
            [str(path) for path in changes],
            "materialize_addons",
            names=human_readable([path.name for path in changes]),
        )
