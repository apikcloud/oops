# osh/commands/addons_materialize.py
import os
from pathlib import Path

import click

from osh.gitutils import commit, git_add, git_top
from osh.messages import GIT_MATERIALIZE_ADDONS
from osh.render import human_readable
from osh.utils import materialize_symlink, str_to_list


@click.command("materialize")
@click.argument("addons")
@click.option("--dry-run", is_flag=True, help="Show what would happen, do nothing.")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
def main(addons: str, dry_run: bool, no_commit: bool):
    """Replace an addon symlink by its real directory contents."""

    repo = git_top()
    os.chdir(repo)

    addons_list = str_to_list(addons)

    changes = []
    for addon in addons_list:
        if not addon:
            continue
        addon_path = Path(repo) / addon
        if not addon_path.exists():
            click.echo(f"[osh] skip: {addon_path} does not exist.")
            continue
        if not addon_path.is_symlink():
            click.echo(f"[osh] skip: {addon_path} is not a symlink.")
            continue

        try:
            materialize_symlink(addon_path, dry_run=dry_run)
        except Exception as error:
            click.echo(error)
            continue
        if not dry_run:
            click.echo(f"[osh] done: {addon_path} is now a real directory.")

        changes.append(addon_path)

    if not no_commit and changes and not dry_run:
        click.echo("Committing changes...")

        git_add([str(path) for path in changes])
        commit(
            GIT_MATERIALIZE_ADDONS.format(names=human_readable([path.name for path in changes])),
            skip_hook=True,
        )
