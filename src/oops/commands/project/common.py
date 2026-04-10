# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: common.py — oops/commands/project/common.py

# TODO: move to utils

import os
from pathlib import Path

from oops.core.config import config
from oops.core.exceptions import MissingMandatoryFiles, MissingRecommendedFiles


def check_project(path: Path, strict: bool = True) -> tuple:
    files = set(os.listdir(path))
    missing_files = config.project.mandatory_files.difference(files)
    warnings = []
    errors = []

    if missing_files:
        if strict:
            raise MissingMandatoryFiles(missing_files)
        else:
            warnings.append(MissingMandatoryFiles.message.format(files=missing_files))

    missing_recommended_files = config.project.recommended_files.difference(files)
    if missing_recommended_files:
        if strict:
            raise MissingRecommendedFiles(missing_recommended_files)
        else:
            warnings.append(MissingRecommendedFiles.message.format(files=missing_recommended_files))

    return warnings, errors
