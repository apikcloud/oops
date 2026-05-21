# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: build.py — oops/kb/build.py

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from oops.core.logger import log
from oops.core.models import Result
from oops.core.paths import CACHE_DIR_NAME, global_kb_path, project_kb_path
from oops.io.file import find_addons
from oops.io.installed_modules import installed_modules_path
from oops.kb.scanner import (
    discover_root_addons,
    scan_module,
    tier_root_from_real_path,
)
from oops.kb.store import SCHEMA_VERSION, KBReader, write_project_kb
from oops.kb.xml_scanner import scan_module_xml


def _resolve_prototype_roles(scan_results: list[dict]) -> None:
    """In-place: upgrade 'create' → 'prototype' for classes whose _inherit
    contains at least one known concrete (non-abstract) model.

    Two-pass algorithm:
      Pass A — collect all model names whose role is 'create' and model_type != 'abstract'.
      Pass B — for each 'create' entry, if any _inherit target is in that set,
               upgrade its role to 'prototype'.

    Args:
        scan_results: List of ScanResult dicts, mutated in place.
    """
    concrete_models: set[str] = set()
    for result in scan_results:
        for entry in result.get("model_origins", []):
            if entry.get("role") in ("create", "prototype") and entry.get("model_type") != "abstract":
                concrete_models.add(entry["model"])

    for result in scan_results:
        for entry in result.get("model_origins", []):
            if entry.get("role") != "create" or entry.get("model_type") == "abstract":
                continue
            inherit_targets: list[str] = json.loads(entry.get("inherit_json", "[]"))
            if any(t in concrete_models for t in inherit_targets):
                entry["role"] = "prototype"


_VIEW_TYPE_MAX_DEPTH = 10


def _resolve_view_types(scan_results: list[dict]) -> None:
    """In-place: fill `view_type` for extension views (those with view_type=None).

    Recursively follows `inherit_id` chains up to _VIEW_TYPE_MAX_DEPTH. On
    failure (missing parent, cycle, or depth exceeded) sets `view_type` to
    'unresolved' — never leaves it as None.

    Args:
        scan_results: List of ScanResult dicts, mutated in place.
    """
    index: dict[str, dict] = {}
    for result in scan_results:
        for view in result.get("views", []):
            index[view["xml_id"]] = view

    def resolve(view: dict, depth: int = 0, seen: set | None = None) -> str:
        if seen is None:
            seen = set()
        if depth >= _VIEW_TYPE_MAX_DEPTH:
            return "unresolved"
        vt = view.get("view_type")
        if vt is not None:
            return vt
        parent_id = view.get("inherit_id")
        if not parent_id or parent_id in seen:
            return "unresolved"
        parent = index.get(parent_id)
        if parent is None:
            return "unresolved"
        seen.add(parent_id)
        resolved = resolve(parent, depth + 1, seen)
        return resolved if resolved else "unresolved"

    for result in scan_results:
        for view in result.get("views", []):
            if view.get("view_type") is None:
                view["view_type"] = resolve(view)


