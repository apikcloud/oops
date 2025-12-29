#!/usr/bin/env python3

import os
from pathlib import Path

from oops.core.config import config
from oops.core.exceptions import MissingMandatoryFiles, MissingRecommendedFiles
from oops.utils.io import read_and_parse


def check_project(path: Path, strict: bool = True) -> tuple:
    files = set(os.listdir(path))
    missing_files = config.project_mandatory_files.difference(files)
    warnings = []
    errors = []

    if missing_files:
        if strict:
            raise MissingMandatoryFiles(missing_files)
        else:
            warnings.append(MissingMandatoryFiles.message.format(files=missing_files))

    missing_recommended_files = config.project_recommended_files.difference(files)
    if missing_recommended_files:
        if strict:
            raise MissingRecommendedFiles(missing_recommended_files)
        else:
            warnings.append(MissingRecommendedFiles.message.format(files=missing_recommended_files))

    return warnings, errors


def parse_packages(path: Path) -> list:
    return read_and_parse(path / config.project_file_packages)


def parse_requirements(path: Path) -> list:
    return read_and_parse(path / config.project_file_requirements)


def parse_odoo_version(path: Path) -> str:
    res = read_and_parse(path / config.project_file_odoo_version)
    if not res:
        raise ValueError()
    return res[0]
