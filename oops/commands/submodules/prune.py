#!/usr/bin/env python3


from pathlib import Path

import click
from git import Repo

from oops.core.messages import commit_messages
from oops.utils.io import list_symlinks, relpath


@click.command(name="prune")
@click.option(
    "--no-commit",
    is_flag=True,
    help="Do not commit automatically at the end",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show planned changes only",
)
@click.argument("names", nargs=-1, required=False)
def main(no_commit: bool, dry_run: bool, names: tuple[str] = None):  # noqa: C901, PLR0912
    """Remove unused submodules (not referenced by any symlink) and clean old paths."""

    repo = Repo()

    if not repo.submodules:
        click.echo("No .gitmodules found.")
        return 0

    symlinks = list_symlinks(repo.working_dir)
    unused = []

    # Check for unused submodules
    for submodule in repo.submodules:
        # TODO: filter by names if given
        if names and submodule.name not in names:
            continue

        path = Path(repo.working_dir) / Path(submodule.path)
        rel = relpath(repo.working_dir, path)
        if any(rel in t for t in symlinks):
            continue

        click.echo(f"[remove] {submodule.name}: {path}")
        submodule.remove(force=True, dry_run=dry_run)
        unused.append(submodule.name)

    if not unused:
        click.echo("✅ No unused submodules detected.")
        return 0

    if not no_commit:
        repo.index.commit(commit_messages.submodules_prune, skip_hooks=True)

    click.echo("\n✅ Unused submodules removed.")

    if no_commit:
        click.echo("Don't forget to commit: git commit -m 'chore: remove unused submodules'")

    return 0
