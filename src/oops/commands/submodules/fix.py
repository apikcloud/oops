# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: fix.py — oops/commands/submodules/fix.py

"""
Fix common submodule issues detected by oops-sub-check.

Normalises submodule URLs to the configured scheme (e.g. SSH).
Deprecated repository replacements are reported but not applied
automatically — use ``oops-sub-replace`` for those.
"""

import click

from oops.commands.base import command
from oops.core.config import config
from oops.services.git import commit, get_local_repo
from oops.utils.net import _parse_url, encode_url
from oops.utils.render import print_success, print_warning


@command(name="fix", help=__doc__)
@click.option("--dry-run", is_flag=True, help="Show planned changes only.")
@click.option("--no-commit", is_flag=True, help="Do not commit automatically at the end.")
def main(dry_run: bool, no_commit: bool) -> None:

    repo, repo_path = get_local_repo()

    if not repo.submodules:
        raise click.UsageError("No .gitmodules found.")

    new_urls = []
    deprecated = []

    for submodule in repo.submodules:
        scheme, _, owner, repository = _parse_url(submodule.url)
        repository_name = f"{owner}/{repository}"

        if config.submodules.force_scheme and config.submodules.force_scheme != scheme:
            new_urls.append(
                (submodule, encode_url(submodule.url, config.submodules.force_scheme))
            )

        if repository_name in config.submodules.deprecated_repositories:
            deprecated.append(
                (submodule.name, config.submodules.deprecated_repositories[repository_name])
            )

    # Report deprecated repos — replacement requires oops-sub-replace
    if deprecated:
        print_warning("Deprecated repositories found (use oops-sub-replace to migrate):")
        for name, replacement in deprecated:
            click.echo(f"  {name} → {replacement}")

    # Fix submodule URLs
    if new_urls:
        click.echo("Submodule URLs to update:")
        for submodule, new_url in new_urls:
            click.echo(f"  {submodule.name}: {submodule.url} → {new_url}")

        if not dry_run:
            for submodule, new_url in new_urls:
                repo.git.submodule("set-url", submodule.path, new_url)

            if not no_commit:
                commit(
                    repo,
                    repo_path,
                    [".gitmodules"],
                    "submodules_fix_urls",
                    description="\n".join(
                        f"- {sub.name}: {url}" for sub, url in new_urls
                    ),
                )
    elif not deprecated:
        print_success("No issues found.")
        return

    if not dry_run and new_urls:
        print_success(f"Fixed {len(new_urls)} submodule URL(s).")
    elif dry_run:
        click.echo("Dry run — no changes applied.")
