#!/usr/bin/env python3
import logging
import os

import click

from oops.core.messages import commit_messages
from oops.git.gitutils import commit, git_add, git_top, list_available_addons
from oops.utils.helpers import str_to_list
from oops.utils.io import find_addons_extended, relpath


@click.command("add")
@click.argument("addons_list")
@click.option("--no-commit", is_flag=True)
def main(addons_list: str, no_commit: bool):
    """Create symlinks for listed addons from available ones in submodules."""

    repo = git_top()
    os.chdir(repo)

    existing_addons = [name for name, _, _ in find_addons_extended(repo)]
    addons = set(str_to_list(addons_list)) - set(existing_addons)

    addons_to_link = {}
    for name, path, _ in list_available_addons(repo):
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
        link_path = repo / name
        # Determine relative target from repo root to the addon_dir
        target_rel = relpath(repo, vals["path"])
        if link_path.exists() or link_path.is_symlink():
            click.echo(f"  [skip] {name} already exists")
            continue
        os.symlink(target_rel, link_path)
        created_links.append(name)
        # Stage symlink
        git_add([name])

    if created_links and not no_commit:
        commit(commit_messages.new_addons, description="\n".join(created_links), skip_hook=True)
