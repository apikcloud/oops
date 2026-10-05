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
from oops.core.metadata import get_metadata
from oops.core.models import ProjectStatus, Result
from oops.io.file import parse_odoo_version
from oops.output.formatters import FormatterRegistry, JsonFormatter, MetricsConsoleFormatter
from oops.output.sinks import deliver
from oops.services.docker import get_image_updates
from oops.services.git import get_last_commit, require_repository
from oops.services.github import get_latest_workflow_run
from oops.utils.net import get_public_repo_url, parse_repository_url
from oops.utils.versioning import get_last_release, get_next_releases
from oops_engine.compat import Optional

from .presenters.show import ShowPresenter

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
def main(token: Optional[str], output_format: str, output_path: Path):

    metadata = get_metadata()

    repo, repo_path = require_repository()
    formatter = FORMATTERS[output_format]()

    result: Result[ProjectStatus] = Result()

    # 2. Long-running processing.
    with live_progress("Initialisation..."):
        status = ProjectStatus(project=repo_path.name)

        # --- Odoo ---
        try:
            status.image = parse_odoo_version(repo_path)
        except (FileNotFoundError, ValueError) as e:
            result.add_error(str(e) or "Could not parse Odoo version.")

        try:
            status.updates = get_image_updates(status.image)
        except requests.RequestException as e:
            status.updates_error = True
            result.add_warning(f"Could not fetch image updates: {e}")

        # --- Git ---
        try:
            remote_url = repo.remote("origin").url
            status.remote_url = get_public_repo_url(remote_url) or None
            _, owner, repo_name = parse_repository_url(remote_url)
        except (ValueError, IndexError):
            owner = ""
            repo_name = ""

        try:
            status.branch = repo.active_branch.name
        except TypeError:  # detached HEAD
            status.branch = None

        status.last_release = get_last_release() or None
        try:
            minor, fix, major = get_next_releases()
            status.next_releases = {"fix": fix, "minor": minor, "major": major}
        except ValueError:
            status.next_releases = None

        status.last_commit = get_last_commit(str(repo_path))

        # --- Optional GitHub Actions ---
        if token and owner and repo_name:
            try:
                status.ci = get_latest_workflow_run(owner=owner, repo=repo_name, token=token, branch="main")
                if not status.ci:
                    result.add_warning("Could not fetch latest GitHub Actions workflow run.")
            except requests.RequestException as e:
                result.add_warning(f"GitHub Actions fetch failed: {e}")

        result.data = status

    # 4. Prepare for the chosen audience and render.
    output = ShowPresenter().prepare(result, target=formatter.target, metadata=metadata)
    deliver(formatter, output, output_format, output_path)
