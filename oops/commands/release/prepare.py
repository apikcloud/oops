# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: prepare.py — oops/commands/release/prepare.py

"""
Prepare a release by detecting modified Odoo addons and building the upgrade command.

Compares the current HEAD against either the last git tag or the last N commits,
including changes inside submodules. With --save, writes the command to a
migration script file.
"""

import click

from oops.commands.base import command
from oops.io.file import get_addons_diff, make_migration_command, write_migration_script
from oops.services.git import get_local_repo
from oops.utils.render import print_error, print_success, print_warning


@command(name="prepare", help=__doc__)
@click.argument("mode", type=click.Choice(["tag", "commit"], case_sensitive=False))
@click.argument("number", required=False, default=1)
@click.option("-s", "--save", is_flag=True, help="Write the command in the migration file.")
def main(
    mode: str,
    number: int,
    save: bool,
):
    repo, _ = get_local_repo()
    tags = sorted(repo.tags, key=lambda t: t.commit.committed_datetime)

    release = None
    if tags and mode == "tag":
        base_ref = str(tags[-1])
        release = base_ref
        click.echo(f"Last tag found : {base_ref}")
    else:
        base_ref = f"HEAD~{number}"
        click.echo(f"Search in the last {number} commit(s)")

    new_addons, updated_addons, removed_addons = get_addons_diff(repo, base_ref)

    if not any([new_addons, updated_addons, removed_addons]):
        click.echo("No modified addon found.")
        raise click.exceptions.Exit(0)

    if removed_addons:
        for addon in removed_addons:
            print_error(addon, "-")

    if new_addons:
        for addon in new_addons:
            print_success(addon, "+")

    if updated_addons:
        for addon in updated_addons:
            print_warning(addon, "w")

    if save:
        content = make_migration_command(
            new_addons,
            updated_addons,
            removed_addons,
            release=release,
        )
        click.echo(content)
        write_migration_script(content)
