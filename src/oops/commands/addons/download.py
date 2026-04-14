# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: download.py — oops/commands/addons/download.py

"""
Download addons from a GitHub repository branch.

Clones the repository over SSH (depth=1) into a temporary directory,
discovers addon directories, and copies them into the current project.
Downloaded addons are added to .gitignore (unless --no-exclude is passed).
"""

import shutil
import tempfile
from pathlib import Path

import click
import git
from oops.commands.base import command
from oops.io.file import file_updater, find_addons, read_tagged_block
from oops.services.git import commit, get_local_repo
from oops.utils.compat import Optional
from oops.utils.helpers import str_to_list
from oops.utils.net import encode_url
from oops.utils.render import print_warning


@command(name="download", help=__doc__)
@click.argument("url")
@click.argument("branch")
@click.option("--addons", "addons_list", help="Comma-separated addon names to copy (copies all if omitted).")
@click.option("--exclude/--no-exclude", is_flag=True, default=True, help="Add downloaded addons to .gitignore.")
def main(url: str, branch: str, exclude: bool, addons_list: Optional[str] = None):
    repo, repo_path = get_local_repo()

    ssh_url = encode_url(url, "ssh")
    addons = [] if addons_list is None else str_to_list(addons_list)

    with tempfile.TemporaryDirectory() as tmpdirname:
        tmpdir = Path(tmpdirname)

        click.echo(f"↓ Cloning {ssh_url} ({branch}) …")
        try:
            git.Repo.clone_from(ssh_url, str(tmpdir), depth=1, branch=branch)
        except git.GitCommandError as exc:
            raise click.ClickException(f"Clone failed: {exc.stderr.strip()}") from exc

        new_addons = []
        skipped_addons = []
        for addon in find_addons(tmpdir):
            if addons and addon.technical_name not in addons:
                continue

            target_path = repo_path / addon.technical_name

            # FIXME: check version before copying
            try:
                shutil.copytree(addon.path, target_path)
            except FileExistsError:
                skipped_addons.append(addon.technical_name)
                continue

            new_addons.append(addon.technical_name)

        if skipped_addons:
            print_warning(f"Skipped (already exists): {', '.join(skipped_addons)}")

        if not new_addons:
            click.echo("No addons downloaded.")
            raise click.Abort()

        click.echo(f"Downloaded ({len(new_addons)}): {', '.join(new_addons)}")

        if exclude:
            gitignore = repo_path / ".gitignore"
            start_tag = "# oops:addons:start"
            end_tag = "# oops:addons:end"

            block = read_tagged_block(gitignore, start_tag, end_tag)
            existing = {
                ln.strip()
                for ln in block.splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            }

            merged = "\n".join(sorted(existing | {f"{a}/" for a in new_addons}))
            if file_updater(str(gitignore), merged, start_tag=start_tag, end_tag=end_tag):
                commit(repo, repo_path, [".gitignore"], "addons_ignored", skip_hooks=True)
