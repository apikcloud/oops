#!/usr/bin/env python3


from pathlib import Path

import click
from git import Repo

from oops.core.config import config
from oops.core.messages import commit_messages
from oops.utils.io import list_symlinks
from oops.utils.net import encode_url, parse_repository_url


@click.command(name="fix")
@click.option(
    "--no-commit",
    is_flag=True,
    help="Do not commit automatically at the end",
)
def main(no_commit: bool):  # noqa: C901, PLR0912
    """Fix submodules"""

    # 1. Prune unused submodules
    # 2. Rename submodules
    # 3. Rewrite submodules

    repo = Repo()

    if not repo.submodules:
        click.echo("No submodules found.")
        return 0

    symlinks = list_symlinks(repo.working_dir)
    broken_symlinks = list_symlinks(repo.working_dir, broken_only=True)
    new_urls = []
    deprecated_repos = []

    for submodule in repo.submodules:
        scheme, owner, repository = parse_repository_url(submodule.url)
        repository_name = f"{owner}/{repository}"

        # Check URL scheme
        if config.sub_force_scheme and config.sub_force_scheme != scheme:
            new_urls.append((submodule.name, encode_url(submodule.url, config.sub_force_scheme)))

        # Check deprecated repositories
        if repository_name in config.sub_deprecated_repositories:
            deprecated_repos.append(
                (submodule.name, config.sub_deprecated_repositories[repository_name])
            )

    # Fix submodule URLs
    if new_urls:
        click.echo("The following submodule URLs will be updated:")
        for name, new_url in new_urls:
            click.echo(f"  {name}: {new_url}")
            submodule = repo.submodules[name]
            repo.git.submodule("set-url", submodule.path, new_url)

        click.echo("Staging submodule URL changes...")
        repo.index.add([Path(repo.working_dir) / ".gitmodules"])

        if not no_commit and repo.index.diff("HEAD"):
            click.echo("Committing submodule URL changes...")
            repo.index.commit(
                commit_messages.submodule_fix_urls.format(
                    description="\n".join(f"- {name}: {url}" for name, url in new_urls)
                )
            )
