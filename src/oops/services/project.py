# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: project.py — oops/services/project.py

"""Project-state helpers: validate the local layout and resolve the Odoo image."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import click
import git
from oops.core.checks import Check, CheckContext, CheckOutcome
from oops.core.config import ProjectConfig, config
from oops.core.exceptions import (
    APIError,
    MissingRecommendedFiles,
    OopsError,
)
from oops.core.metadata import update_metadata
from oops.core.models import ImageInfo, Result
from oops.io.file import parse_odoo_version
from oops.utils.net import sparse_clone


@dataclass
class ProjectCheckContext(CheckContext):
    path: Path
    config: ProjectConfig
    strict: bool


class CheckMandatoryFiles(Check[ProjectCheckContext]):
    name = "check_mandatory_files"
    label = "Project mandatory files"

    def _run(self) -> Result[CheckOutcome]:

        cfg = self.ctx.config
        files = set(os.listdir(self.ctx.path))
        missing_files = cfg.mandatory_files.difference(files)

        return self._resolve(list(missing_files), "Mandatory file is missing: {item}")
        # self.result.add_warning(MissingMandatoryFiles.message.format(files=missing_files))


class CheckRecommendedFiles(Check[ProjectCheckContext]):
    name = "check_recommended_files"
    label = "Project recommended files"

    def _run(self) -> Result[CheckOutcome]:

        cfg = self.ctx.config
        files = set(os.listdir(self.ctx.path))
        missing_recommended_files = cfg.recommended_files.difference(files)

        if missing_recommended_files:
            self.result.add_warning(MissingRecommendedFiles.message.format(files=missing_recommended_files))

        self.add(status="passed")
        return self.result


def require_project(repo_path: Path) -> ImageInfo:
    """Guard: assert all mandatory files exist, then parse and return the Odoo version.

    Intended as the first call inside commands that need an initialised project
    (e.g. ``oops project update``, ``oops project init``).

    Args:
        repo_path: Root directory of the git repository.

    Returns:
        Parsed :class:`~oops.core.models.ImageInfo` from ``odoo_version.txt``.

    Raises:
        OopsError: If any mandatory file is missing. Recorded by
            :class:`~oops.commands.base.OopsCommand` telemetry as ``Exit(1)``.
        click.UsageError: If ``odoo_version.txt`` is empty or its format is
            unrecognised. Formatted by Click without triggering the telemetry
            error path.
    """
    present = set(os.listdir(repo_path))
    missing = config.project.mandatory_files.difference(present)
    if missing:
        raise OopsError(
            f"This command requires an initialised project. Missing mandatory files: {', '.join(sorted(missing))}."
        )
    try:
        image_info = parse_odoo_version(repo_path)
        update_metadata(odoo_version=str(image_info.major_version))
        return image_info
    except (FileNotFoundError, ValueError) as e:
        raise click.UsageError(
            f"Could not parse {config.project.file_odoo_version}. "
            "Make sure the file contains a valid Odoo Docker image tag."
        ) from e


def fetch_project_files(
    url: str,
    branch: "str | None",
    files: list[str],
    tmpdir: Path,
) -> None:
    """Sparse-clone the listed files/directories from a remote repository.

    Raises:
        APIError: If the remote clone fails.
    """
    try:
        sparse_clone(url, tmpdir, files, branch)
    except git.GitCommandError as exc:
        raise APIError(f"Clone failed: {exc.stderr.strip()}") from exc


def copy_project_files(
    tmpdir: Path,
    files: list[str],
    repo_path: Path,
) -> list[str]:
    """Copy fetched files from *tmpdir* into the local repository.

    Returns:
        Subset of *files* actually present in *tmpdir* and copied.
    """
    applied: list[str] = []
    for f in files:
        src = tmpdir / f
        dst = repo_path / f
        if not src.exists():
            continue
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        applied.append(f)
    return applied
