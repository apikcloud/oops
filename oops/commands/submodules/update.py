# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: update.py — oops/commands/submodules/update.py

"""
Fetch and pull submodules to their latest upstream commit.

For each submodule with a configured branch, fetches from origin, checks out
the branch, and pulls the latest commits. Specific submodules can be targeted
by name; PR submodules can be skipped with --skip-pr.
"""

import click

from oops.commands.base import command
from oops.utils.git import commit, get_local_repo, is_pull_request
from oops.utils.render import print_success, print_warning


@command("update", help=__doc__)
@click.option("--dry-run", is_flag=True, help="Show planned changes only")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
@click.option("--skip-pr", is_flag=True, help="Skip submodules that are pull requests")
@click.argument("names", nargs=-1, required=False)
def main(dry_run: bool, no_commit: bool, skip_pr: bool, names: "tuple[str] | None" = None):

    repo, repo_path = get_local_repo()
    changes = []
    files = []

    if not repo.submodules:
        raise click.UsageError("No .gitmodules found.")

    for submodule in repo.submodules:
        if names and submodule.name not in names:
            continue
        if not submodule.path:
            print_warning(f"Missing path for {submodule.name}, skipping.")
            continue

        if not submodule.branch:
            print_warning(f"No branch defined for {submodule.name}, skipping.")
            continue

        if skip_pr and is_pull_request(submodule):
            print_warning(f"Submodule {submodule.name} is a pull request, skipping.")
            continue

        click.echo(f"Updating {submodule.name} to latest of '{submodule.branch}'...")

        if dry_run:
            continue

        sub_repo = submodule.module()
        branch = submodule.branch_name

        # Ensure repo is up to date
        sub_repo.remotes.origin.fetch()
        # Checkout the configured branch
        sub_repo.git.checkout(branch)

        # Pull latest commits
        sub_repo.remotes.origin.pull(branch)

        # Stage submodule update in parent repo
        files.append(submodule.path)
        changes.append(f"{submodule.name} ({submodule.branch})")

    if not no_commit and not dry_run:
        commit(
            repo,
            repo_path,
            files,
            "submodules_update",
            skip_hooks=True,
            description="\n".join(changes),
        )

    print_success(
        "Submodule update complete." if not dry_run else "Dry run complete — no changes applied."
    )
