#!/usr/bin/env python3


from pathlib import Path

import click
from git import Repo

from oops.commands.project.common import parse_odoo_version
from oops.core.messages import commit_messages
from oops.services.docker import find_available_images, format_available_images, parse_image_tag
from oops.utils.io import write_text_file
from oops.utils.tools import ask


@click.command(name="update")
@click.option("--force", is_flag=True, help="Don't ask for confirmation")
def main(force: bool):  # noqa: C901
    """Update odoo image in odoo_version.txt to the latest available."""

    repo = Repo()
    current_version = parse_odoo_version(Path(repo.working_dir))
    image_infos = parse_image_tag(current_version)

    if not image_infos.release:
        click.echo("Current odoo version does not specify a release date, cannot proceed")
        return 1

    available_images = find_available_images(
        release=image_infos.release,
        version=image_infos.major_version,
        enterprise=image_infos.enterprise,
    )

    if not available_images:
        click.echo("No available images found")
        return 0

    if force:
        new_image = available_images[0]
    else:
        click.echo(format_available_images(available_images, include_index=True))
        answer = ask("Select new image [0]: ", default="0")
        try:
            new_image = available_images[int(answer)]
        except (ValueError, IndexError):
            click.echo("Invalid selection, aborting")
            return 1

    click.echo(f"Update odoo image to: {new_image.image}")

    odoo_version_file = Path(repo.working_dir) / "odoo_version.txt"
    write_text_file(odoo_version_file, [new_image.image])

    repo.index.add([str(odoo_version_file)])
    repo.index.commit(
        commit_messages.image_update.format(
            old=current_version, new=new_image.image, days=new_image.delta
        ),
        skip_hooks=True,
    )
