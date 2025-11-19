import click

from oops.gitutils import (
    commit,
    git_add,
    guess_submodule_name,
    load_repo,
    parse_submodules,
    rename_submodule,
)
from oops.io import ask, is_pull_request_path
from oops.messages import GIT_SUBMODULES_RENAME


@click.command("rename")
@click.option("--dry-run", is_flag=True, help="Show planned changes only")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
@click.option("--prompt/--no-prompt", is_flag=True, default=True, help="Prompt before renaming")
def main(dry_run: bool, no_commit: bool, prompt: bool):
    """
    Rename git submodules to match new naming conventions.
    """

    _, gitmodules = load_repo()

    if not gitmodules:
        click.echo("No .gitmodules found.")
        raise click.Abort()

    subs = parse_submodules(gitmodules)

    for name, values in subs.items():
        pull_request = is_pull_request_path(values["path"]) or is_pull_request_path(name)
        new_name = guess_submodule_name(values["url"], pull_request=pull_request)
        if name != new_name:
            click.echo(f"Renaming submodule '{name}' -> '{new_name}'")

            if prompt:
                ans = ask(f"Apply change for '{name}' ? [Y/n/e] ", default="y")
                if ans in ("n", "no"):
                    continue
                elif ans == "e":
                    custom = input("Enter custom name: ").strip()
                    if custom:
                        new_name = custom

            rename_submodule(str(gitmodules), name, new_name, values, dry_run)

    if not no_commit and not dry_run:
        click.echo("Committing changes...")
        git_add([str(gitmodules), ".git/config"])
        commit(GIT_SUBMODULES_RENAME, skip_hook=True)
    else:
        click.echo("Done. Commit .gitmodules changes to share them with the team.")
