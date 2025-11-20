# oops/commands/addons_materialize.py
from pathlib import Path

import click

from oops.core.messages import commit_messages
from oops.git.core import GitRepository
from oops.utils.helpers import str_to_list
from oops.utils.io import materialize_symlink
from oops.utils.render import human_readable


@click.command("materialize")
@click.argument("addons")
@click.option("--dry-run", is_flag=True, help="Show what would happen, do nothing.")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
def main(addons: str, dry_run: bool, no_commit: bool):
    """Replace an addon symlink by its real directory contents."""

    repo = GitRepository()

    addons_list = str_to_list(addons)

    changes = []
    for addon in addons_list:
        if not addon:
            continue
        addon_path = Path(repo.path) / addon
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
        click.echo("Committing changes...")

        repo.add([str(path) for path in changes])
        repo.commit(
            commit_messages.materialize_addons.format(
                names=human_readable([path.name for path in changes])
            ),
            skip_hook=True,
        )
