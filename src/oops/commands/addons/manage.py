# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: manage.py — src/oops/commands/addons/manage.py

"""Interactively link or unlink addons from submodules at the repo root."""

import os
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.exceptions import AppAbort, NotFoundError
from oops.io.file import relpath
from oops.io.manifest import find_addons_extended
from oops.services.git import commit, list_available_addons, require_repository, require_submodules
from oops.utils.render import (
    colorize,
    conclude,
    get_console,
    make_table,
    prompt_choices,
    prompt_confirm,
    rule,
)


def _show_summary(added: set, removed: set) -> None:
    rows = [[colorize("+ link", "green"), name] for name in sorted(added)] + [
        [colorize("- unlink", "red"), name] for name in sorted(removed)
    ]
    columns = [("Action", "dim", "left"), ("Addon", "brand.primary", "left")]
    rule("Pending changes")
    get_console().print(make_table(title=None, columns=columns, rows=rows))


def _create_symlinks(repo_path: Path, added: set, available: dict) -> list:
    # TODO: refactor and move to io/file.py
    from oops.utils.render import print_warning

    created = []
    for name in sorted(added):
        link = repo_path / name
        if link.exists() or link.is_symlink():
            print_warning(f"{name} — already exists, skipping")
            continue
        os.symlink(relpath(repo_path, available[name]), link)
        created.append(name)
    return created


def _remove_symlinks(repo_path: Path, removed: set) -> list:
    # TODO: refactor and move to io/file.py
    from oops.utils.render import print_warning

    unlinked = []
    for name in sorted(removed):
        link = repo_path / name
        if not link.is_symlink():
            print_warning(f"{name} — not a symlink, skipping")
            continue
        link.unlink()
        unlinked.append(name)
    return unlinked


@command("manage", help=__doc__)
@click.option(
    "--no-commit",
    is_flag=True,
    help="If set, symlink changes will not be committed.",
)
def main(no_commit: bool):

    repo, repo_path = require_repository()
    require_submodules(repo)

    existing = {name for name, _, _ in find_addons_extended(repo_path)}
    available: dict = {name: path for name, path, _ in list_available_addons(repo, repo_path)}

    if not available:
        raise NotFoundError("No addons found in any submodule.")

    result = prompt_choices("Select addon(s): ", set(available.keys()), existing)
    if result is None:
        raise AppAbort()

    selected = set(result)
    previously_selected = existing & set(available.keys())

    added = selected - previously_selected
    removed = previously_selected - selected

    if not added and not removed:
        click.echo("Nothing to do.")
        return

    _show_summary(added, removed)

    if not prompt_confirm("\nProceed?", default=True):
        raise AppAbort()

    created = _create_symlinks(repo_path, added, available)
    unlinked = _remove_symlinks(repo_path, removed)

    total = len(created) + len(unlinked)
    if not total:
        click.echo("Nothing to do.")
        return

    if not no_commit:
        if created:
            commit(repo, repo_path, created, "addons_new", skip_hooks=True)
        if unlinked:
            commit(repo, repo_path, unlinked, "addons_remove", remove=True, skip_hooks=True)

    conclude(True, f"{total} change(s) applied.")
