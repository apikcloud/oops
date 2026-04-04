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

import os

import click

from oops.commands.base import command
from oops.core.config import config
from oops.io.file import find_modified_addons
from oops.services.git import get_local_repo, get_submodule_sha


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

    if tags and mode == "tag":
        base_ref = str(tags[-1])
        click.echo(f"Last tag found : {base_ref}")
    else:
        base_ref = f"HEAD~{number}"
        click.echo(f"Search in the last {number} commit(s)")

    # Newly added root-level entries (new symlinks or addon folders)
    added_files = repo.git.diff("--name-only", "--diff-filter=A", base_ref, "HEAD").splitlines()
    new_addons = set(find_modified_addons(added_files))

    # All changed files across the main repo and submodules
    diff_files = repo.git.diff("--name-only", base_ref, "HEAD").splitlines()
    for sm in repo.submodules:
        subrepo = sm.module()

        old_sha = get_submodule_sha(repo, base_ref, str(sm.path))
        new_sha = get_submodule_sha(repo, "HEAD", str(sm.path))

        # The submodule has not changed between base_ref and HEAD.
        if not old_sha or not new_sha or old_sha == new_sha:
            continue

        sub_diff = subrepo.git.diff("--name-only", old_sha, new_sha).splitlines()
        diff_files.extend(f"{sm.path}/{f}" for f in sub_diff)

    all_addons = set(find_modified_addons(diff_files))
    updated_addons = all_addons - new_addons

    if not all_addons:
        click.echo("No modified addon found.")
        raise click.exceptions.Exit(0)

    commands = []

    if new_addons:
        click.echo(f"{len(new_addons)} new addon(s):")
        click.echo("\n".join(sorted(new_addons)))
        commands.append(config.project.migrate_install_command.format(addons=",".join(sorted(new_addons))))

    if updated_addons:
        click.echo(f"{len(updated_addons)} updated addon(s):")
        click.echo("\n".join(sorted(updated_addons)))
        commands.append(config.project.migrate_command.format(addons=",".join(sorted(updated_addons))))

    click.echo()
    command = " && ".join(commands)
    click.echo(command)

    if save:
        with open(config.project.file_migrate, mode="w", encoding="UTF-8") as file:
            file.write(config.project.migrate_content.format(content=command))
        # Do a chmod +x
        st = os.stat(config.project.file_migrate)
        os.chmod(config.project.file_migrate, st.st_mode | 0o111)
