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
from git import Repo

from oops.core.messages import commit_messages
from oops.utils.git import is_pull_request


@click.command("update", help=__doc__)
@click.option("--dry-run", is_flag=True, help="Show planned changes only")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
@click.option("--skip-pr", is_flag=True, help="Skip submodules that are pull requests")
@click.argument("names", nargs=-1, required=False)
def main(dry_run: bool, no_commit: bool, skip_pr: bool, names: "tuple[str] | None" = None):

    repo = Repo()
    changes = []

    if not repo.submodules:
        raise click.UsageError("No .gitmodules found.")

    for submodule in repo.submodules:
        if names and submodule.name not in names:
            continue
        if not submodule.path:
            click.echo(f"⚠️  Missing path for {submodule.name}, skipping.")
            continue

        if not submodule.branch:
            click.echo(f"⏭️  No branch defined for submodule {submodule.name}, skipping.")
            continue

        if skip_pr and is_pull_request(submodule):
            click.echo(f"⏭️  Submodule {submodule.name} is a pull request, skipping.")
            continue

        click.echo(f"🔄 Updating {submodule.name} to latest of '{submodule.branch}'...")

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
        repo.git.add(submodule.path)
        changes.append(f"{submodule.name} ({submodule.branch})")

    if not no_commit and not dry_run:
        if not repo.index.diff(repo.head.commit):
            click.echo("No changes to commit.")
            raise click.exceptions.Exit(0)

        click.echo("Committing changes...")
        desc = "\n".join(changes)
        repo.index.commit(
            commit_messages.submodules_update.format(description=desc), skip_hooks=True
        )

    click.echo("✅ Submodules updated to their upstream branches.")
