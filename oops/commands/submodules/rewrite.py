#!/usr/bin/env python3

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

import click
from git import Repo

from oops.core.config import config
from oops.core.messages import commit_messages
from oops.utils.git import is_pull_request
from oops.utils.io import (
    desired_path,
    get_symlink_map,
    rewrite_symlink,
)
from oops.utils.tools import ask


@click.command(name="rewrite")
@click.option(
    "--base-dir",
    default=config.new_submodule_path,
    help="Base directory for rewritten paths (default: .third-party)",
)
@click.option("-f", "--force", is_flag=True, help="Apply all changes without prompting")
@click.option("--dry-run", is_flag=True, help="Show planned changes only")
@click.option(
    "--no-commit",
    is_flag=True,
    help="Do not commit automatically at the end",
)
@click.argument("names", nargs=-1, required=False)
def main(
    base_dir: str, force: bool, dry_run: bool, no_commit: bool, names: Optional[tuple[str]] = None
):  # noqa: C901, PLR0912, PLR0915
    """
    Rewrite submodule paths to be under a common base dir (e.g. .third-party).
    Also rewrites symlinks.
    """

    repo = Repo()

    if not repo.submodules:
        click.echo("No .gitmodules found.")
        return 0

    # FIXME: assume there is only one symlink per submodule for now
    mapping = get_symlink_map(repo.working_dir)

    plan = []
    for submodule in repo.submodules:
        if names and submodule.name not in names:
            continue
        if not submodule.url:
            click.echo(f"[warn] submodule '{submodule.name}' has no URL, skipping")
            continue

        # Ensure we have a symlink target for this submodule
        if submodule.path not in mapping:
            click.echo(
                f"[warn] submodule '{submodule.name}' path '{submodule.path}' "
                f"has no symlink, skipping"
            )
            continue

        pull_request = is_pull_request(submodule)
        first_symlink = mapping[submodule.path] if pull_request else None
        target = desired_path(
            submodule.url, prefix=base_dir, pull_request=pull_request, suffix=first_symlink
        )

        if submodule.path != target:
            plan.append((submodule, target))

    if not plan:
        click.echo("No submodule needs rewriting.")
        return 0

    for submodule, new_path in plan:
        click.echo(
            f"[plan] {submodule.name}\n  url : {submodule.url}\n  path: {submodule.path} -> {new_path}"
        )

    accepted = []
    for submodule, new_path in plan:
        if force:
            accepted.append((submodule, new_path))
        else:
            ans = ask(
                f"\nApply change for '{submodule.name}' ({submodule.path} -> {new_path})? [Y/n/e] ",
                default="y",
            )
            if ans in ("y", "yes"):
                accepted.append((submodule, new_path))
            elif ans == "e":
                custom = input("Enter custom target path: ").strip()
                if custom:
                    accepted.append((submodule, custom))
    if not accepted:
        click.echo("Nothing accepted. Exiting.")
        return 0

    # Move submodules
    moved = []
    for submodule, new_path in accepted:
        # capture before move (GitPython mutates it)
        old_path = str(submodule.path)
        moved.append((old_path, str(new_path)))
        if not dry_run:
            submodule.move(new_path)

        logging.debug(moved)

    if dry_run:
        click.echo("\nDry run mode, no changes applied.")
        for oldp, newp in moved:
            click.echo(f"[dry-run] {oldp} -> {newp}")
        return 0

    # Rewrite symlinks
    # Build a quick lookup for old->new prefixes
    rewrites = 0
    for root, dirs, files in os.walk(repo.working_dir):
        if ".git" in dirs:
            dirs.remove(".git")
        for name in dirs + files:
            p = Path(root) / name
            if p.is_symlink():
                for oldp, newp in moved:
                    logging.debug(p, ":", oldp, "->", newp)
                    if rewrite_symlink(p, oldp, newp):
                        rewrites += 1
                        repo.index.add([str(p)])
                        break

    click.echo(f"Symlinks rewritten: {rewrites}")

    # Remove old base dir if it exists
    if config.old_submodule_path.exists():
        shutil.rmtree(config.old_submodule_path)
        repo.index.remove([str(config.old_submodule_path)], r=True, f=True)
        click.echo(f"Removed old submodule base dir: {config.old_submodule_path}")

    # Auto commit
    # TODO: add description of changes
    if not no_commit and not dry_run and repo.index.diff(repo.head.commit):
        repo.index.commit(
            commit_messages.submodules_rewrite,
            skip_hooks=True,
        )

        click.echo("Changes committed.")
    else:
        click.echo("Changes staged but not committed (--no-commit).")
