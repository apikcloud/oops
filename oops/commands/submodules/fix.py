# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: fix.py — oops/commands/submodules/fix.py

"""
Fix common submodule issues detected by oops-sub-check.

Normalises submodule URLs to the configured scheme (e.g. SSH) and replaces
deprecated repository paths as defined in the project config.
"""

import click

from oops.commands.base import command
from oops.core.config import config
from oops.utils.git import commit, get_local_repo
from oops.utils.net import encode_url, parse_repository_url


@command(name="fix", help=__doc__)
@click.option(
    "--no-commit",
    is_flag=True,
    help="Do not commit automatically at the end",
)
def main(no_commit: bool):  # noqa: C901, PLR0912

    # 1. Prune unused submodules
    # 2. Rename submodules
    # 3. Rewrite submodules

    repo, repo_path = get_local_repo()

    if not repo.submodules:
        click.echo("No submodules found.")
        raise click.Abort()

    new_urls = []
    # deprecated_repos = []

    repo_to_remove = []
    repo_to_add = []
    # symlinks_to_update = []

    for submodule in repo.submodules:
        scheme, owner, repository = parse_repository_url(submodule.url)
        repository_name = f"{owner}/{repository}"

        # Check URL scheme
        if config.submodules.force_scheme and config.submodules.force_scheme != scheme:
            new_urls.append(
                (submodule.name, encode_url(submodule.url, config.submodules.force_scheme))
            )

        # Check deprecated repositories
        if repository_name in config.submodules.deprecated_repositories:
            repo_to_remove.append(submodule.name)
            repo_to_add.append(
                (config.submodules.deprecated_repositories[repository_name], submodule.branch)
            )

    # Fix submodule URLs
    if new_urls:
        click.echo("The following submodule URLs will be updated:")
        for name, new_url in new_urls:
            click.echo(f"  {name}: {new_url}")
            submodule = repo.submodules[name]
            repo.git.submodule("set-url", submodule.path, new_url)

        if not no_commit:
            click.echo("Committing submodule URL changes...")
            commit(
                repo,
                repo_path,
                [".gitmodules"],
                "submodules_fix_urls",
                description="\n".join(f"- {name}: {url}" for name, url in new_urls),
            )
