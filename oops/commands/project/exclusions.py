# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: exclusions.py — oops/commands/project/exclusions.py

"""
Add symlinked addons to the pre-commit exclusion file.

Writes the list of symlinked addon paths to the pre-commit exclusion file so
that pre-commit hooks skip third-party addons. The file is committed unless
--no-commit is passed.
"""

import click

from oops.commands.base import command
from oops.core.config import config
from oops.io.file import find_addons, write_text_file
from oops.services.git import commit, get_local_repo


@command(name="exclude", help=__doc__)
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
def main(no_commit: bool):
    repo, repo_path = get_local_repo()

    if not (repo_path / ".gitmodules").exists():
        raise click.ClickException("No .gitmodules found.")

    names = sorted(
        addon.technical_name
        for addon in find_addons(repo_path, shallow=True)
        if addon.symlink
    )

    if not names:
        click.echo("No symlinked addons found.")
        raise click.exceptions.Exit(0)

    click.echo(f"Found {len(names)} symlinked addon(s) to exclude from pre-commit")

    filepath = repo_path / config.project.pre_commit_exclude_file
    write_text_file(filepath, ["|".join(f"{name}/" for name in names)])

    if not no_commit:
        commit(repo, repo_path, [str(filepath)], "pre_commit_exclude", skip_hooks=True)
