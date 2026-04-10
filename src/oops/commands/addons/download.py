# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: download.py — oops/commands/addons/download.py

"""
Download and extract addons from a GitHub repository branch.

Fetches the branch as a ZIP archive, extracts addon directories into the
working directory, and adds them to .gitignore (unless --no-exclude is passed).
A GitHub token can be provided via --token or the TOKEN / GH_TOKEN / GITHUB_TOKEN
environment variables.
"""

import logging
import shutil
import tempfile
from pathlib import Path

import click
from oops.commands.base import command
from oops.io.file import find_addons, update_gitignore
from oops.services.git import commit, get_local_repo
from oops.services.github import fetch_branch_zip
from oops.utils.compat import Optional
from oops.utils.helpers import str_to_list
from oops.utils.net import parse_repository_url


@command(name="download", help=__doc__)
@click.argument("url")
@click.argument("branch")
@click.option("--token", envvar=["TOKEN", "GH_TOKEN", "GITHUB_TOKEN"])
@click.option("--addons", "addons_list", help="List of addons separated by commas")
@click.option("--exclude/--no-exclude", is_flag=True, default=True)
def main(
    url: str,
    branch: str,
    exclude: bool,
    token: Optional[str] = None,
    addons_list: Optional[str] = None,
):

    repo, repo_path = get_local_repo()

    _, owner, repo_name = parse_repository_url(url)
    addons = [] if addons_list is None else str_to_list(addons_list)

    options = {}
    if token:
        options["token"] = token

    with tempfile.TemporaryDirectory() as tmpdirname:
        _, extracted_root = fetch_branch_zip(owner, repo_name, branch, tmpdirname, **options)

        if extracted_root is None:
            raise click.UsageError("Download failed.")

        logging.debug(extracted_root)

        new_addons = []
        skipped_addons = []
        for addon in find_addons(Path(extracted_root)):
            if addons and addon.technical_name not in addons:
                skipped_addons.append(addon.technical_name)
                continue

            target_path = repo_path / addon.technical_name

            # FIXME: check duplicates (addon already exists) and version before copying

            try:
                logging.debug("Copy %s from %s to %s", addon.technical_name, addon, target_path)
                shutil.copytree(addon.path, target_path)
            except FileExistsError:
                logging.warning("Skip %s (already exists)", addon.technical_name)
                skipped_addons.append(addon.technical_name)
                continue

            new_addons.append(addon.technical_name)

        if skipped_addons:
            logging.debug("Skipped: %s", " ".join(skipped_addons))

        if not new_addons:
            click.echo("No addons downloaded.")
            raise click.Abort()

        click.echo(f"Addons downloaded ({len(new_addons)}): {', '.join(new_addons)}")

        if exclude:
            update_gitignore(repo_path / ".gitignore", new_addons)
            commit(repo, repo_path, [".gitignore"], "addons_ignored", skip_hooks=True)
