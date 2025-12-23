from pathlib import Path

import click

from oops.core.messages import commit_messages
from oops.git.core import GitRepository
from oops.git.gitutils import (
    rename_submodule,
)
from oops.utils.io import ask, desired_path, is_pull_request_path, symlink_targets


@click.command("rename")
@click.option("--dry-run", is_flag=True, help="Show planned changes only")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
@click.option("--prompt/--no-prompt", is_flag=True, default=True, help="Prompt before renaming")
def main(dry_run: bool, no_commit: bool, prompt: bool):
    """
    Rename git submodules to match new naming conventions.
    """

    repo = GitRepository()

    if not repo.has_gitmodules:
        click.echo("No .gitmodules found.")
        raise click.Abort()

    # FIXME: assume there is only one symlink per submodule for now
    symlinks = {str(Path(t).parent): Path(t).name for t in symlink_targets(repo.path)}

    for submodule in repo.parse_gitmodules():
        pull_request = is_pull_request_path(submodule.path) or is_pull_request_path(submodule.name)
        first_symlink = symlinks.get(submodule.path) if pull_request else None
        new_name = desired_path(
            submodule.url,
            pull_request=pull_request,
            suffix=first_symlink,
        )

        if submodule.name != new_name:
            click.echo(f"Renaming submodule '{submodule.name}' -> '{new_name}'")

            if prompt:
                ans = ask(f"Apply change for '{submodule.name}' ? [Y/n/e] ", default="y")
                if ans in ("n", "no"):
                    continue
                elif ans == "e":
                    custom = input("Enter custom name: ").strip()
                    if custom:
                        new_name = custom

            rename_submodule(
                str(repo.gitmodules),
                submodule.name,
                new_name,
                submodule.path,
                submodule.url,
                submodule.branch,
                dry_run,
            )

    if not no_commit and not dry_run:
        click.echo("Committing changes...")
        repo.add([str(repo.gitmodules), ".git/config"])
        repo.commit(commit_messages.submodules_rename, skip_hook=True)
    else:
        click.echo("Done. Commit .gitmodules changes to share them with the team.")