def build_project_kb(
    repo_path: Path,
    version: str,
    modules: Iterable[str],
    *,
    slug: str | None = None,
    global_kb: Path | None = None,
) -> "Result[Path]":
    """Build the project KB.

    Args:
        repo_path: Repository root.
        version: Odoo version string, e.g. ``"17.0"``.
        modules: Allowed module names (the user-owned installed list).
        slug: Project slug embedded in KB metadata. Defaults to ``repo_path.name``.
        global_kb: Path to the global KB. Defaults to ``global_kb_path(version)``.

    Returns:
        Result[Path] where .data is the path to the freshly written project KB.
        .warnings contains any non-fatal diagnostic messages (e.g. skipped tier
        roots). Hard errors (missing global KB, schema mismatch) still raise
        FileNotFoundError.

    Raises:
        FileNotFoundError: If the global KB does not exist.
    """
    result: "Result[Path]" = Result()
    modules_list = list(modules)
    project = slug or repo_path.name

    if global_kb is None:
        global_kb = global_kb_path(version)
    if not global_kb.exists():
        raise FileNotFoundError(f"Global KB not found: {global_kb}\nRun oops misc build-kb first.")

    # Verify the global KB is on the expected schema before reading from it.
    with KBReader(global_kb) as _gkb:
        _sv = _gkb.get_meta().get("schema_version")
    if _sv != str(SCHEMA_VERSION):
        raise FileNotFoundError(
            f"Global KB at {global_kb} is on schema {_sv!r}, expected {SCHEMA_VERSION!r}. Re-run oops misc build-kb."
        )

    cache_dir = repo_path / CACHE_DIR_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = cache_dir / "kb.db"

    allowed_modules: set[str] = set(modules_list)

    # --- Seed from global KB ---

    log.info(f"Loading global KB: {global_kb}")

    with KBReader(global_kb) as kb:
        global_meta = kb.get_meta()
        global_sources = kb.get_sources()
        global_modules = kb.get_modules()
        global_symbols = [
            dict(r)
            for r in kb._con.execute(
                "SELECT model, name, kind, origin, module, source_file, source_line, field_type, section FROM symbols"
            ).fetchall()
        ]
        global_field_refs = [
            dict(r)
            for r in kb._con.execute(
                "SELECT model, field_name, module, kwarg, target_method FROM field_refs"
            ).fetchall()
        ]
        global_model_origins = [
            dict(r)
            for r in kb._con.execute(
                "SELECT model, module, origin, role, model_type, "
                "inherit_json, inherits_json, source_file, source_line "
                "FROM model_origins"
            ).fetchall()
        ]
        global_views = [
            dict(r)
            for r in kb._con.execute(
                "SELECT xml_id, module, origin, name, model, view_type, inherit_id, "
                "mode, source_file, source_line, fields_json, buttons_json FROM views"
            ).fetchall()
        ]
        global_actions = [
            dict(r)
            for r in kb._con.execute(
                "SELECT xml_id, module, origin, name, model, view_id, domain, source_file, source_line FROM actions"
            ).fetchall()
        ]
        global_menus = [
            dict(r)
            for r in kb._con.execute(
                "SELECT xml_id, module, origin, name, action, parent_id, source_file, source_line FROM menus"
            ).fetchall()
        ]

    global_scan = {
        "modules": global_modules,
        "symbols": global_symbols,
        "field_refs": global_field_refs,
        "model_origins": global_model_origins,
        "views": global_views,
        "actions": global_actions,
        "menus": global_menus,
    }

    global_odoo_version = global_meta.get("odoo_version", version)
    sources: dict[str, str] = dict(global_sources)

    # --- Discover root addons (symlinks + non-symlink dirs at root) ---
    tiers = discover_root_addons(repo_path, allowed_modules)

    # Scan order: apik (owned via apik-addons/), local (owned at root),
    # third-party (selected community modules).
    tier_scan_order = ["apik", "local", "third-party"]
    project_scan_results: list[dict] = []

    for origin in tier_scan_order:
        tier_modules = tiers.get(origin, [])
        if not tier_modules:
            continue

        log.info(f"Scanning {origin} tier ({len(tier_modules)}) modules)…")

        scanned = 0

        if origin == "local":
            tier_root = repo_path
        else:
            tier_root = None
            for _, real_path in tier_modules:
                tier_root = tier_root_from_real_path(origin, real_path)
                if tier_root:
                    break

        if tier_root is None:
            result.add_warning(f"Could not determine tier root for {origin}, skipping.")
            continue

        sources[origin] = str(tier_root)

        tier_result: dict = {
            "modules": {},
            "symbols": [],
            "field_refs": [],
            "model_origins": [],
            "views": [],
            "actions": [],
            "menus": [],
        }
        for _, real_module_path in tier_modules:
            manifest = real_module_path / "__manifest__.py"
            if not manifest.exists():
                manifest = real_module_path / "__openerp__.py"
            if not manifest.exists():
                log.info(f"No manifest in {real_module_path}, skipping.")
                continue

            scan = scan_module(real_module_path, origin, tier_root)
            tier_result["modules"].update(scan["modules"])
            tier_result["symbols"].extend(scan["symbols"])
            tier_result["field_refs"].extend(scan.get("field_refs", []))
            tier_result["model_origins"].extend(scan.get("model_origins", []))

            xml_scan = scan_module_xml(real_module_path, origin, tier_root)
            tier_result["views"].extend(xml_scan.get("views", []))
            tier_result["actions"].extend(xml_scan.get("actions", []))
            tier_result["menus"].extend(xml_scan.get("menus", []))

            scanned += 1

        log.info(f"{scanned} modules scanned")
        project_scan_results.append(tier_result)

    # --- Scope (input list, not actually-scanned set) ---
    scope = sorted(modules_list)

    # --- Resolve prototype roles and view types across all scan results ---
    all_scan_results = [global_scan] + project_scan_results
    _resolve_prototype_roles(all_scan_results)
    _resolve_view_types(all_scan_results)

    # --- Write ---
    log.info(f"Writing project KB → {db_path}")
    write_result = write_project_kb(
        db_path=db_path,
        odoo_version=global_odoo_version,
        project=project,
        scope=scope,
        sources=sources,
        scan_results=all_scan_results,
    )
    result.merge(write_result)
    result.data = db_path
    return result


