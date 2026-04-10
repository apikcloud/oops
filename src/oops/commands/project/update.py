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

import click
import requests
from oops.commands.base import command
from oops.core.config import config
from oops.io.file import parse_odoo_version, write_text_file
from oops.services.docker import find_available_images, format_available_images
from oops.services.git import commit, get_local_repo


@command(name="update", help=__doc__)
@click.option("--force", is_flag=True, help="Don't ask for confirmation")
def main(force: bool):  # noqa: C901
    repo, repo_path = get_local_repo()

    try:
        image_info = parse_odoo_version(repo_path)
    except ValueError as e:
        raise click.ClickException(str(e) or "Could not parse current Odoo version.") from e

    if not image_info.release:
        raise click.ClickException("Current Odoo version does not specify a release date, cannot proceed.")

    try:
        available_images = find_available_images(
            release=image_info.release,
            version=image_info.major_version,
            enterprise=image_info.enterprise,
        )
    except requests.RequestException as e:
        raise click.ClickException(f"Failed to fetch available images: {e}") from e

    if not available_images:
        raise click.ClickException("No newer images found.")

    if force:
        new_image = available_images[0]
    else:
        click.echo(format_available_images(available_images, include_index=True))
        answer = click.prompt("Select new image", default="1")
        try:
            # Remove 1 to match the index as we display from 1 to n.
            answer = 1 if int(answer) <= 0 else int(answer) - 1
            new_image = available_images[answer]
        except (ValueError, IndexError) as e:
            raise click.ClickException("Invalid selection.") from e

    click.echo(f"Updating Odoo image to: {new_image.image}")

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
