# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: diff.py — oops/commands/addons/diff.py

"""
Find modified Odoo addons and print the corresponding --update command.

Compares the current HEAD against either the last git tag or the last N commits,
including changes inside submodules. With --save, writes the command to a
migration script file.
"""

import os

import click

from oops.commands.base import command
from oops.core.config import config
from oops.io.file import find_modified_addons
from oops.services.git import get_local_repo, get_submodule_sha


@command(name="diff", help=__doc__)
@click.argument("mode", type=click.Choice(["tag", "commit"], case_sensitive=False))
@click.argument("number", required=False, default=1)
@click.option("-s", "--save", is_flag=True, help="Write the command in the migration file.")
def main(
    mode: str,
    number: int,
    save: bool,
):
    # TODO: distinguish between new modules and modified ones (install vs update)
    repo, _ = get_local_repo()
    tags = sorted(repo.tags, key=lambda t: t.commit.committed_datetime)

    if tags and mode == "tag":
        base_ref = str(tags[-1])
        click.echo(f"Last tag found : {base_ref}")
    else:
        base_ref = f"HEAD~{number}"
        click.echo(f"Search in the last {number} commit(s)")

    diff_files = repo.git.diff("--name-only", base_ref, "HEAD").splitlines()
    for sm in repo.submodules:
        subrepo = sm.module()

        old_sha = get_submodule_sha(repo, base_ref, sm.path)
        new_sha = get_submodule_sha(repo, "HEAD", sm.path)

        # The submodule has not changed between base_ref and HEAD.
        if not old_sha or not new_sha or old_sha == new_sha:
            continue

        sub_diff = subrepo.git.diff("--name-only", old_sha, new_sha).splitlines()

        diff_files.extend(f"{sm.path}/{f}" for f in sub_diff)
    addons = find_modified_addons(diff_files)

    if not addons:
        click.echo("No modified addon found.")
        raise click.exceptions.Exit(0)

    command = config.project.migrate_command.format(addons=",".join(addons))

    click.echo(f"{len(addons)} addon(s) found:")
    click.echo("\n".join(addons))

    click.echo()
    click.echo(command)

    if save:
        with open(config.project.file_migrate, mode="w", encoding="UTF-8") as file:
            file.write(config.project.migrate_content.format(content=command))
        # Do a chmod +x
        st = os.stat(config.project.file_migrate)
        os.chmod(config.project.file_migrate, st.st_mode | 0o111)
