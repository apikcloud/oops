# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: identity.py — oops/kb/identity.py

"""Stable, module-qualified ids and source-path normalization for the IR v2.

Ids are load-bearing in the flat-list IR (spec §7): they let the audit product
build a repo-wide graph by concatenating the 58 per-module files, and let the
reference product regroup flat ``fields[]`` / ``methods[]`` by their ``model``
ref.

Id scheme (spec §7.1):
    - model  → ``"{module}:{model}"``                 e.g. ``project_management:project.project``
    - field  → ``"{module}:{model}#field:{name}"``    e.g. ``...#field:dev_hours``
    - method → ``"{module}:{model}#method:{name}"``    e.g. ``...#method:_compute_dev_hours``
    - view   → its ``xml_id`` (already globally unique; no helper needed)
"""

from __future__ import annotations

from oops.core.compat import Optional


def model_id(module: str, model: str) -> str:
    """Return the module-qualified model id, e.g. ``project_management:project.project``."""
    return f"{module}:{model}"


def field_id(module: str, model: str, name: str) -> str:
    """Return the field id, e.g. ``project_management:project.project#field:dev_hours``."""
    return f"{model_id(module, model)}#field:{name}"


def method_id(module: str, model: str, name: str) -> str:
    """Return the method id, e.g. ``project_management:project.project#method:_compute_dev_hours``."""
    return f"{model_id(module, model)}#method:{name}"


def normalize_source_file(path: Optional[str], module: str) -> Optional[str]:
    """Return a path rooted at the module dir: ``'<module>/<sub>/<file>'``.

    Trims any deeper repo prefix (e.g. ``'org/repo/<module>/...'``) down to
    ``'<module>/...'`` so every ``source_file`` in the IR shares one convention
    (spec §6). Uses the last occurrence of the module segment, so a repo whose
    parent dir happens to share the module name is handled correctly.

    Args:
        path: A repo- or tier-root-relative source path, or ``None``/``""``.
        module: The technical module name forming the desired root segment.

    Returns:
        The module-rooted path, or the input unchanged when it is falsy or does
        not contain the module segment.
    """
    if not path:
        return path
    parts = path.replace("\\", "/").split("/")
    if module in parts:
        # last occurrence of the module segment
        i = len(parts) - 1 - parts[::-1].index(module)
        return "/".join(parts[i:])
    return path
