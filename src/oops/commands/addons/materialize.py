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

from pathlib import Path

import click
from oops.commands.base import command
from oops.core.compat import Optional, Tuple
from oops.core.models import Plan, PlanAction, Result
from oops.io.file import materialize_symlink
from oops.output.helper import render_and_raise
from oops.output.workflow import run_mutation_workflow
from oops.services.git import commit_v2, require_repository
from oops.utils.helpers import str_to_list
from oops.utils.render import colorize, human_readable


def _build_plan(candidates: list) -> Plan:
    """Build materialize plan from symlink candidates — pure data, no I/O."""
    return Plan(
        title="Addons to materialize",
        actions=[
            PlanAction(label=p.name, kind="available", data={"path": str(p)})
            for p in candidates
        ],
    )


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
@click.option("--no-commit", is_flag=True, help="Do not commit changes.")
@click.option("-f", "--force", is_flag=True, help="Apply all changes without prompting.")
def main(include: Optional[str], exclude: Optional[str], no_commit: bool, force: bool) -> None:
    if include and exclude:
        raise click.UsageError("--include and --exclude are mutually exclusive.")

    repo, repo_path = require_repository()

    candidates = sorted(p for p in repo_path.iterdir() if p.is_symlink())

    if include:
        include_set = set(str_to_list(include))
        candidates = [p for p in candidates if p.name in include_set]
    elif exclude:
        exclude_set = set(str_to_list(exclude))
        candidates = [p for p in candidates if p.name not in exclude_set]

    # 1. Build the plan (pure business logic)
    plan = _build_plan(candidates)

    # 2. Define how to execute one action; track successes for commit.
    materialized: list[str] = []

    def apply(action: PlanAction) -> Tuple[str, bool]:
        materialize_symlink(Path(action.data["path"]), dry_run=False)
        materialized.append(action.data["path"])
        return colorize("materialized", "green"), True

    # 3. Run the shared scenario (select → present → confirm → apply)
    outer: Result[None] = Result()
    result = run_mutation_workflow(
        plan=plan,
        apply=apply,
        outer=outer,
        title="Materialized addons",
        force=force,
        select_prompt="Select addon(s) to materialize: ",
        empty_message="No symlinks found to materialize.",
    )

    # 4. Command-specific side effect: commit
    if materialized and not no_commit:
        outer.merge(
            commit_v2(
                repo,
                repo_path,
                materialized,
                "addons_materialize",
                names=human_readable([Path(p).name for p in materialized], sep="\n"),
                remove_and_add=True,
            )
        )
    elif materialized:
        outer.add_warning("Don't forget to commit the materialized addons.")

    # 5. Final render (after commit), non-zero exit on errors
    render_and_raise(result, outer)
