# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: add.py — oops/commands/addons/add.py
"""
Create root-level symlinks for specific addons found in any tracked submodule.

Searches all submodules for addons matching the provided names and creates
symlinks at the repository root. Skips addons that are already present.
"""

import os

import click
from oops.commands.base import command
from oops.io.file import relpath
from oops.io.manifest import find_addons_extended
from oops.services.git import commit, get_local_repo, list_available_addons
from oops.utils.helpers import str_to_list
from oops.utils.render import print_success, print_warning


@command("add", help=__doc__)
@click.argument("addons_list", type=str)
@click.option(
    "--no-commit",
    is_flag=True,
    help="If set, created symlinks will not be committed.",
)
def main(addons_list: str, no_commit: bool):

    repo, repo_path = get_local_repo()

    # Addons already linked at the repo root
    existing = {name for name, _, _ in find_addons_extended(repo_path)}
    requested = set(str_to_list(addons_list)) - existing

    if not requested:
        click.echo("All requested addons are already present.")
        raise click.exceptions.Exit(0)

    # Addons available in submodules, keyed by name
    available: dict = {
        name: path for name, path, _ in list_available_addons(repo, repo_path) if name in requested
    }

    missing = requested - available.keys()
    if missing:
        print_warning(f"Not found in any submodule ({len(missing)}): {', '.join(sorted(missing))}")

    if not available:
        raise click.ClickException("No matching addons found in any submodule.")

    created = []
    for name, addon_path in available.items():
        link = repo_path / name
        if link.exists() or link.is_symlink():
            click.echo(f"  [skip] {name} — already exists")
            continue
        os.symlink(relpath(repo_path, addon_path), link)
        created.append(name)
        click.echo(f"  [link] {name}")

    if not created:
        click.echo("Nothing to do.")
        return

    if not no_commit:
        commit(repo, repo_path, created, "addons_new", skip_hooks=True)
    else:
        print_success(f"{len(created)} symlink(s) created.")
