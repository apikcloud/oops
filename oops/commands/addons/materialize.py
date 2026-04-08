# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: materialize.py — oops/commands/addons/materialize.py

"""
Replace addon symlinks with a real copy of the addon directory.

Useful when you need to modify a third-party addon locally. The symlink is
removed and its target directory is copied in place. Only symlinks are
processed; real directories are skipped.

By default all symlinks found at the repository root are processed.
Use --include to restrict to a subset, or --exclude to skip specific addons.
"""

import click

from oops.commands.base import command
from oops.io.file import materialize_symlink
from oops.services.git import commit, get_local_repo
from oops.utils.compat import Optional
from oops.utils.helpers import str_to_list
from oops.utils.render import human_readable, print_error, print_success


@command("materialize", help=__doc__)
@click.option(
    "--include",
    default=None,
    metavar="ADDONS",
    help="Comma-separated list of addon names to materialize (default: all symlinks).",
)
@click.option(
    "--exclude",
    default=None,
    metavar="ADDONS",
    help="Comma-separated list of addon names to skip.",
)
@click.option("--dry-run", is_flag=True, help="Show what would happen, do nothing.")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
def main(include: Optional[str], exclude: Optional[str], dry_run: bool, no_commit: bool):

    if include and exclude:
        raise click.UsageError("--include and --exclude are mutually exclusive.")

    repo, repo_path = get_local_repo()

    candidates = sorted(p for p in repo_path.iterdir() if p.is_symlink())

    if include:
        include_set = set(str_to_list(include))
        candidates = [p for p in candidates if p.name in include_set]
    elif exclude:
        exclude_set = set(str_to_list(exclude))
        candidates = [p for p in candidates if p.name not in exclude_set]

    changes = []
    for addon_path in candidates:
        try:
            materialize_symlink(addon_path, dry_run=dry_run)
        except Exception as error:
            print_error(f"Failed to materialize {addon_path.name}")
            click.echo(str(error))
            continue

        print_success(f"{addon_path.name} is now a real directory")
        changes.append(addon_path)

    if not no_commit and changes and not dry_run:
        commit(
            repo,
            repo_path,
            [str(path) for path in changes],
            "addons_materialize",
            names=human_readable([str(path.name) for path in changes], sep="\n"),
            remove_and_add=True,
        )
