import logging
import os
from pathlib import Path

import click
from git import Repo

from oops.core.config import config
from oops.core.messages import commit_messages
from oops.utils.io import desired_path, rewrite_symlink
from oops.utils.net import encode_url


@click.command("replace")
@click.option("--dry-run", is_flag=True, help="Show planned changes only")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
@click.argument("names", nargs=-1, required=False)
@click.argument("url")
@click.argument("branch")
def main(
    dry_run: bool, no_commit: bool, names: tuple[str] = None, url: str = None, branch: str = None
):
    """
    Replace one or more submodules with a (new) submodule
    """

    repo = Repo()

    if not repo.submodules:
        click.echo("No .gitmodules found.")
        raise click.Abort()

    not_found = [name for name in names if name not in repo.submodules]
    if not_found:
        click.echo(f"❌ Submodule(s) not found: {', '.join(not_found)}")
        return 1

    new_url = encode_url(url, config.sub_force_scheme)
    old_paths = []

    if not dry_run:
        new_name = desired_path(new_url, pull_request=False)
        new_path = desired_path(new_url, pull_request=False, prefix=str(config.new_submodule_path))

        if new_name not in repo.submodules:
            click.echo(f"Adding new submodule '{new_url}' (branch={branch})")
            repo.git.submodule(
                "add",
                "--name",
                new_name,
                "-b",
                branch,
                new_url,
                new_path,
            )
        else:
            click.echo(f"Submodule '{new_name}' already exists, skipping addition.")
            new_path = repo.submodules[new_name].path

            if branch != repo.submodules[new_name].branch:
                click.echo(f"Updating branch of existing submodule '{new_name}' to '{branch}'")
                repo.git.config(f"submodule.{new_name}.branch", branch)

    # Remove old submodules
    for name in names:
        submodule = repo.submodules[name]

        click.echo(f"Remove submodule '{submodule.name}' ('{submodule.url}', branch={branch})")

        if not dry_run:
            old_path = str(submodule.path)
            submodule.remove(force=True)
            old_paths.append(old_path)

    # Update symlinks
    # the strategy is to walk the working directory and rewrite any symlink
    # that points to an old submodule path to point to the new submodule path
    rewrites = 0
    if not dry_run:
        for root, dirs, files in os.walk(repo.working_dir):
            if ".git" in dirs:
                dirs.remove(".git")
            for name in dirs + files:
                p = Path(root) / name
                if p.is_symlink():
                    for oldp in old_paths:
                        logging.debug(p, ":", oldp, "->", new_path)
                        if rewrite_symlink(p, oldp, new_path):
                            rewrites += 1
                            repo.index.add([str(p)])
                            break

        click.echo(f"Rewrote {rewrites} symlink(s)")

    # Finally, commit changes
    if not no_commit and not dry_run and repo.index.diff(repo.head.commit):
        click.echo("Committing submodule replacements...")
        repo.index.commit(
            commit_messages.submodules_replace.format(
                description="\n".join(
                    f"- replaced '{name}' with '{new_name}' (branch={branch})" for name in names
                ),
                skip_hooks=True,
            )
        )
