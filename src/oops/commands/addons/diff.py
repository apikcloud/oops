# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: diff.py — oops/commands/addons/diff.py

"""
Show modified Odoo addons between a base ref and HEAD.

By default compares against the latest tag, or the penultimate tag when HEAD
is already at the latest tag. The base can be overridden with --tag, --ref,
or --commits. With --save, writes a migration script file.
"""

import click

from oops.commands.base import command
from oops.io.file import get_addons_diff, make_migration_command, write_migration_script
from oops.services.git import commit, get_local_repo
from oops.utils.render import print_error, print_success, print_warning


@command(name="diff", help=__doc__)
@click.option("--tag", default=None, help="Compare against this specific tag.")
@click.option("--ref", default=None, help="Compare against any ref or SHA.")
@click.option("--commits", default=None, type=int, help="Compare against HEAD~N.")
@click.option("-s", "--save", is_flag=True, help="Write the command in the migration file.")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
def main(  # noqa: C901, PLR0912
    tag: str,
    ref: str,
    commits: int,
    save: bool,
    no_commit: bool,
):
    repo, repo_path = get_local_repo()

    # Resolve base ref and optional release label
    release = None
    if ref:
        base_ref = ref
    elif tag:
        base_ref = tag
        release = tag
    elif commits:
        base_ref = f"HEAD~{commits}"
    else:
        # Auto-detect: latest tag, or penultimate if HEAD is already at the latest
        all_tags = sorted(repo.tags, key=lambda t: t.commit.committed_datetime)
        if not all_tags:
            raise click.ClickException("No tags found. Use --ref or --commits to specify a base.")
        latest = all_tags[-1]
        if repo.head.commit == latest.commit and len(all_tags) >= 2:
            chosen = all_tags[-2]
            click.echo(f"HEAD is at {latest} — using penultimate tag: {chosen}")
        else:
            chosen = latest
            click.echo(f"Using latest tag: {chosen}")
        base_ref = str(chosen)
        release = base_ref

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

    content = make_migration_command(
        new_addons,
        updated_addons,
        removed_addons,
        release=release,
    )
    click.echo(content)

    if save:
        migration_script = write_migration_script(content)

        if not no_commit:
            commit(repo, repo_path, [migration_script], "migration_script", skip_hooks=True)
