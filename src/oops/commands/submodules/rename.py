# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: rename.py — oops/commands/submodules/rename.py

"""
Rename submodules to match the <ORG>/<REPO> naming convention.

Computes the canonical name from the submodule URL and renames it if it
differs. Prompts for confirmation on each change unless --no-prompt is passed.
Specific submodules can be targeted by name.
"""

import click

from oops.commands.base import command
from oops.io.file import desired_path, get_symlink_map
from oops.io.tools import ask
from oops.services.git import commit, get_local_repo, is_pull_request


@command("rename", help=__doc__)
@click.option("--dry-run", is_flag=True, help="Show planned changes only")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
@click.option("--prompt/--no-prompt", is_flag=True, default=True, help="Prompt before renaming")
@click.option(
    "--pull-request", "--pr", "force_pr", is_flag=True, help="Mark submodules as pull request"
)
@click.argument("names", nargs=-1, required=False)
def main(dry_run: bool, no_commit: bool, prompt: bool, force_pr: bool, names: tuple):

    repo, repo_path = get_local_repo()

    if not repo.submodules:
        raise click.UsageError("No .gitmodules found.")

    # Assume at most one symlink per submodule
    mapping = get_symlink_map(repo.working_dir)
    changed = False

    for submodule in repo.submodules:
        if names and submodule.name not in names:
            continue

        pull_request = force_pr or is_pull_request(submodule)
        first_symlink = mapping.get(submodule.path) if pull_request else None
        new_name = desired_path(
            submodule.url,
            pull_request=pull_request,
            suffix=first_symlink,
        )

        if submodule.name == new_name:
            continue

        click.echo(f"Renaming '{submodule.name}' -> '{new_name}' (PR={pull_request})")

        if prompt:
            ans = ask(f"Apply change for '{submodule.name}'? [Y/n/e] ", default="y")
            if ans in ("n", "no"):
                continue
            elif ans == "e":
                custom = click.prompt("Enter custom name", default=new_name)
                if custom:
                    new_name = custom

        if not dry_run:
            try:
                submodule.rename(new_name)
                changed = True
            except Exception as err:
                raise click.UsageError(
                    f"Error renaming submodule '{submodule.name}': {err}"
                ) from err

    if not changed:
        click.echo(
            "Nothing to rename." if not dry_run else "Dry run complete — no changes applied."
        )
        return

    if not dry_run and not no_commit:
        commit(repo, repo_path, [".gitmodules"], "submodules_rename", skip_hooks=True)
    elif not dry_run:
        click.echo("Done. Commit .gitmodules to share changes with the team.")
