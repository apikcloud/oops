# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: show.py — oops/commands/project/show.py

"""
Display a summary of the current project.

Shows Odoo version, Docker image release date, available image updates,
git remote and release info. With a GitHub token, also shows the latest
Actions workflow run.
"""

import click
import requests
from oops.commands.base import command
from oops.io.file import parse_odoo_version
from oops.services.docker import check_image, find_available_images
from oops.services.git import get_last_commit, require_repository
from oops.services.github import get_latest_workflow_run
from oops.services.project import check_project
from oops.utils.compat import Optional
from oops.utils.net import get_public_repo_url, parse_repository_url
from oops.utils.render import (
    conclude,
    format_datetime,
    get_console,
    metrics_grid,
    metrics_panel,
    render_result,
    rule,
)
from oops.utils.versioning import get_last_release, get_next_releases


@command(name="show", help=__doc__)
@click.option(
    "--token",
    envvar=["TOKEN", "GH_TOKEN", "GITHUB_TOKEN"],
    help="GitHub token to request API, needs actions:read or repo scope."
    " Envvar is also supported: TOKEN, GH_TOKEN, GITHUB_TOKEN.",
)
def main(token: Optional[str]):  # noqa: C901, PLR0912, PLR0915

    repo, repo_path = require_repository()

    result = check_project(repo_path, strict=False)

    try:
        image_info = parse_odoo_version(repo_path)
        result.merge(check_image(image_info, strict=False))
    except (FileNotFoundError, ValueError) as e:
        result.add_error(str(e) or "Could not parse Odoo version.")
        image_info = None

    # --- Odoo panel ---
    odoo_values = [
        ["Version", f"{image_info.major_version} ({image_info.edition})" if image_info else "—"],
        ["Image date", image_info.release.isoformat() if image_info and image_info.release else "—"],
        ["Registry", image_info.source if image_info else "—"],
        ["Update(s)", _format_image_updates(image_info)],
    ]

    # --- Git panel ---
    try:
        remote_url = repo.remote("origin").url
        canonical_url = get_public_repo_url(remote_url)
        _, owner, repo_name = parse_repository_url(remote_url)
    except (ValueError, IndexError):
        canonical_url = ""
        owner = ""
        repo_name = ""

    last_release = get_last_release()
    try:
        minor, fix, major = get_next_releases()
        next_releases = f"minor: {minor}, fix: {fix}, major: {major}"
    except ValueError:
        next_releases = "no valid release found"

    last_commit = get_last_commit(str(repo_path))

    git_values = [
        ["Remote", canonical_url or "—"],
        ["Last release", last_release or "—"],
        ["Next releases", next_releases],
        ["Last commit", str(last_commit) if last_commit else "—"],
    ]

    panels = [
        metrics_panel("Odoo", odoo_values),
        metrics_panel("Git", git_values),
    ]

    # --- Optional GitHub Actions panel ---
    if token and owner and repo_name:
        try:
            run = get_latest_workflow_run(owner=owner, repo=repo_name, token=token, branch="main")
            if run:
                gha_values = [
                    ["Last run", str(run)],
                    ["Date", f"{format_datetime(run.date)} ({run.age} days ago)"],
                    ["URL", run.url],
                ]
                panels.append(metrics_panel("GitHub Actions", gha_values))
            else:
                result.add_warning("Could not fetch latest GitHub Actions workflow run.")
        except requests.RequestException as e:
            result.add_warning(f"GitHub Actions fetch failed: {e}")

    rule(f"Project status — {repo_path.name}")
    console = get_console()
    console.print(metrics_grid(*panels))
    console.print()

    render_result(result)  # raises on errors
    conclude(result.ok, "Status report")


def _format_image_updates(image_info) -> str:
    if not image_info:
        return "—"
    if not image_info.release:
        return "No release date in current image tag"
    try:
        available = find_available_images(
            release=image_info.release,
            version=image_info.major_version,
            enterprise=image_info.enterprise,
        )
    except requests.RequestException as e:
        return f"Could not fetch: {e}"
    if not available:
        return "Up to date"
    latest = available[0]
    return f"{len(available)} available, latest is {latest.delta} days newer ({latest.release.isoformat()})"
