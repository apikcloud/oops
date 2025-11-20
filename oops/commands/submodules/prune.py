#!/usr/bin/env python3

import logging
import shutil

import click

from oops.core.config import config
from oops.core.messages import commit_messages
from oops.git.core import GitRepository
from oops.git.submodules import GitSubmodules
from oops.utils.io import relpath, symlink_targets


@click.command(name="prune")
@click.option(
    "--no-commit",
    is_flag=True,
    help="Do not commit automatically at the end",
)
def main(no_commit: bool):  # noqa: C901, PLR0912
    """Remove unused submodules (not referenced by any symlink) and clean old paths."""

    repo = GitRepository()
    submodules = GitSubmodules()

    if not repo.has_gitmodules:
        click.echo("No .gitmodules found.")
        return 0

    # subs = repo.parse_submodules()
    # if not subs:
    #     click.echo("No submodules found.")
    #     return 0

    targets = symlink_targets(repo.path)

    unused = []
    for submodule in repo.parse_gitmodules():
        path = repo.path / submodule.path
        rel = relpath(repo.path, path)
        if any(rel in t for t in targets):
            continue
        unused.append((submodule.name, str(path)))

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
        submodules.deinit(path, delete=True)

        # Cleanup .git/modules leftovers
        moddir = repo.path / ".git" / "modules" / path
        if moddir.exists():
            click.echo(f"[cleanup] removing {moddir}")
            shutil.rmtree(str(moddir))

    for path in [config.old_submodule_path, config.new_submodule_path]:
        old_base_path = repo.path / path

        if old_base_path.exists():
            click.echo(f"[prune] removing dir: {old_base_path}")
            try:
                old_base_path.rmdir()
            except OSError as error:
                logging.error(error)

    # TODO: improve commit functionality...
    if not no_commit:
        repo.add_all()
        repo.commit(commit_messages.submodules_prune, skip_hook=True)

    click.echo("\n✅ Unused submodules removed.")

    if no_commit:
        click.echo("Don't forget to commit: git commit -m 'chore: remove unused submodules'")

    return 0
