# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: manifest.py — oops/io/manifest.py

"""
Odoo manifest reading, parsing, and addon discovery.

Sections:
    - Path lookup: locate manifest files within addon directories
    - Dict parsing: read manifests as plain Python dicts (via ast.literal_eval)
    - CST parsing: read manifests as concrete syntax trees (via libcst) for lossless rewriting
    - Discovery: enumerate addons and manifest paths under a directory
"""

import ast
import logging
import os
from collections.abc import Generator
from pathlib import Path

import libcst as cst
from oops.core.config import config
from oops.core.exceptions import NoManifestFound
from oops.utils.compat import Optional, Union

# ---------------------------------------------------------------------------
# Path lookup
# ---------------------------------------------------------------------------


def get_manifest_path(addon_dir: str) -> Optional[str]:
    """Return the path to the manifest file inside an addon directory.

    Args:
        addon_dir: Path to the addon directory to search.

    Returns:
        Absolute path to the manifest file, or None if not found.
    """
    for manifest_name in config.manifest_names:
        manifest_path = os.path.join(addon_dir, manifest_name)
        if os.path.isfile(manifest_path):
            return manifest_path


# ---------------------------------------------------------------------------
# Dict parsing
# ---------------------------------------------------------------------------


def parse_manifest(filepath: Path) -> dict:
    """Parse an Odoo manifest file into a Python dict via ast.literal_eval.

    Args:
        filepath: Path to the manifest file (not the addon directory).

    Returns:
        Parsed manifest as a dict, or an empty dict if evaluation fails.
    """
    source = filepath.read_text(encoding="utf-8")

    # Convert the exact dict literal slice to a Python object (safe: literals only).
    manifest = ast.literal_eval(source)
    if not isinstance(manifest, dict):
        logging.error("Parsed manifest is not a dict after literal evaluation.")
        return {}
    return manifest


def load_manifest(addon_dir: Path) -> dict:
    """Load and parse the Odoo manifest found inside an addon directory.

    Args:
        addon_dir: Path to the addon directory containing the manifest file.

    Returns:
        Parsed manifest as a dict, or an empty dict if no manifest is found.
    """
    for manifest_name in config.manifest_names:
        manifest_path = addon_dir / manifest_name
        if manifest_path.is_file():
            return parse_manifest(manifest_path)
    logging.debug(f"No Odoo manifest found in {addon_dir}")
    return {}


# ---------------------------------------------------------------------------
# CST parsing
# ---------------------------------------------------------------------------


def parse_manifest_cst(raw: str) -> cst.CSTNode:
    """Parse a manifest source string into a libcst module node.

    Args:
        raw: Raw Python source text of the manifest file.

    Returns:
        Parsed CST module node suitable for lossless rewriting.
    """
    return cst.parse_module(raw)


def read_manifest(path: str) -> cst.CSTNode:
    """Read and parse the manifest file in an addon directory as a CST node.

    Args:
        path: Path to the addon directory containing the manifest file.

    Returns:
        Parsed CST module node of the manifest file.

    Raises:
        NoManifestFound: If no manifest file exists in the given directory.
    """
    manifest_path = get_manifest_path(path)
    if not manifest_path:
        raise NoManifestFound(f"no Odoo manifest found in {path}")
    with open(manifest_path) as mf:
        return parse_manifest_cst(mf.read())


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def find_addons_extended(
    addons_dir: Union[str, Path], installable_only: bool = False, names: Optional[list] = None
) -> "Generator[tuple[str, Path, dict]]":
    """Yield (name, path, manifest) for each addon found in a directory.

    Args:
        addons_dir: Directory to scan for addon subdirectories.
        installable_only: If True, skip addons where installable is False. Defaults to False.
        names: If provided, only yield addons whose name is in this list.

    Yields:
        Tuple of (addon_name, addon_path, manifest_dict) for each matching addon.
    """

    if isinstance(addons_dir, str):
        addons_dir = Path(addons_dir)

    for name in os.listdir(addons_dir):
        path = addons_dir / Path(name)
        if not path.is_dir():
            continue
        manifest = load_manifest(path)
        if not manifest:
            continue
        if installable_only and not manifest.get("installable", True):
            continue

        if names and name not in names:
            continue

        yield name, path, manifest


def find_manifests(path: str, names: Optional[list] = None) -> "Generator[Optional[str]]":
    """Yield the path to each manifest file found in a directory.

    Args:
        path: Directory to scan for addon subdirectories.
        names: If provided, only yield manifests for addons in this list.

    Yields:
        Path to each manifest file found.
    """

    for name in os.listdir(path):
        addon_path = os.path.join(path, name)
        try:
            manifest_path = get_manifest_path(addon_path)
        except NoManifestFound:
            continue

        if names and name not in names:
            continue

        yield manifest_path
