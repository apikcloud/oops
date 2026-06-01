# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: materialize.py — oops/commands/addons/materialize.py

"""
Replace addon symlinks with a real copy of the addon directory.

Useful when you need to modify a third-party addon locally. The symlink is
removed and its target directory is copied in place. Only symlinks are
processed; real directories are skipped.

By default all symlinks found at the repository root are processed.
Use --include to restrict to a subset, or --exclude to skip specific addons.
"""

import click
from oops.commands.base import command, render_and_exit
from oops.core.compat import Optional
from oops.core.logger import live_progress, log
from oops.core.models import Result
from oops.io.file import materialize_symlink
from oops.output.formatters import OutputFormatter, SimpleSummaryConsoleFormatter
from oops.services.git import commit_v2, require_repository
from oops.utils.helpers import str_to_list
from oops.utils.render import human_readable

from .presenters.materialize import MaterializePresenter


@command("materialize", help=__doc__)
@click.option(
    "--include",
    default=None,
    metavar="ADDONS",
    help="Comma-separated list of addon names to materialize (default: all symlinks).",
)
@click.option(
    "--exclude",
    default=None,
    metavar="ADDONS",
    help="Comma-separated list of addon names to skip.",
)
@click.option("--dry-run", is_flag=True, help="Show what would happen, do nothing.")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
@click.pass_context
def main(ctx, include: Optional[str], exclude: Optional[str], dry_run: bool, no_commit: bool):
    if include and exclude:
        raise click.UsageError("--include and --exclude are mutually exclusive.")

    formatter: OutputFormatter = SimpleSummaryConsoleFormatter()

    result: Result[dict] = Result({"cmd": "Materialize addons", "rows": [], "dry_run": dry_run})
    assert result.data is not None

    repo, repo_path = require_repository()

    candidates = sorted(p for p in repo_path.iterdir() if p.is_symlink())

    if include:
        include_set = set(str_to_list(include))
        candidates = [p for p in candidates if p.name in include_set]
    elif exclude:
        exclude_set = set(str_to_list(exclude))
        candidates = [p for p in candidates if p.name not in exclude_set]

    changes = []

    with live_progress("Materializing addons…"):
        for addon_path in candidates:
            if dry_run:
                result.data["rows"].append({"addon": addon_path.name, "action": "planned"})
                continue

            log.info(f"Materializing {addon_path.name}…")
            try:
                materialize_symlink(addon_path, dry_run=False)
            except Exception as error:
                result.add_error(f"Failed to materialize {addon_path.name}: {error}")
                result.data["rows"].append({"addon": addon_path.name, "action": "failed"})
                continue

            result.data["rows"].append({"addon": addon_path.name, "action": "materialized"})
            changes.append(addon_path)

    if not no_commit and changes and not dry_run:
        commit_result = commit_v2(
            repo,
            repo_path,
            [str(path) for path in changes],
            "addons_materialize",
            names=human_readable([str(path.name) for path in changes], sep="\n"),
            remove_and_add=True,
        )
        result.merge(commit_result)

    output = MaterializePresenter().prepare(result, target=formatter.target)
    render_and_exit(result, formatter, output, "text", None)
