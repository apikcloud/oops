#!/usr/bin/env python3


import click

from oops.docker import find_available_images, format_available_images, parse_image_tag
from oops.gitutils import commit, git_add, git_top
from oops.io import ask, write_text_file
from oops.messages import GIT_ODOO_IMAGE_UPDATE
from oops.project.common import parse_odoo_version


@click.command(name="update")
@click.option("--force", is_flag=True, help="Don't ask for confirmation")
def main(force: bool):  # noqa: C901
    """Update odoo image in odoo_version.txt to the latest available."""

    repo = git_top()
    current_version = parse_odoo_version(repo)
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

    odoo_version_file = repo / "odoo_version.txt"
    write_text_file(odoo_version_file, [new_image.image])

    git_add([odoo_version_file])
    commit(
        GIT_ODOO_IMAGE_UPDATE.format(
            old=current_version, new=new_image.image, days=new_image.delta
        ),
        skip_hook=True,
    )
