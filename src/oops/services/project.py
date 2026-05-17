# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: project.py — oops/services/project.py

"""Project-state helpers: validate the local layout and resolve the Odoo image."""

import os
from pathlib import Path

import click
from oops.core.config import config
from oops.core.exceptions import MissingMandatoryFiles, MissingRecommendedFiles, OopsError
from oops.core.models import ImageInfo, Result
from oops.io.file import parse_odoo_version


def check_project(path: Path, strict: bool = True) -> Result[None]:
    files = set(os.listdir(path))
    missing_files = config.project.mandatory_files.difference(files)

    result: "Result[None]" = Result()

    if missing_files:
        if strict:
            raise MissingMandatoryFiles(missing_files)
        else:
            result.add_warning(MissingMandatoryFiles.message.format(files=missing_files))

    missing_recommended_files = config.project.recommended_files.difference(files)
    if missing_recommended_files:
        if strict:
            raise MissingRecommendedFiles(missing_recommended_files)
        else:
            result.add_warning(MissingRecommendedFiles.message.format(files=missing_recommended_files))

    return result


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
        return parse_odoo_version(repo_path)
    except (FileNotFoundError, ValueError) as e:
        raise click.UsageError(
            f"Could not parse {config.project.file_odoo_version}. "
            "Make sure the file contains a valid Odoo Docker image tag."
        ) from e
