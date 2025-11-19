#!/usr/bin/env python3
import os
import sys
from pathlib import Path

import click

from oops.gitutils import (
    add_submodule,
    commit,
    git_add,
    git_config_submodule,
    git_top,
    submodule_sync,
    submodule_update,
)
from oops.helpers import str_to_list
from oops.io import (
    desired_path,
    ensure_parent,
    relpath,
)
from oops.messages import (
    GIT_SUBMODULE_ADD,
    GIT_SUBMODULE_ADD_DESC,
)
from oops.net import parse_repository_url
from oops.render import human_readable, render_table
from oops.settings import NEW_SUBMODULES_PATH


def find_addons(submodule_dir: Path):
    """Return addon directories (contain __manifest__.py or __openerp__.py)."""
    addons = []
    for root, dirs, files in os.walk(submodule_dir):
        # speed: ignore .git and typical junk
        if ".git" in dirs:
            dirs.remove(".git")
        if "__manifest__.py" in files or "__openerp__.py" in files:
            addons.append(Path(root))
    return addons


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
    default=NEW_SUBMODULES_PATH,
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
@click.command(name="add")
def main(  # noqa: C901, PLR0915
    url: str,
    branch: str,
    base_dir: str,
    name: str,
    addons: str,
    **options,
):
    """Add a git submodule and optionally create symlinks for its addons."""

    addons_to_link = str_to_list(addons) if addons else []
    auto_symlinks = options["auto_symlinks"]
    no_commit = options["no_commit"]
    dry_run = options["dry_run"]

    repo = git_top()
    os.chdir(repo)

    # Compute target path and name
    try:
        _, owner, repo_name = parse_repository_url(url)
    except ValueError as e:
        click.echo(f"Error: {e}")
        sys.exit(1)

    sub_path_str = desired_path(url, base_dir)
    sub_path = repo / sub_path_str
    sub_name = name or f"{owner}/{repo_name}"

    # Plan summary
    rows = [
        ["Repo Root", repo],
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
        return 0

    # Safety: prevent overwrite
    if sub_path.exists():
        click.echo(f"Error: destination already exists: {sub_path_str}", file=sys.stderr)
        sys.exit(1)

    ensure_parent(sub_path)

    # Add submodule
    click.echo("[add] git submodule add")
    # FIXME: checkout to the branch before commit
    add_submodule(url, sub_name, sub_path_str, branch=branch)

    # Pin branch in .gitmodules (redundant but explicit)
    click.echo("[config] record branch in .gitmodules")

    if branch:
        git_config_submodule(str(repo / ".gitmodules"), sub_name, "branch", branch)

    # Sync and fetch content
    submodule_sync()
    submodule_update()

    created_links = []

    def create_symlink(addon_dir: Path):
        link_name = f"{addon_dir.name}"
        link_path = repo / link_name
        # Determine relative target from repo root to the addon_dir
        target_rel = relpath(repo, addon_dir)
        if link_path.exists() or link_path.is_symlink():
            click.echo(f"  [skip] {link_name} already exists")
            return
        os.symlink(target_rel, link_path)
        created_links.append(link_name)
        # Stage symlink
        git_add([link_name])

    if auto_symlinks or addons:
        click.echo("[scan] detecting addon folders…")
        addons_found = find_addons(sub_path)
        if not addons_found:
            click.echo("  no addon folders detected.")
        else:
            click.echo(
                f"  found {len(addons_found)} addon folder(s). Creating symlinks at repo root…"
            )

            source = (
                addons_found
                if auto_symlinks
                else filter(lambda item: item.name in addons_to_link, addons_found)
            )

            for addon_dir in source:
                create_symlink(addon_dir)

        if addons:
            diff = set(addons_to_link).difference(set(created_links))
            if diff:
                click.echo(f"Addons not found: {human_readable(diff)}")

    # Stage .gitmodules and submodule path
    git_add([".gitmodules", sub_path_str])

    if not no_commit:
        commit(
            GIT_SUBMODULE_ADD.format(name=sub_name),
            description=GIT_SUBMODULE_ADD_DESC.format(
                url=url,
                branch=branch,
                path=sub_path_str,
                symlinks=human_readable(created_links) if created_links else 0,
            ),
        )
        click.echo("✅ Submodule added and committed.")
    else:
        click.echo("⚠️ Changes staged but not committed (--no-commit).")

    return 0
