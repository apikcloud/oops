# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: add.py — oops/commands/addons/add.py
"""
Create root-level symlinks for specific addons found in any tracked submodule.

Searches all submodules for addons matching the provided names and creates
symlinks at the repository root. Skips addons that are already present.
"""

import os

import click

from oops.core.messages import commit_messages
from oops.git import list_available_addons
from oops.git.core import GitRepository
from oops.utils.helpers import str_to_list
from oops.utils.io import find_addons_extended, relpath


@click.command("add")
@click.argument("addons_list", type=str)
@click.option(
    "--no-commit",
    is_flag=True,
    help="If set, created symlinks will not be committed.",
)
def main(addons_list: str, no_commit: bool):

    repo = GitRepository()

    existing_addons = [name for name, _, _ in find_addons_extended(repo.path)]
    addons = set(str_to_list(addons_list)) - set(existing_addons)

    addons_to_link = {}
    for name, path, _ in list_available_addons(repo.path):
        if name in addons:
            addons_to_link[name] = {"path": path, "version": None}

    if not addons_to_link:
        click.echo("No addons found...")
        raise click.Abort()

    missing_addons = addons.difference(set(addons_to_link.keys()))

    if missing_addons:
        click.echo(f"Missing addons ({len(missing_addons)}): {', '.join(missing_addons)}")

    created_links = []
    for name, vals in addons_to_link.items():
        link_path = repo.path / name
        # Determine relative target from repo root to the addon_dir
        target_rel = relpath(repo.path, vals["path"])
        if link_path.exists() or link_path.is_symlink():
            click.echo(f"  [skip] {name} already exists")
            continue
        os.symlink(target_rel, link_path)
        created_links.append(name)
        # Stage symlink
        repo.add([name])

    if created_links and not no_commit:
        repo.commit(
            commit_messages.new_addons, description="\n".join(created_links), skip_hook=True
        )

    return 0
