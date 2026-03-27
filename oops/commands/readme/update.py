# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: update.py — oops/commands/readme/update.py

"""
Generate the addons table in the README.md of the project.

The exclusion list uses a start and end tags to identify the section to update. The tags are the following:
- start: # [//]: # (addons)
- end: # [//]: # (end addons)

If the tags are not found in the file, they are automatically added at the end of the file with its content.

This command can be used with two options:
- --dry-run: Show what would happen, do nothing.
- --no-commit: Do not commit changes.

"""

from __future__ import annotations

from pathlib import Path

import click
from git import Repo
from tabulate import tabulate

from oops.core.config import config
from oops.core.messages import commit_messages
from oops.utils.io import file_updater, find_addons


@click.option("--dry-run", default=False, is_flag=True, help="Show what would happen, do nothing.")
@click.option("--no-commit", default=True, is_flag=True, help="Do not commit changes.")
def main(dry_run: bool = False, no_commit: bool = True):
    def _get_github_user(_user):
        """Structure the maintainer's GitHub user as a link and display their avatar."""
        return (
            f"<a href='https://github.com/{_user}'>"
            f"<img src='https://github.com/{_user}.png' width='32' height='32' alt='{_user}'/></a>"
        )

    # Corresponding map for headers and manifest keys.
    headers = {
        "Addon": "technical_name",
        "Version": "version",
        "Maintainers": "maintainers",
        "Summary": "summary",
    }

    readme_file = config.project_file_readme

    repo = Repo()
    repo_path = Path(repo.working_dir)

    structure = []
    for addon in find_addons(repo_path, shallow=True):
        row = [f"[{addon.technical_name}](/{addon.technical_name})", addon.version]

        addon_maintainers = [_get_github_user(user) for user in addon.maintainers]
        row.append(" ".join(addon_maintainers))

        row.append(" ".join(addon.summary.split()))

        structure.append(row)

    table = tabulate(structure, headers=headers.keys(), tablefmt="github")

    new_content = f"Available addons\n----------------\n\n{table}\n"

    has_update = False
    if not dry_run:
        click.echo(f"Updating {readme_file}...")
        # We keep using OCA tags, in case we want to use their tools again.
        # Start tag: # [//]: # (addons)
        # End tag: # [//]: # (end addons)
        has_update = file_updater(
            filepath=readme_file,
            new_inner_content=new_content,
            start_tag="[//]: # (addons)",
            end_tag="[//]: # (end addons)",
            padding="\n\n",
        )
    else:
        click.echo(f"It would update {readme_file} with:\n{new_content}")

    if not no_commit and not dry_run and has_update:
        click.echo("Committing changes...")

        repo.index.add([readme_file])
        repo.index.commit(commit_messages.update_addons_table, skip_hooks=True)
