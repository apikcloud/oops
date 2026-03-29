# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from __future__ import annotations

import ast
import logging
import os
import re
from pathlib import Path
from typing import Any

from oops.git.core import GitRepository
from oops.utils.helpers import str_to_list


def file_updater(
    filepath: str,
    new_inner_content: str,
    start_tag: str = None,
    end_tag: str = None,
    padding: str = "\n",
) -> bool:
    """Update a file with new content, either replacing the entire file or a section between tags.

    Args:
        filepath: Path to the file to update.
        new_inner_content: New content to insert.
        start_tag: Start tag for targeted replacement (optional).
        end_tag: End tag for targeted replacement (optional).
        padding: Padding to add around the new content (default: newline).

    Returns:
        bool: True if the file was updated, False if no changes have been made.
    """
    path = Path(filepath)
    if not path.exists():
        os.makedirs(path.parent, exist_ok=True)
        open(filepath, "w").close()

    if (start_tag and not end_tag) or (end_tag and not start_tag):
        raise ValueError(f"Targeted update for {filepath} requires BOTH start and end tags.")

    content = path.read_text()

    # Case 1: Full File Replacement (no tags).
    if not start_tag:
        new_file_content = new_inner_content.strip() + "\n"

    # Case 2: Targeted Replacement (replace content between tags).
    else:
        start_esc = re.escape(start_tag)
        end_esc = re.escape(end_tag)
        # Capture optional leading whitespace to preserve indentation
        pattern = rf"([ \t]*{start_esc}).*?([ \t]*{end_esc})"

        match = re.search(pattern, content, flags=re.DOTALL)
        if match:
            replacement = f"\\1{padding}{new_inner_content.strip()}{padding}\\2"
            new_file_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        else:
            return False

    if new_file_content != content:
        path.write_text(new_file_content)
        return True

    return False


def get_content_from_manifest(fields: str) -> dict[str, dict[str, str]] | None:
    """Helper function to extract content from a manifest.
    It returns a dictionary with the manifest path as key and the content as value.
    Only the fields specified in the fields parameter are extracted.

    Args:
        fields: Comma-separated list of fields to extract from the manifest.
        If empty, all fields are extracted.

    Returns:
        dict[str, dict[str, str]]: Dictionary with the manifest path as key and the content as value.
    """
    repo = GitRepository()
    field_list = str_to_list(fields)

    # Only look at directories at the root (including symlinks).
    manifest_paths = []
    for item in repo.path.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            # Check if this folder (or a manifest inside it) exists.
            manifest = item / "__manifest__.py"
            if manifest.exists():
                manifest_paths.append(manifest)

    if not manifest_paths:
        logging.warning("No manifests found.")
        return {}

    manifest_paths.sort()

    # Select the correct extractor function depending on the fields to extract.
    if not field_list:

        def _extractor(_data: dict[str, Any]) -> dict[str, Any]:
            return _data
    else:

        def _extractor(_data: dict[str, Any]) -> dict[str, Any]:
            return {field: _data.get(field) for field in field_list if _data.get(field)}

    # Loop over all manifests and extract the required fields or all depending on the strategy to use.
    content_retrieved = {}
    for m_path in manifest_paths:
        if data := _parse_odoo_manifest(m_path):
            content_retrieved[m_path.parent.name] = _extractor(data)

    return content_retrieved


def _parse_odoo_manifest(path: Path) -> dict[str, Any] | None:
    """Parse the given manifest with AST to extract the data.

    Args:
        path: Path to the manifest.

    Return:
        Evaluation of the manifest content.
    """
    if not path.exists():
        return None

    try:
        tree = ast.parse(path.read_text(encoding="UTF-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                return ast.literal_eval(node)
    except (SyntaxError, ValueError):
        return None
    return None
