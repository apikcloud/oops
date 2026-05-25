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

from pathlib import Path

import click
import requests
from oops.commands.base import command
from oops.core.logger import live_progress
from oops.core.models import Result
from oops.io.file import parse_odoo_version
from oops.output.formatters import FormatterRegistry, JsonFormatter, MetricsConsoleFormatter
from oops.output.sinks import deliver
from oops.services.docker import check_image, format_image_updates
from oops.services.git import get_last_commit, require_repository
from oops.services.github import get_latest_workflow_run
from oops.services.project import check_project
from oops.utils.compat import Optional
from oops.utils.net import get_public_repo_url, parse_repository_url
from oops.utils.render import (
    format_datetime,
)
from oops.utils.versioning import get_last_release, get_next_releases

from .presenters.show import prepare

FORMATTERS: FormatterRegistry = {
    "json": JsonFormatter,
    "text": MetricsConsoleFormatter,
}


@command(name="show", help=__doc__)
@click.option(
    "--token",
    envvar=["TOKEN", "GH_TOKEN", "GITHUB_TOKEN"],
    help="GitHub token to request API, needs actions:read or repo scope."
    " Envvar is also supported: TOKEN, GH_TOKEN, GITHUB_TOKEN.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format",
)
@click.option(
    "--output-path",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the output to this path instead of stdout (json) or a temp file (html).",
)
def main(token: Optional[str], output_format: str, output_path: Path):  # noqa: C901, PLR0912, PLR0915

    repo, repo_path = require_repository()
    formatter = FORMATTERS[output_format]()

    result: Result[dict] = Result()

    # 2. Long-running processing.
    with live_progress("Initialisation..."):
        outer = check_project(repo_path, strict=False)
        result.data = {"project": repo_path.name}

        try:
            image_info = parse_odoo_version(repo_path)
            outer.merge(check_image(image_info, strict=False))
        except (FileNotFoundError, ValueError) as e:
            outer.add_error(str(e) or "Could not parse Odoo version.")
            image_info = None

        # --- Odoo panel ---
        odoo_values = [
            ["Version", f"{image_info.major_version} ({image_info.edition})" if image_info else "—"],
            ["Image date", image_info.release.isoformat() if image_info and image_info.release else "—"],
            ["Registry", image_info.source if image_info else "—"],
            ["Update(s)", format_image_updates(image_info)],
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

        result.data["metrics"] = {
            "odoo": odoo_values,
            "git": git_values,
        }

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
                    result.data["metrics"]["actions"] = gha_values
                else:
                    outer.add_warning("Could not fetch latest GitHub Actions workflow run.")
            except requests.RequestException as e:
                outer.add_warning(f"GitHub Actions fetch failed: {e}")

    # 4. Prepare for the chosen audience and render.
    output = prepare(result, outer, target=formatter.target)
    deliver(formatter, output, output_format, output_path)
