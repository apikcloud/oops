# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: manifest.py — oops/io/manifest.py


import ast
import logging
import os
from pathlib import Path

import libcst as cst

from oops.core.config import config
from oops.core.exceptions import NoManifestFound
from oops.utils.compat import Optional, Union


def parse_manifest(filepath: Path) -> dict:
    """
    Parse an Odoo manifest file,
    then safely convert it to a Python dict via ast.literal_eval.
    """
    source = filepath.read_text(encoding="utf-8")

    # Convert the exact dict literal slice to a Python object (safe: literals only).
    manifest = ast.literal_eval(source)
    if not isinstance(manifest, dict):
        logging.error("Parsed manifest is not a dict after literal evaluation.")
        return {}
    return manifest


def load_manifest(addon_dir: Path) -> dict:
    """Return the path to the manifest file in this addon directory."""
    for manifest_name in config.manifest_names:
        manifest_path = addon_dir / manifest_name
        if manifest_path.is_file():
            return parse_manifest(manifest_path)
    logging.debug(f"No Odoo manifest found in {addon_dir}")
    return {}


def get_manifest_path(addon_dir: str) -> Optional[str]:
    """Return the path to the manifest file in this addon directory."""
    for manifest_name in config.manifest_names:
        manifest_path = os.path.join(addon_dir, manifest_name)
        if os.path.isfile(manifest_path):
            return manifest_path


def parse_manifest_cst(raw: str) -> cst.CSTNode:
    return cst.parse_module(raw)


def read_manifest(path: str) -> cst.CSTNode:
    manifest_path = get_manifest_path(path)
    if not manifest_path:
        raise NoManifestFound(f"no Odoo manifest found in {path}")
    with open(manifest_path) as mf:
        return parse_manifest_cst(mf.read())


def find_addons_extended(
    addons_dir: Union[str, Path], installable_only: bool = False, names: Optional[list] = None
):
    """Yield (name, path, manifest) for each addon in the given directory."""

    if isinstance(addons_dir, str):
        addons_dir = Path(addons_dir)

    for name in os.listdir(addons_dir):
        path = addons_dir / Path(name)
        try:
            manifest = parse_manifest(path)
        except NoManifestFound:
            continue
        if installable_only and not manifest.get("installable", True):
            continue

        if names and name not in names:
            continue

        yield name, path, manifest


def find_manifests(path: str, names: Optional[list] = None):
    """Yield the path to each manifest file in the given directory."""

    for name in os.listdir(path):
        addon_path = os.path.join(path, name)
        try:
            manifest_path = get_manifest_path(addon_path)
        except NoManifestFound:
            continue

        if names and name not in names:
            continue

        yield manifest_path
