# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: update.py — oops/commands/submodules/update.py

"""
Fetch and pull submodules to their latest upstream commit.

For each submodule with a configured branch, fetches from origin, checks out
the branch, and pulls the latest commits. Specific submodules can be targeted
by name; PR submodules can be skipped with --skip-pr.
"""

import click
from oops.commands.base import command, render_and_exit
from oops.core.exceptions import AppAbort, OopsError
from oops.core.logger import live_progress, log
from oops.core.models import Result
from oops.output.formatters import OutputFormatter, SimpleSummaryConsoleFormatter
from oops.services.git import browse_submodules, commit_v2, is_pull_request, require_repository, require_submodules
from oops.utils.render import prompt_choices

from .presenters.update import prepare


@command("update", help=__doc__)
@click.option("--dry-run", is_flag=True, help="Show planned changes only")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
@click.option("--skip-pr", is_flag=True, help="Skip submodules that are pull requests")
@click.option("--only-pr", is_flag=True, help="Skip submodules that are not pull requests")
@click.argument("names", nargs=-1, required=False)
@click.pass_context
def main(ctx, dry_run: bool, no_commit: bool, skip_pr: bool, only_pr: bool, names: "tuple[str] | None" = None):
    formatter: OutputFormatter = SimpleSummaryConsoleFormatter()
    outer: Result[None] = Result()
    result: Result[dict] = Result({"cmd": "Update submodules", "rows": [], "dry_run": dry_run})
    assert result.data is not None

    if skip_pr and only_pr:
        raise click.UsageError("")

    repo, repo_path = require_repository()
    submodules = require_submodules(repo)
    changes = []
    files = []

    # Ask user
    if not names:
        if skip_pr:
            candidates = set(s.name for s in submodules if not is_pull_request(s))
        elif only_pr:
            candidates = set(s.name for s in submodules if is_pull_request(s))
        else:
            candidates = set(s.name for s in submodules)

        if not candidates:
            raise OopsError("...")
        names = prompt_choices("Select submodule(s)", candidates, set())
        if names is None:
            raise AppAbort()

    with live_progress("Updating submodules…"):
        total = len(names)
        for index, submodule in browse_submodules(submodules, names):
            if not submodule.path:
                outer.add_warning(f"Missing path for {submodule.name}, skipping.")
                result.data["rows"].append({"submodule": submodule.name, "branch": "—", "action": "skipped"})
                continue

            if not submodule.branch:
                outer.add_warning(f"No branch defined for {submodule.name}, skipping.")
                result.data["rows"].append({"submodule": submodule.name, "branch": "—", "action": "skipped"})
                continue

            if dry_run:
                result.data["rows"].append(
                    {"submodule": submodule.name, "branch": submodule.branch_name, "action": "planned"}
                )
                continue

            log.info(f"{index}/{total} Updating {submodule.name}…")

            sub_repo = submodule.module()
            branch = submodule.branch_name

            sub_repo.remotes.origin.fetch()
            sub_repo.git.checkout(branch)
            sub_repo.remotes.origin.pull(branch)

            repo.git.add(submodule.path)
            files.append(submodule.path)
            changes.append(f"{submodule.name} ({submodule.branch})")
            result.data["rows"].append({"submodule": submodule.name, "branch": branch, "action": "updated"})

    if not no_commit and not dry_run:
        tmp = commit_v2(
            repo,
            repo_path,
            files,
            "submodules_update",
            skip_hooks=True,
            already_staged=True,
            description="\n".join(changes),
        )
        outer.merge(tmp)

    output = prepare(result, outer, target=formatter.target)
    render_and_exit(ctx, outer, formatter, output, "text", None)