# ---------------------------------------------------------------------------
# Staleness detection
# ---------------------------------------------------------------------------


def _parse_kb_timestamp(value: str | None) -> datetime | None:
    """Parse an ISO-format ``meta.generated_at`` value.

    Returns None when the value is missing or unparseable; callers treat
    that as "stale" since a missing anchor is indistinguishable from a
    pre-feature KB.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_project_kb_stale(repo_path: Path, version: str) -> tuple[bool, str]:
    """Decide whether the project KB needs to be rebuilt.

    Args:
        repo_path: Repository root.
        version: Odoo version string (used to resolve the global KB path).

    Returns:
        ``(stale, reason)``. ``reason`` is one of (priority order):

        - ``"no project KB at <path>"``
        - ``"project KB schema version <x> differs from current <y> ..."``
        - ``"project KB has no generated_at metadata"``
        - ``"installed_modules.txt is newer than project KB"``
        - ``"global KB is newer than project KB"``
        - ``""`` when fresh.
    """
    project = project_kb_path(repo_path)
    if not project.exists():
        return True, f"no project KB at {project}"

    with KBReader(project) as kb:
        meta = kb.get_meta()
        sv = meta.get("schema_version")
        if sv != str(SCHEMA_VERSION):
            return True, (
                f"project KB schema version {sv!r} differs from current {SCHEMA_VERSION!r} — rebuild required"
            )
        project_ts = _parse_kb_timestamp(meta.get("generated_at"))

    if project_ts is None:
        return True, "project KB has no generated_at metadata"

    modules_file = installed_modules_path(repo_path)
    if modules_file.exists():
        file_mtime = datetime.fromtimestamp(modules_file.stat().st_mtime, tz=timezone.utc)
        if file_mtime > project_ts:
            return True, "installed_modules.txt is newer than project KB"

    global_kb = global_kb_path(version)
    if global_kb.exists():
        with KBReader(global_kb) as kb:
            global_ts = _parse_kb_timestamp(kb.get_meta().get("generated_at"))
        if global_ts and global_ts > project_ts:
            return True, "global KB is newer than project KB"

    return False, ""


def compute_root_drift(
    repo_path: Path,
    installed_modules: Iterable[str],
) -> tuple[list[str], list[str]]:
    """Compare installed_modules against addons present at the repo root.

    TODO: Make it generic and use it for `oops addons compare`

    Args:
        repo_path: Repository root.
        installed_modules: Module names declared in installed_modules.txt.

    Returns:
        Tuple ``(missing_at_root, extra_at_root)`` of sorted module names.
        - ``missing_at_root``: names in ``installed_modules`` but not present
            at the root (no symlink, no local dir).
        - ``extra_at_root``: names present at the root but absent from
            ``installed_modules`` (these will not be scanned by the KB build).
    """
    installed = set(installed_modules)
    at_root = {a.technical_name for a in find_addons(repo_path, shallow=True)}
    missing = installed - at_root
    extra = at_root - installed
    return sorted(missing), sorted(extra)
