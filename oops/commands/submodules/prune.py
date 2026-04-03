# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: prune.py — oops/commands/submodules/prune.py

"""
Remove submodules that are not referenced by any symlink.

Iterates over all submodules, checks whether any symlink in the repository
points to the submodule path, and removes those that are unused. Specific
submodules can be targeted by passing their names as arguments.
"""

from pathlib import Path

import click

from oops.commands.base import command
from oops.core.messages import commit_messages
from oops.io.file import list_symlinks, relpath
from oops.services.git import get_local_repo
from oops.utils.compat import Optional
from oops.utils.render import print_success, print_warning


@command(name="prune", help=__doc__)
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
def main(no_commit: bool, dry_run: bool, names: "Optional[tuple[str]]" = None):  # noqa: C901, PLR0912

    repo, repo_path = get_local_repo()

    if not repo.submodules:
        click.echo("No .gitmodules found.")
        raise click.Abort()

    symlinks = list_symlinks(repo_path)
    unused = []

    # Check for unused submodules
    for submodule in repo.submodules:
        # TODO: filter by names if given
        if names and submodule.name not in names:
            continue

        path = repo_path / Path(submodule.path)
        rel = relpath(repo_path, path)
        if any(rel in t for t in symlinks):
            continue

        click.echo(f"[remove] {submodule.name}: {path}")
        submodule.remove(force=True, dry_run=dry_run)
        unused.append(submodule.name)

    if not unused:
        print_success("No unused submodules detected.")
        raise click.exceptions.Exit(0)

    if not no_commit:
        repo.index.commit(commit_messages.submodules_prune, skip_hooks=True)

    print_success(f"{len(unused)} submodule(s) removed: {', '.join(unused)}")

    if no_commit:
        print_warning("Don't forget to commit: git commit -m 'chore: remove unused submodules'")
