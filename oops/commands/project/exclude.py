# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: update.py — oops/commands/precommit/update.py

"""
Generate the exclusion list for pre-commit hooks in the .pre-commit-config.yaml file.
It checks all the addons in the root of the project and if the project is not owned by Apik, it excludes the addon.

The exclusion list uses a start and end tags to identify the section to update. The tags are the following:
- start: # oops:exclude:start
- end: # oops:exclude:end

If the tags are not found in the file, they are automatically added with the inner content at the head of the file.
"""

from __future__ import annotations

from pathlib import Path

import click
from git import Repo
from oops.core.config import config
from oops.core.messages import commit_messages
from oops.utils.io import file_updater, find_addons


@click.command("exclude", help=__doc__)
@click.option("--dry-run", is_flag=True, help="Show what would happen, do nothing.")
@click.option("--no-commit", is_flag=True, help="Do not commit changes.")
def main(dry_run: bool = False, no_commit: bool = False):
    default_exclusions = config.pre_commit_default_exclusions

    items = []

    precommit_file = config.pre_commit_file
    repo = Repo()
    repo_path = Path(repo.working_dir)

    for addon in find_addons(repo_path, shallow=True):
        if "apik" not in addon.author.lower():
            items.append(addon.technical_name)

    indented_items = [f"  {item}" for item in default_exclusions + items]

    to_exclude_str = "|\n".join(indented_items)
    to_exclude_str = f"exclude: |\n  (?x)\n{to_exclude_str}"

    has_update = False
    if not dry_run:
        click.echo(f"Updating {precommit_file}...")
        has_update = file_updater(
            filepath=".pre-commit-config.yaml",
            new_inner_content=to_exclude_str,
            start_tag="# oops:exclude:start",
            end_tag="# oops:exclude:end",
            padding="\n",
            append_position="top",
        )
    else:
        click.echo(f"It would update {precommit_file} with:\n{to_exclude_str}")

    if not no_commit and not dry_run and has_update:
        click.echo("Committing changes...")

        repo.index.add([precommit_file])
        repo.index.commit(commit_messages.pre_commit_exclude, skip_hooks=True)
