# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: prune.py — oops/commands/submodules/prune.py

"""
Remove submodules that are not referenced by any symlink.

Iterates over all submodules, checks whether any symlink in the repository
points to the submodule path, and removes those that are unused. Specific
submodules can be targeted by passing their names as arguments.
"""

from pathlib import Path

import click
from oops.commands.base import command
from oops.core.compat import Optional
from oops.core.exceptions import AppAbort, EarlyExit
from oops.core.logger import live_progress, log
from oops.core.messages import commit_messages
from oops.core.models import Result, Rows
from oops.io.file import list_symlinks, relpath
from oops.output.helper import render
from oops.services.git import require_repository, require_submodules
from oops.utils.render import colorize, conclude, prompt_confirm, render_panel


def _is_used(repo_path: Path, path: Path, symlinks: list) -> bool:

    rel = relpath(repo_path, path)
    if any(rel in t for t in symlinks):
        return True
    return False


@command(name="prune", help=__doc__)
@click.option(
    "--no-commit",
    is_flag=True,
    help="Do not commit automatically at the end",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show planned changes only",
)
@click.argument("names", nargs=-1, required=False)
@click.pass_context
def main(ctx, no_commit: bool, dry_run: bool, names: "Optional[tuple[str]]" = None):  # noqa: C901, PLR0912

    repo, repo_path = require_repository()
    submodules = require_submodules(repo)

    symlinks = list_symlinks(repo_path)
    candidates = []
    unused = []

    result: Result[Rows] = Result(
        Rows(
            columns=[("Name", "brand.primary", "left"), ("Status", "dim", "center")],
            rows=[],
            metrics={"total": 0, "planned": 0, "success": 0, "failed": 0, "skipped": 0},
        )
    )

    outer: Result[None] = Result()

    with live_progress("Looking for unused submodules..."):
        # Check for unused submodules
        for submodule in submodules:
            log.info(f"Checking {submodule.name}")

            if names and submodule.name not in names:
                continue

            path = repo_path / Path(submodule.path)

            if _is_used(repo_path, path, symlinks):
                result.data.rows.append([submodule.name, "skipped"])
                result.data.metrics["skipped"] += 1
                continue

            result.data.metrics["planned"] += 1
            candidates.append(submodule)
            unused.append(submodule.name)

    if not unused:
        conclude(True, "Nothing to do, no unused submodules detected.")
        raise EarlyExit()

    render_panel(f"{len(unused)} submodules are about to be removed", "\n".join(unused))

    if not prompt_confirm("Proceed?", default=True):
        raise AppAbort()

    for submodule in candidates:
        name = submodule.name
        try:
            submodule.remove(force=True, dry_run=dry_run)
            row = [name, colorize("removed", "green")]
            result.data.metrics["success"] += 1
        except Exception as error:
            outer.add_error(str(error))
            row = [name, colorize("failed", "red")]
            result.data.metrics["failed"] += 1

        result.data.rows.append(row)

    result.data.rows.sort(key=lambda item: item[0])
    result.data.metrics["total"] = len(result.data.rows)

    if not no_commit:
        try:
            repo.index.commit(commit_messages.submodules_prune, skip_hooks=True)
        except Exception as error:
            outer.add_error(str(error))

    if no_commit:
        outer.add_warning("Don't forget to commit: git commit -m 'chore: remove unused submodules'")

    render(result, outer)

    if not outer.ok:
        ctx.exit(1)
