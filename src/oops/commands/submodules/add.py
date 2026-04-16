# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: add.py — oops/commands/submodules/add.py

"""
Add a git submodule and optionally create symlinks for its addons.

Clones the repository as a submodule under the base directory (default:
.third-party), records the tracked branch, and optionally creates symlinks at
the repo root for every addon found or for a specific list.
"""

import os
from pathlib import Path

import click
from git import GitCommandError
from oops.commands.base import command
from oops.core.config import config
from oops.core.messages import commit_messages
from oops.io.file import (
    desired_path,
    ensure_parent,
    find_addon_dirs,
    relpath,
)
from oops.services.git import get_local_repo, read_gitmodules
from oops.utils.helpers import str_to_list
from oops.utils.net import parse_repository_url
from oops.utils.render import human_readable, print_error, print_success, print_warning, render_table


@click.argument(
    "url",
)
@click.option(
    "-b",
    "--branch",
    help="Branch to track for the submodule (e.g., 18.0)",
)
@click.option(
    "--base-dir",
    default=lambda: config.submodules.current_path,
    help="Base dir for submodules (default: .third-party)",
)
@click.option(
    "--name",
    help="Optional submodule name (defaults to '<ORG>/<REPO>')",
)
@click.option(
    "--auto-symlinks",
    is_flag=True,
    help="Auto-create symlinks at repo root for each addon folder detected in the submodule",
)
@click.option(
    "--addons",
    help="List of addons for which to create symlinks (default: '')",
)
@click.option(
    "--no-commit",
    is_flag=True,
    help="Do not commit automatically at the end",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show planned actions only",
)
@click.option(
    "--pull-request",
    is_flag=True,
    help="Indicates that the submodule is a pull request (affects naming)",
)
@command(name="add", help=__doc__)
def main(  # noqa: C901, PLR0915, PLR0913
    url: str,
    branch: str,
    base_dir: str,
    name: str,
    addons: str,
    **options,
):

    addons_to_link = str_to_list(addons) if addons else []
    auto_symlinks = options["auto_symlinks"]
    no_commit = options["no_commit"]
    pull_request = options["pull_request"]
    dry_run = options["dry_run"]

    repo, repo_path = get_local_repo()

    # Compute target path and name
    try:
        _, owner, repo_name = parse_repository_url(url)
    except ValueError as e:
        print_error(str(e))
        raise click.exceptions.Exit(1) from e

    suffix = addons_to_link[0] if addons_to_link and pull_request else None
    sub_path_str = desired_path(url, prefix=base_dir, pull_request=pull_request, suffix=suffix)

    sub_path = repo_path / sub_path_str
    sub_name = desired_path(url, pull_request=pull_request, suffix=suffix)

    # Plan summary
    rows = [
        ["Repo Root", repo_path],
        ["URL", url],
        ["Branch", branch],
        ["Submodule name", sub_name],
        ["Target path", sub_path_str],
        ["Auto symlinks", human_readable(auto_symlinks)],
        ["Addons", addons or ""],
        ["Commit at the end", human_readable(not no_commit)],
        ["Dry-run", human_readable(dry_run)],
    ]
    click.echo(render_table(rows))

    if dry_run:
        print_warning("This is a dry run. No changes will be made.")
        raise click.Abort()

    # Safety: prevent overwrite
    if sub_path.exists():
        print_error(f"Destination already exists: {sub_path_str}")
        raise click.exceptions.Exit(1)

    ensure_parent(sub_path)

    # Add submodule
    click.echo("[add] git submodule add")
    # FIXME: check if git submodule folder exists before trying to create (.git/modules/<org>/<repo>)
    try:
        repo.create_submodule(
            name=sub_name,
            path=sub_path_str,
            url=url,
            branch=branch,
        )
    except GitCommandError as exc:
        print_error(f"Failed to add submodule: {exc}")
        raise click.exceptions.Exit(1) from exc

    # Pin branch in .gitmodules (redundant but explicit)
    click.echo("[config] record branch in .gitmodules")

    if branch:
        gitmodules = read_gitmodules(repo)
        click.echo(f"Setting branch {branch!r} for submodule {sub_name!r}...")
        gitmodules.set_value(f'submodule "{sub_name}"', "branch", branch)

    created_links = []

    def create_symlink(addon_dir: Path):
        link_name = f"{addon_dir.name}"
        link_path = repo_path / link_name
        # Determine relative target from repo root to the addon_dir
        target_rel = relpath(repo_path, addon_dir)
        if link_path.exists() or link_path.is_symlink():
            click.echo(f"  [skip] {link_name} already exists")
            return
        os.symlink(target_rel, link_path)
        created_links.append(link_name)
        # Stage symlink
        repo.index.add([link_name])

    if auto_symlinks or addons:
        click.echo("[scan] detecting addon folders…")
        addons_found = [addon for addon in find_addon_dirs(sub_path, with_pr=pull_request)]
        if not addons_found:
            click.echo("  no addon folders detected.")
        else:
            click.echo(f"  found {len(addons_found)} addon folder(s). Creating symlinks at repo root…")

            source = addons_found if auto_symlinks else filter(lambda item: item.name in addons_to_link, addons_found)

            for addon_dir in source:
                create_symlink(addon_dir)

        if addons:
            diff = set(addons_to_link).difference(set(created_links))
            if diff:
                click.echo(f"Addons not found: {human_readable(diff)}")

    # Stage .gitmodules and submodule path
    repo.index.add([".gitmodules", sub_path_str])

    if not no_commit:
        repo.index.commit(
            commit_messages.submodule_add.format(
                name=sub_name,
                url=url,
                branch=branch,
                path=sub_path_str,
                symlinks=human_readable(created_links) if created_links else 0,
            ),
        )
        print_success("Submodule added and committed.")
    else:
        print_warning("Changes staged but not committed (--no-commit).")
