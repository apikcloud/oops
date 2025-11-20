import subprocess

import click

from oops.core.messages import commit_messages
from oops.git.core import GitRepository
from oops.git.gitutils import update_from
from oops.utils.io import ask


@click.command("update")
@click.option("--dry-run", is_flag=True, help="Show planned changes only")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
def main(dry_run: bool, no_commit: bool):
    """
    Update git submodules to their latest upstream versions.
    """

    repo = GitRepository()

    if not repo.has_gitmodules:
        click.echo("No .gitmodules found.")
        raise click.Abort()

    changes = []
    for submodule in repo.parse_gitmodules():
        if not submodule.path:
            click.echo(f"⚠️  Missing path for {submodule.name}, skipping.")
            continue

        if not submodule.branch:
            click.echo(f"⏭️  No branch defined for submodule {submodule.name}, skipping.")
            continue

        if submodule.pr:
            click.echo(f"⚠️  Submodule {submodule.name} looks like a pull request.")
            answer = ask("Are you sure you want to update it? [y/N]: ", default="n")
            if answer != "y":
                click.echo(f"⏭️  Skipping pull request submodule {submodule.path}.")
                continue

        click.echo(f"🔄 Updating {submodule.name} to latest of '{submodule.branch}'...")

        if dry_run:
            continue

        try:
            # fetch and checkout the branch
            update_from(submodule.path, submodule.branch)
            changes.append(submodule.path)
        except subprocess.CalledProcessError as e:
            click.echo(f"❌ Failed to update {submodule.path}: {e}")
            continue

    if not no_commit and not dry_run:
        click.echo("Committing changes...")
        repo.add([str(repo.gitmodules)] + changes)
        repo.commit(commit_messages.submodules_update, skip_hook=True)

    click.echo("✅ Submodules updated to their upstream branches.")
