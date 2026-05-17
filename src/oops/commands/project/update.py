# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: update.py — oops/commands/project/update.py

"""
Update odoo_version.txt to the latest available Docker image.

Queries the image registry for newer releases of the currently configured Odoo
version and prompts the user to select one. With --force, picks the latest
image automatically and commits the change.
"""

from __future__ import annotations

import click
import requests
from oops.commands.base import command
from oops.core.config import config
from oops.core.exceptions import APIError, AppAbort, OopsError
from oops.io.file import write_text_file
from oops.services.docker import find_available_images
from oops.services.git import commit, require_repository
from oops.services.project import require_project
from oops.utils.render import conclude, prompt_select, rule
from rich.live import Live
from rich.spinner import Spinner


@command(name="update", help=__doc__)
@click.option("--force", is_flag=True, help="Don't ask for confirmation")
def main(force: bool):  # noqa: C901
    repo, repo_path = require_repository()

    image_info = require_project(repo_path)

    if not image_info.release:
        raise OopsError("Current Odoo version does not specify a release date, cannot proceed.")

    rule(f"Update Odoo image — currently {image_info.image}")

    with Live(Spinner("dots", text="Fetching available images…"), refresh_per_second=10):
        try:
            available_images = find_available_images(
                release=image_info.release,
                version=image_info.major_version,
                enterprise=image_info.enterprise,
            )
        except requests.RequestException as e:
            raise APIError(f"Failed to fetch available images: {e}") from e

    if not available_images:
        raise OopsError("No newer images found.")

    if force:
        new_image = available_images[0]
    else:
        max_len = max(len(img.image) for img in available_images)
        choices = [f"{img.image:<{max_len}}   {img.release.isoformat()}  +{img.delta}d" for img in available_images]
        answer = prompt_select("Select new image", choices)
        if not answer:
            raise AppAbort()
        idx = choices.index(answer)
        new_image = available_images[idx]

    odoo_version_file = repo_path / config.project.file_odoo_version
    write_text_file(odoo_version_file, [new_image.image])

    commit(
        repo,
        repo_path,
        [config.project.file_odoo_version],
        "image_update",
        skip_hooks=True,
        old=image_info.image,
        new=new_image.image,
        days=new_image.delta,
    )

    conclude(True, f"Image updated to {new_image.image}")
