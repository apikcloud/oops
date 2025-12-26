import click
from git import Repo

from oops.core.messages import commit_messages
from oops.utils.git import is_pull_request
from oops.utils.io import desired_path, get_symlink_map
from oops.utils.tools import ask


@click.command("rename")
@click.option("--dry-run", is_flag=True, help="Show planned changes only")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
@click.option("--prompt/--no-prompt", is_flag=True, default=True, help="Prompt before renaming")
@click.option(
    "--pull-request", "--pr", "force_pr", is_flag=True, help="Mark submodules as pull request"
)
@click.argument("names", nargs=-1, required=False)
def main(dry_run: bool, no_commit: bool, prompt: bool, force_pr: bool, names: tuple[str] = None):
    """
    Rename git submodules to match new naming conventions.
    """

    repo = Repo()

    if not repo.submodules:
        click.echo("No .gitmodules found.")
        raise click.Abort()

    # FIXME: assume there is only one symlink per submodule for now
    mapping = get_symlink_map(repo.working_dir)

    for submodule in repo.submodules:
        # TODO: filter by names if given
        if names and submodule.name not in names:
            continue

        pull_request = force_pr or is_pull_request(submodule)
        first_symlink = mapping.get(submodule.path) if pull_request else None
        new_name = desired_path(
            submodule.url,
            pull_request=pull_request,
            suffix=first_symlink,
        )

        if submodule.name != new_name:
            click.echo(f"Renaming submodule '{submodule.name}' -> '{new_name}' (PR={pull_request})")

            if prompt:
                ans = ask("Apply change for ? [Y/n/e] ", default="y")
                if ans in ("n", "no"):
                    continue
                elif ans == "e":
                    custom = input("Enter custom name: ").strip()
                    if custom:
                        new_name = custom

            if not dry_run:
                submodule.rename(new_name)
                try:
                    submodule.rename(new_name)
                except Exception as e:
                    click.echo(f"Error renaming submodule {submodule.name}: {e}")
                    return 1

    if not no_commit and not dry_run:
        if repo.index.diff(repo.head.commit):
            click.echo("Committing changes...")
            repo.index.commit(commit_messages.submodules_rename, skip_hooks=True)
    else:
        click.echo("Done. Commit .gitmodules changes to share them with the team.")
