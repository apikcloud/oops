# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: convert.py — src/oops/commands/project/convert.py

"""
Bootstrap an existing repository as an oops-managed Odoo project.

Fetches the mandatory template files from the configured sync source,
prompts the user to pick the Odoo Docker image closest to a requested
release date (or the most recent one), writes ``odoo_version.txt``, and
creates a single ``project_bootstrap`` commit.

The command refuses to run if the repository already has every file
declared in ``config.project.mandatory_files``.
"""

from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path

import click
import requests
from oops.commands.base import command
from oops.core.config import config
from oops.core.exceptions import APIError, AppAbort, ConfigError, EarlyExit, OopsError
from oops.io.file import write_text_file
from oops.services.docker import find_available_images
from oops.services.git import commit, require_repository
from oops.services.project import copy_project_files, fetch_project_files
from oops.utils.helpers import normalize_version_arg
from oops.utils.render import conclude, get_console, print_success, prompt_select, rule
from rich.live import Live
from rich.spinner import Spinner


@command("convert", help=__doc__)
@click.option(
    "--version",
    "-v",
    required=True,
    callback=normalize_version_arg,
    help="Target Odoo major version (e.g. '19' or '19.0').",
)
@click.option(
    "--release",
    "-r",
    default=None,
    help="Target release date as YYYY-MM-DD. If omitted, the most recent image is preselected.",
)
@click.option(
    "--enterprise/--no-enterprise",
    default=True,
    help="Use the enterprise edition (default) or the community edition.",
)
def main(version: str, release: str | None, enterprise: bool) -> None:
    local_repo, repo_path = require_repository()

    missing = config.project.mandatory_files - set(os.listdir(repo_path))
    if not missing:
        conclude(True, "Project already bootstrapped — every mandatory file is present.")
        raise EarlyExit()

    remote_url = config.sync.remote_url
    branch = config.sync.branch
    files: set[str] = set(config.sync.files) | config.project.recommended_files | config.project.mandatory_files

    if not remote_url:
        raise ConfigError("sync.remote_url is not configured. Set it in ~/.oops.yaml or .oops.yaml.")
    if not branch:
        raise ConfigError("sync.branch is not configured. Set it in ~/.oops.yaml or .oops.yaml.")

    try:
        target_date: date | None = date.fromisoformat(release) if release else None
    except ValueError as exc:
        raise click.UsageError(f"--release must be YYYY-MM-DD (got {release!r}).") from exc

    rule(f"Bootstrap Odoo {version} project — {repo_path.name}")

    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = Path(_tmpdir)
        with Live(Spinner("dots", text=f"Cloning {remote_url} …"), refresh_per_second=10):
            fetch_project_files(remote_url, branch, list(files), tmpdir)
        applied = copy_project_files(tmpdir, list(files), repo_path)

    console = get_console()
    for f in applied:
        console.print(f"  [green]✓[/] {f}")

    if not applied:
        raise OopsError("Sync source returned no files — cannot bootstrap.")

    with Live(Spinner("dots", text="Fetching available images…"), refresh_per_second=10):
        try:
            available_images = find_available_images(
                version=float(version),
                enterprise=enterprise,
                target_date=target_date,
            )
        except requests.RequestException as e:
            raise APIError(f"Failed to fetch available images: {e}") from e

    if not available_images:
        raise OopsError(f"No images found for Odoo {version} ({'enterprise' if enterprise else 'community'}).")

    max_len = max(len(img.image) for img in available_images)
    choices = [f"{img.image:<{max_len}}   {img.release.isoformat()}  Δ{img.delta}d" for img in available_images]
    answer = prompt_select("Select Odoo image", choices)
    if not answer:
        raise AppAbort()
    new_image = available_images[choices.index(answer)]

    odoo_version_file = repo_path / config.project.file_odoo_version
    write_text_file(odoo_version_file, [new_image.image])

    all_files = list(applied)
    if config.project.file_odoo_version not in all_files:
        all_files.append(config.project.file_odoo_version)

    commit(
        local_repo,
        repo_path,
        all_files,
        "project_bootstrap",
        skip_hooks=True,
        version=version,
        image=new_image.image,
    )

    print_success(f"Image selected: {new_image.image} (released {new_image.release.isoformat()})")
    conclude(True, f"Project bootstrapped — Odoo {version} on {new_image.image}")
