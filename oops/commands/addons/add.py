# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: add.py — oops/commands/addons/add.py

import logging
import os

import click

from git import Repo
from pathlib import Path

from oops.core.config import config
from oops.core.messages import commit_messages
from oops.git import list_available_addons
# from oops.git.core import GitRepository
from oops.utils.helpers import str_to_list
from oops.utils.io import desired_path,find_addons_extended, relpath


@click.command("add")
@click.argument("addons_list")
@click.option("--no-commit", is_flag=True)
def main(addons_list: str, no_commit: bool):
    """Create symlinks for listed addons from available ones in submodules."""

    repo = Repo()
    submodule_path = Path(repo.working_dir) / config.new_submodule_path
    addons_extended = find_addons_extended(Path(repo.working_dir))
    print("submodule_path",submodule_path)
    print([(name,path) for name, path, _ in addons_extended if submodule_path not in path.parents])
    existing_addons = [name for name, path, _ in addons_extended if submodule_path not in path.parents]
    print("="*120)
    print(existing_addons)
    print("="*120)
    addons = set(str_to_list(addons_list)) - set(existing_addons)

    addons_to_link = {}
    for name, path, _ in addons_extended:
        print(name,path)
        if name in addons:
            addons_to_link[name] = {"path": path, "version": None}

    if not addons_to_link:
        logging.warning("Not found...")
        return 0

    missing_addons = set(addons_to_link.keys()).difference(addons)

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
