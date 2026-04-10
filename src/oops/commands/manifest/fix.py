# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: fix.py — oops/commands/manifest/fix.py

"""
[EXPERIMENTAL] Apply autofixes to Odoo manifest files.

Scans the repository for __manifest__.py files and applies all autofixable
rules from oops.rules.manifest in place (author/maintainers, key order).
Reports how many files were modified.

Use oops-man-check to preview violations without modifying files.
"""

import click
from oops.commands.base import command
from oops.commands.manifest.common import collect_paths, run_fixit
from oops.io.file import get_filtered_addon_names
from oops.services.git import commit, get_local_repo
from oops.utils.helpers import str_to_list


@command(name="fix", help=__doc__)
@click.option("--names", default=None, help="Comma-separated list of addon names to fix.")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
def main(names: str, no_commit: bool) -> None:
    repo, repo_path = get_local_repo()

    name_filter = str_to_list(names) if names else get_filtered_addon_names(repo_path)
    paths = collect_paths(repo_path, name_filter)

    if not paths:
        click.echo("No manifest files found.")
        raise click.exceptions.Exit(0)

    fixed = run_fixit(paths, autofix=True, show_diff=True)

    if fixed:
        click.echo(f"{fixed} violation(s) fixed across {len(paths)} manifest(s).")

        # TODO: guess what files were actually modified and only commit those, instead of all paths
        if not no_commit:
            commit(
                repo,
                repo_path,
                paths,
                "manifest_update",
                skip_hooks=True,
            )

    else:
        click.echo(f"Nothing to fix in {len(paths)} manifest(s).")
