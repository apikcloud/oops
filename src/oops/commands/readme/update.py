# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
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
from oops.commands.base import command, render_and_exit
from oops.core.config import config
from oops.core.logger import live_progress, log
from oops.core.models import Result
from oops.io.file import file_updater, find_addons
from oops.output.formatters import OutputFormatter, PreCommitFormatter, SimpleSummaryConsoleFormatter
from oops.services.git import commit_v2, require_repository
from oops.services.github import get_github_user
from oops.utils.render import render_table

from .presenters.update import UpdatePresenter


@command(name="update", help=__doc__)
@click.option("--dry-run", default=False, is_flag=True, help="Show what would happen, do nothing.")
@click.option("--no-commit", default=False, is_flag=True, help="Do not commit changes.")
@click.option(
    "--hook",
    is_flag=True,
    help="Minimal output for pre-commit hooks.",
)
def main(dry_run: bool = False, no_commit: bool = False, hook: bool = False):

    formatter: OutputFormatter = PreCommitFormatter() if hook else SimpleSummaryConsoleFormatter()

    repo, repo_path = require_repository()

    result: Result[dict] = Result({"cmd": "Update README", "rows": [], "dry_run": dry_run})

    assert result.data is not None

    readme_file = config.project.readme_file

    headers = {
        "Addon": "technical_name",
        "Version": "version",
        "Maintainers": "maintainers",
        "Summary": "summary",
    }

    structure = []

    with live_progress("Updating README…", enabled=not hook):
        # Addons section
        for addon in find_addons(repo_path, shallow=True):
            log.info(f"Reading {addon.technical_name}…")
            addon_maintainers = [get_github_user(user) for user in addon.maintainers]
            maintainers_str = " ".join(addon_maintainers)

            structure.append(
                [
                    f"[{addon.technical_name}](/{addon.technical_name})",
                    addon.version,
                    maintainers_str,
                    " ".join(addon.summary.split()),
                ]
            )

        structure.sort()
        table = render_table(structure, list(headers.keys()), index=False)
        new_content = f"Available addons\n----------------\n\n{table}\n"

        try:
            has_update = file_updater(
                filepath=readme_file,
                new_inner_content=new_content,
                start_tag="[//]: # (addons)",
                end_tag="[//]: # (end addons)",
                padding="\n\n",
                dry_run=dry_run,
            )
            status = "updated" if has_update else "no change"
        except Exception as error:
            has_update = False
            result.add_error(str(error))
            status = "failed"

        result.data["rows"].append(["addons", status])

    if not no_commit and not dry_run and has_update:
        commit_result: Result = commit_v2(repo, repo_path, [readme_file], "addons_update_table", skip_hooks=True)
        result.merge(commit_result)

    output = UpdatePresenter().prepare(result, formatter.target)
    render_and_exit(result, formatter, output, "text")
