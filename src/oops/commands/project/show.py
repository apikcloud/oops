# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: show.py — oops/commands/project/show.py

"""
Display a summary of the current project.

Shows Odoo version, Docker image release date, available image updates,
Python requirements, system packages, git remote and release info.
With a GitHub token, also shows the latest Actions workflow run.
"""

import click
import requests
from oops.commands.base import command
from oops.commands.project.common import check_project
from oops.io.file import (
    parse_odoo_version,
)
from oops.services.docker import check_image, find_available_images
from oops.services.git import get_last_commit, get_local_repo
from oops.services.github import get_latest_workflow_run
from oops.utils.compat import Optional
from oops.utils.net import get_public_repo_url, parse_repository_url
from oops.utils.render import format_datetime, render_table
from oops.utils.versioning import get_last_release, get_next_releases


@command(name="show", help=__doc__)
@click.option(
    "--token",
    envvar=["TOKEN", "GH_TOKEN", "GITHUB_TOKEN"],
    help="GitHub token to request API, needs actions:read or repo scope."
    " Envvar is also supported: TOKEN, GH_TOKEN, GITHUB_TOKEN.",
)
@click.option("--minimal", is_flag=True, help="Show minimal output.")
def main(token: Optional[str], minimal: bool):  # noqa: C901, PLR0912, PLR0915

    repo, repo_path = get_local_repo()

    warns, errors = check_project(repo_path, strict=False)

    try:
        image_info = parse_odoo_version(repo_path)
        warns += check_image(image_info, strict=False)
    except ValueError as e:
        errors.append(str(e) or "Could not parse Odoo version.")
        image_info = None

    # Remote URL
    try:
        remote_url = repo.remote("origin").url
        canonical_url = get_public_repo_url(remote_url)
        _, owner, repo_name = parse_repository_url(remote_url)
    except (ValueError, IndexError):
        canonical_url = ""
        owner = ""
        repo_name = ""

    # Release info
    last_release = get_last_release()
    try:
        minor, fix, major = get_next_releases()
        next_releases = f"minor: {minor}, fix: {fix}, major: {major}"
    except ValueError:
        next_releases = "no valid release found"

    # Available image updates
    if image_info and image_info.release:
        try:
            available_images = find_available_images(
                release=image_info.release,
                version=image_info.major_version,
                enterprise=image_info.enterprise,
            )
            if available_images:
                latest = available_images[0]
                image_update_msg = (
                    f"{len(available_images)} available, "
                    f"latest is {latest.delta} days newer ({latest.release.isoformat()})"
                )
            else:
                image_update_msg = "Up to date"
        except requests.RequestException as e:
            image_update_msg = f"Could not fetch: {e}"
    elif image_info:
        image_update_msg = "No release date in current image tag"
    else:
        image_update_msg = "--"

    last_commit = get_last_commit(str(repo_path))

    rows = [
        [
            "Odoo version",
            f"{image_info.major_version} ({image_info.edition})" if image_info else "--",
        ],
        [
            "Current image date",
            image_info.release.isoformat() if image_info and image_info.release else "--",
        ],
        ["Registry", image_info.source if image_info else "--"],
        ["Available update(s)", image_update_msg],
        ["Git", ""],
        ["Remote URL", canonical_url or "--"],
        ["Last release", last_release or "--"],
        ["Next releases", next_releases],
        ["Last commit", str(last_commit) if last_commit else "--"],
    ]

    if not minimal and token and owner and repo_name:
        try:
            run = get_latest_workflow_run(owner=owner, repo=repo_name, token=token, branch="main")
            if run:
                rows += [
                    ["GitHub Actions", ""],
                    ["Last run", str(run)],
                    ["Date", f"{format_datetime(run.date)} ({run.age} days ago)"],
                    ["URL", run.url],
                ]
            else:
                warns.append("Could not fetch latest GitHub Actions workflow run.")
        except requests.RequestException as e:
            warns.append(f"GitHub Actions fetch failed: {e}")

    for msg in warns:
        rows.append([click.style("Warning", fg="yellow"), click.style(msg, fg="yellow")])
    for msg in errors:
        rows.append([click.style("Error", fg="red"), click.style(msg, fg="red")])

    click.echo(render_table(rows))
