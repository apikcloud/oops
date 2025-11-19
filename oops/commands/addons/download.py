#!/usr/bin/env python3

import logging
import os
import shutil
import tempfile
from pathlib import Path

import click

from oops.core.messages import commit_messages
from oops.git.gitutils import commit, git_add, git_top, update_gitignore
from oops.services.github import fetch_branch_zip
from oops.utils.compat import Optional
from oops.utils.helpers import str_to_list
from oops.utils.io import find_addons
from oops.utils.net import parse_repository_url

logging.basicConfig(level=logging.INFO)


@click.command(name="download")
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
    """Download and extract addons from a git repository branch zip."""

    local_repo = git_top()
    gitignore = local_repo / ".gitignore"
    url, owner, repo = parse_repository_url(url)
    addons = [] if addons_list is None else str_to_list(addons_list)

    options = {}
    if token:
        options["token"] = token
    with tempfile.TemporaryDirectory() as tmpdirname:
        _, extracted_root = fetch_branch_zip(owner, repo, branch, tmpdirname, **options)

        if extracted_root is None:
            click.Abort("You're fucked")
            return 1

        logging.debug(extracted_root)
        logging.debug(os.listdir(extracted_root))

        new_addons = []
        skipped_addons = []
        for addon in find_addons(Path(extracted_root)):
            if addons and addon.technical_name not in addons:
                skipped_addons.append(addon.technical_name)
                continue

            target_path = local_repo / addon.technical_name

            # FIXME: check duplicates (addon already exists) and version before copying

            try:
                logging.debug(f"Copy {addon.technical_name} from {addon} to {target_path}")
                shutil.copytree(addon.path, target_path)
            except FileExistsError:
                logging.warning(f"Skip {addon.technical_name}")
                skipped_addons.append(addon.technical_name)
                continue

            new_addons.append(addon.technical_name)

        if skipped_addons:
            logging.debug(" ".join(skipped_addons))

        if not new_addons:
            return 0

        logging.info(f"Addons added ({len(new_addons)}): {', '.join(new_addons)}")
        if exclude:
            update_gitignore(gitignore, new_addons)
            git_add([gitignore])
            commit(commit_messages.addons_ignored, skip_hook=True)
