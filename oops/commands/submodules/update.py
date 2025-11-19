import subprocess

import click

from oops.core.messages import commit_messages
from oops.git.gitutils import commit, git_add, load_repo, parse_gitmodules, update_from
from oops.utils.io import ask


@click.command("update")
@click.option("--dry-run", is_flag=True, help="Show planned changes only")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
def main(dry_run: bool, no_commit: bool):
    """
    Update git submodules to their latest upstream versions.
    """

    repo, gitmodules = load_repo()

    if not gitmodules:
        click.echo("No .gitmodules found.")
        raise click.Abort()

    changes = []
    for name, path, branch, _, pull_request in parse_gitmodules(gitmodules):
        if not path:
            click.echo(f"⚠️  Missing path for {name}, skipping.")
            continue

        if not branch:
            click.echo(f"⏭️  No branch defined for submodule {name}, skipping.")
            continue

        if pull_request:
            click.echo(f"⚠️  Submodule {name} looks like a pull request.")
            answer = ask("Are you sure you want to update it? [y/N]: ", default="n")
            if answer != "y":
                click.echo(f"⏭️  Skipping pull request submodule {path}.")
                continue

        click.echo(f"🔄 Updating {name} to latest of '{branch}'...")

        if dry_run:
            continue

        try:
            # fetch and checkout the branch
            update_from(path, branch)
            changes.append(path)
        except subprocess.CalledProcessError as e:
            click.echo(f"❌ Failed to update {path}: {e}")
            continue

    if not no_commit and not dry_run:
        click.echo("Committing changes...")
        git_add([str(gitmodules)] + changes)
        commit(commit_messages.submodules_update, skip_hook=True)

    click.echo("✅ Submodules updated to their upstream branches.")
