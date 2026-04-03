# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: info.py — oops/commands/project/info.py

"""
Display a summary of the current project.

Shows Odoo version, Docker image release date, available image updates,
Python requirements, system packages, git remote and release info.
With a GitHub token, also shows the latest Actions workflow run.
"""

import click
from oops.commands.base import command

from oops.commands.project.common import (
    check_project,
    parse_odoo_version,
    parse_packages,
    parse_requirements,
)
from oops.git import (
    get_last_commit,
    get_last_release,
    get_next_releases,
)
from oops.git.core import GitRepository
from oops.services.docker import check_image, find_available_images, parse_image_tag
from oops.services.github import get_latest_workflow_run
from oops.utils.render import format_datetime, human_readable, render_table


@command(name="info", help=__doc__)
@click.option(
    "--token",
    envvar=["TOKEN", "GH_TOKEN", "GITHUB_TOKEN"],
    help="GitHub token to request API, needs actions:read or repo scope."
    " Envvar is also supported: TOKEN, GH_TOKEN, GITHUB_TOKEN.",
)
@click.option(
    "--minimal",
    is_flag=True,
    help="Show minimal output.",
)
def main(token: str, minimal: bool):  # noqa: C901

    repo = GitRepository()

    warnings, errors = check_project(repo.path, strict=False)
    packages = parse_packages(repo.path)
    requirements = parse_requirements(repo.path)
    odoo_version = parse_odoo_version(repo.path)
    image_infos = parse_image_tag(odoo_version)
    warnings += check_image(image_infos, strict=False)
    last_release = get_last_release()
    url, owner, repo_name = repo.get_remote_url()

    try:
        minor, fix, major = get_next_releases()
        next_releases = f"minor: {minor}, fix: {fix}, major: {major}"
    except ValueError:
        next_releases = "no valid release found"

    if image_infos.release:
        available_images = find_available_images(
            release=image_infos.release,
            version=image_infos.major_version,
            enterprise=image_infos.enterprise,
        )

        if available_images:
            latest = available_images[0]
            message = (
                f"Found {len(available_images)} available images, "
                f"the latest is {latest.delta} days newer ({latest.release.isoformat()})"
            )
        else:
            message = "No available images found"

    else:
        message = "Current odoo version does not specify a release date, cannot proceed"

    last_commit = get_last_commit()

    rows = [
        ["Odoo version", f"{image_infos.major_version} ({image_infos.edition})"],
        ["Date of current image", image_infos.release or "no valid release found"],
        ["Registry", image_infos.source],
        ["Available image(s)", message],
        ["System package(s)", human_readable(packages) or "--"],
        ["Python requirement(s)", human_readable(requirements, sep=", ") or "--"],
        ["Git:", ""],
        ["Remote URL", url or "no remote found"],
        ["Last release", last_release or "no valid release found"],
        ["Next release", next_releases],
        ["Last commit", str(last_commit) if last_commit else "no valid commit found"],
    ]

    if not minimal and token:
        res = get_latest_workflow_run(owner=owner, repo=repo_name, token=token, branch="main")

        if not res:
            errors.append("Could not fetch latest GitHub Actions workflow run")
        else:
            rows.append(["GitHub Actions:", ""])
            rows.append(["Last run:", str(res)])
            rows.append(["Date", f"{format_datetime(res.date)} ({res.age} days ago)"])
            rows.append(["URL", res.url])

    if warnings:
        for row in warnings:
            rows.append([click.style("Warning", fg="yellow"), click.style(row, fg="yellow")])

    if errors:
        for row in errors:
            rows.append([click.style("Error", fg="red"), click.style(row, fg="red")])

    click.echo(render_table(rows))
