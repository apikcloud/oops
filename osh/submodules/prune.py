#!/usr/bin/env python3

import logging
import shutil

import click

from osh.gitutils import (
    commit,
    git_add_all,
    git_top,
    parse_submodules,
    submodule_deinit,
)
from osh.io import relpath, symlink_targets
from osh.messages import GIT_SUBMODULES_PRUNE
from osh.settings import NEW_SUBMODULES_PATH, OLD_SUBMODULES_PATH


@click.command(name="prune")
@click.option(
    "--no-commit",
    is_flag=True,
    help="Do not commit automatically at the end",
)
def main(no_commit: bool):  # noqa: C901, PLR0912
    """Remove unused submodules (not referenced by any symlink) and clean old paths."""

    repo = git_top()
    gm = repo / ".gitmodules"
    if not gm.exists():
        click.echo("No .gitmodules found.")
        return 0

    subs = parse_submodules(gm)
    if not subs:
        click.echo("No submodules found.")
        return 0

    targets = symlink_targets(repo)

    unused = []
    for name, item in subs.items():
        path = repo / item["path"]
        rel = relpath(repo, path)
        if any(rel in t for t in targets):
            continue
        unused.append((name, str(path)))

    if not unused:
        click.echo("✅ No unused submodules detected.")
        return 0

    click.echo("The following submodules appear unused (no symlinks point to them):")
    for name, path in unused:
        click.echo(f"  - {name}: {path}")

    confirm = input("\nRemove these submodules? [y/N] ").strip().lower()
    if confirm not in ("y", "yes"):
        click.echo("Aborted.")
        return 1

    for name, path in unused:
        click.echo(f"[remove] {name}: {path}")
        # Deinit + remove from index + working tree
        submodule_deinit(path, delete=True)

        # Cleanup .git/modules leftovers
        moddir = repo / ".git" / "modules" / path
        if moddir.exists():
            click.echo(f"[cleanup] removing {moddir}")
            shutil.rmtree(str(moddir))

    for path in [OLD_SUBMODULES_PATH, NEW_SUBMODULES_PATH]:
        old_base_path = repo / path

        if old_base_path.exists():
            click.echo(f"[prune] removing dir: {old_base_path}")
            try:
                old_base_path.rmdir()
            except OSError as error:
                logging.error(error)

    # TODO: improve commit functionality...
    if not no_commit:
        git_add_all()
        commit(GIT_SUBMODULES_PRUNE, skip_hook=True)

    click.echo("\n✅ Unused submodules removed.")

    if no_commit:
        click.echo("Don't forget to commit: git commit -m 'chore: remove unused submodules'")

    return 0
