# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: pipeline.py — oops_engine/pipeline.py

"""The generic, non-apik-tiered scan pipeline used by ``oops-engine-scan``.

Unlike ``build.build_project_kb()`` (the local CLI's own apik-tiered layout
and global-KB-seeding pipeline), this scans an entire workspace directory as
one flat tier — no submodule/tier concept, no global-KB merge. It is the
right primitive for scanning an arbitrary external repository (a project
checkout or Odoo's own core/enterprise source tree) in a k8s batch job.
"""

from __future__ import annotations

from pathlib import Path

from oops_engine.build import _resolve_module_apps, _resolve_prototype_roles, _resolve_view_types
from oops_engine.compat import Any, Dict, List, Optional
from oops_engine.models import Result
from oops_engine.scanner import scan_tier
from oops_engine.xml_scanner import scan_tier_xml


def _merge(py_scan: Dict[str, Any], xml_scan: Dict[str, Any]) -> Dict[str, Any]:
    """Combine scan_tier's and scan_tier_xml's results into one ScanResult dict."""
    return {
        "modules": py_scan.get("modules", {}),
        "symbols": py_scan.get("symbols", []),
        "field_refs": py_scan.get("field_refs", []),
        "model_origins": py_scan.get("model_origins", []),
        "views": xml_scan.get("views", []),
        "actions": xml_scan.get("actions", []),
        "menus": xml_scan.get("menus", []),
    }


def scan_repository(workspace_path: Path, repo_id: str, origin: Optional[str] = None) -> Result[List[Dict[str, Any]]]:
    """Scan every addon under workspace_path as one flat tier. No submodule/tier concept.

    Args:
        workspace_path: Root of an already-checked-out repository (a project
            or Odoo core/enterprise source tree). Cloning/checkout is the
            caller's responsibility — this function only reads what's there.
        repo_id: Identity under which the scanned rows will be written
            (see ``store.write_kb``); not used for scanning itself.
        origin: Provenance label stamped onto every scanned row. Defaults to
            ``repo_id`` when not given.

    Returns:
        Result wrapping a one-element list containing the merged ScanResult
        dict, ready to pass to ``store.write_kb(..., scan_results=...)``.
    """
    origin = origin or repo_id
    py_result = scan_tier(workspace_path, origin)
    xml_result = scan_tier_xml(workspace_path, origin)
    scan_result = _merge(py_result.data or {}, xml_result.data or {})
    scan_results = [scan_result]

    _resolve_prototype_roles(scan_results)
    _resolve_view_types(scan_results)
    _resolve_module_apps(scan_results)

    return Result(data=scan_results, warnings=py_result.warnings + xml_result.warnings)
