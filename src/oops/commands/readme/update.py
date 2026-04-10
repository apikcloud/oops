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
"""

from __future__ import annotations

import click
from oops.core.config import config
from oops.io.file import file_updater, find_addons
from oops.services.git import commit, get_local_repo
from oops.services.github import get_github_user
from oops.utils.render import render_table


@click.command(name="update", help=__doc__)
@click.option("--dry-run", default=False, is_flag=True, help="Show what would happen, do nothing.")
@click.option("--no-commit", default=False, is_flag=True, help="Do not commit changes.")
def main(dry_run: bool = False, no_commit: bool = False):

    repo, repo_path = get_local_repo()
    readme_file = config.project.readme_file

    # Corresponding map for headers and manifest keys.
    headers = {
        "Addon": "technical_name",
        "Version": "version",
        "Maintainers": "maintainers",
        "Summary": "summary",
    }

    structure = []
    for addon in find_addons(repo_path, shallow=True):
        row = [f"[{addon.technical_name}](/{addon.technical_name})", addon.version]

        addon_maintainers = [get_github_user(user) for user in addon.maintainers]

        row.append(" ".join(addon_maintainers))
        row.append(" ".join(addon.summary.split()))
        structure.append(row)

    table = render_table(structure, list(headers.keys()), index=False)
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
        commit(repo, repo_path, [readme_file], "addons_update_table", skip_hooks=True)
