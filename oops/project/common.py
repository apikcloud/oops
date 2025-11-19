#!/usr/bin/env python3

import os
from pathlib import Path

from oops.exceptions import MissingMandatoryFiles, MissingRecommendedFiles
from oops.io import read_and_parse
from oops.settings import (
    PROJECT_FILE_ODOO_VERSION,
    PROJECT_FILE_PACKAGES,
    PROJECT_FILE_REQUIREMENTS,
    PROJECT_MANDATORY_FILES,
    PROJECT_RECOMMENDED_FILES,
)


def check_project(path: Path, strict: bool = True) -> tuple:
    files = set(os.listdir(path))
    missing_files = PROJECT_MANDATORY_FILES.difference(files)
    warnings = []
    errors = []

    if missing_files:
        if strict:
            raise MissingMandatoryFiles(missing_files)
        else:
            warnings.append(MissingMandatoryFiles.message.format(files=missing_files))

    missing_recommended_files = PROJECT_RECOMMENDED_FILES.difference(files)
    if missing_recommended_files:
        if strict:
            raise MissingRecommendedFiles(missing_recommended_files)
        else:
            warnings.append(MissingRecommendedFiles.message.format(files=missing_recommended_files))

    return warnings, errors


def parse_packages(path: Path) -> list:
    return read_and_parse(path / PROJECT_FILE_PACKAGES)


def parse_requirements(path) -> list:
    return read_and_parse(path / PROJECT_FILE_REQUIREMENTS)


def parse_odoo_version(path) -> str:
    res = read_and_parse(path / PROJECT_FILE_ODOO_VERSION)
    if not res:
        raise ValueError()
    return res[0]
