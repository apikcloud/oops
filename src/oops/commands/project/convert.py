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
import shutil
import tempfile
from datetime import date
from pathlib import Path

import click
import requests
from oops.commands.base import command
from oops.core.config import config
from oops.core.exceptions import APIError, AppAbort, ConfigError, EarlyExit, OopsError
from oops.core.logger import live_progress
from oops.core.models import ImageInfo, Plan, PlanAction, Result
from oops.io.file import write_text_file
from oops.output.helper import render_and_raise
from oops.output.workflow import run_mutation_workflow
from oops.services.docker import find_available_images
from oops.services.git import commit_v2, require_repository
from oops.services.project import fetch_project_files
from oops.utils.helpers import normalize_version_arg
from oops.utils.render import colorize, conclude, prompt_select, rule
from oops_engine.compat import Tuple


def _build_plan(
    files: set[str],
    existing_files: set[str],
    image: ImageInfo,
    version: str,
    file_odoo_version: str,
) -> Plan:
    """Build the bootstrap plan as pure data — no I/O, no prompts.

    `existing_files` is the subset of `files` actually present in the
    sparse-cloned tmpdir. Only those are scheduled as "copy" actions.
    The version file is always scheduled as a "write" action regardless.
    """
    actions = []
    for f in sorted(files - {file_odoo_version}):
        if f in existing_files:
            actions.append(PlanAction(label=f, kind="copy", detail="from sync source"))
    actions.append(
        PlanAction(
            label=file_odoo_version,
            kind="write",
            detail=image.image,
            data={"image": image.image},
        )
    )
    return Plan(title=f"Bootstrap Odoo {version}", actions=actions)


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
@click.option("--no-commit", is_flag=True, help="Stage changes but do not commit.")
@click.option("-f", "--force", is_flag=True, help="Skip confirmation prompt.")
def main(version: str, release: str | None, enterprise: bool, no_commit: bool, force: bool) -> None:
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

    # 1. Image selection — pre-plan: the chosen image informs the plan content
    with live_progress("Fetching available images…"):
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

    # 2. Fetch files — pre-mutation: tmpdir must outlive the workflow apply calls
    tmpdir_obj = tempfile.TemporaryDirectory()
    tmpdir = Path(tmpdir_obj.name)
    try:
        with live_progress(f"Cloning {remote_url}…"):
            fetch_project_files(remote_url, branch, list(files), tmpdir)

        existing_files = {f for f in files if (tmpdir / f).exists()}
        if not existing_files:
            raise OopsError("Sync source returned no files — cannot bootstrap.")

        # 3. Build plan (pure: which files to copy, which to write)
        plan = _build_plan(files, existing_files, new_image, version, config.project.file_odoo_version)

        # 4. Mutation for one plan action
        def apply(action: PlanAction) -> Tuple[str, bool]:
            if action.kind == "write":
                write_text_file(repo_path / action.label, [action.data["image"]])
                return colorize("written", "green"), True
            src = tmpdir / action.label
            dst = repo_path / action.label
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            return colorize("copied", "green"), True

        # 5. Present plan, confirm, apply
        outer: Result[None] = Result()
        result = run_mutation_workflow(
            plan=plan,
            apply=apply,
            outer=outer,
            title=f"Bootstrap Odoo {version}",
            force=force,
            select=False,
            empty_message="Nothing to convert.",
        )
    finally:
        tmpdir_obj.cleanup()

    # 6. Commit
    all_files = [a.label for a in plan.actionable]
    if not no_commit:
        outer.merge(
            commit_v2(
                local_repo,
                repo_path,
                all_files,
                "project_bootstrap",
                skip_hooks=True,
                version=version,
                image=new_image.image,
            )
        )
    else:
        outer.add_warning("Don't forget to commit changes.")

    render_and_raise(result, outer)
