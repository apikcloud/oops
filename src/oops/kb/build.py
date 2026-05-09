# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: build.py — oops/kb/build.py

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from oops.core.paths import CACHE_DIR_NAME, global_kb_path, project_kb_path
from oops.io.installed_modules import installed_modules_path
from oops.kb.scanner import (
    discover_root_addons,
    scan_module,
    tier_root_from_real_path,
)
from oops.kb.store import KBReader, write_project_kb

log = logging.getLogger(__name__)


def build_project_kb(
    repo_path: Path,
    version: str,
    modules: Iterable[str],
    *,
    slug: str | None = None,
    global_kb: Path | None = None,
) -> Path:
    """Build the project KB.

    Args:
        repo_path: Repository root.
        version: Odoo version string, e.g. ``"17.0"``.
        modules: Allowed module names (the user-owned installed list).
        slug: Project slug embedded in KB metadata. Defaults to ``repo_path.name``.
        global_kb: Path to the global KB. Defaults to ``global_kb_path(version)``.

    Returns:
        Path to the freshly written project KB (``<repo>/.oops-cache/kb.db``).

    Raises:
        FileNotFoundError: If the global KB does not exist.
    """
    modules_list = list(modules)
    project = slug or repo_path.name

    if global_kb is None:
        global_kb = global_kb_path(version)
    if not global_kb.exists():
        raise FileNotFoundError(
            f"Global KB not found: {global_kb}\nRun oops misc kb-build-global first."
        )

    cache_dir = repo_path / CACHE_DIR_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = cache_dir / "kb.db"

    allowed_modules: set[str] = set(modules_list)

    # --- Seed from global KB ---
    log.info("Loading global KB: %s", global_kb)
    with KBReader(global_kb) as kb:
        global_meta = kb.get_meta()
        global_sources = kb.get_sources()
        global_modules = kb.get_modules()
        global_symbols = []
        rows = kb._con.execute(
            "SELECT model, name, kind, origin, module, source_file, source_line FROM symbols"
        ).fetchall()
        for r in rows:
            global_symbols.append(dict(r))

    global_scan = {
        "modules": global_modules,
        "symbols": global_symbols,
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

        log.info("Scanning %s tier (%d modules)…", origin, len(tier_modules))
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
            log.warning("Could not determine tier root for %s, skipping.", origin)
            continue

        sources[origin] = str(tier_root)

        tier_result: dict = {"modules": {}, "symbols": []}
        for _, real_module_path in tier_modules:
            manifest = real_module_path / "__manifest__.py"
            if not manifest.exists():
                manifest = real_module_path / "__openerp__.py"
            if not manifest.exists():
                log.debug("No manifest in %s, skipping.", real_module_path)
                continue

            result = scan_module(real_module_path, origin, tier_root)
            tier_result["modules"].update(result["modules"])
            tier_result["symbols"].extend(result["symbols"])
            scanned += 1

        log.info("  → %d modules scanned", scanned)
        project_scan_results.append(tier_result)

    # --- Scope (input list, not actually-scanned set) ---
    scope = sorted(modules_list)

    # --- Write ---
    log.info("Writing project KB → %s", db_path)
    write_project_kb(
        db_path=db_path,
        odoo_version=global_odoo_version,
        project=project,
        scope=scope,
        sources=sources,
        scan_results=[global_scan] + project_scan_results,
    )

    return db_path


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
    """Return (stale, reason).

    Reasons (in priority order):
      - "no project KB at <path>"
      - "project KB has no generated_at metadata"
      - "installed_modules.txt is newer than project KB"
      - "global KB is newer than project KB"
      - "" when fresh.

    The version is required to resolve the global KB path; callers
    already need it for build_project_kb.
    """
    project = project_kb_path(repo_path)
    if not project.exists():
        return True, f"no project KB at {project}"

    with KBReader(project) as kb:
        project_ts = _parse_kb_timestamp(kb.get_meta().get("generated_at"))

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
    tiers = discover_root_addons(repo_path, None)
    at_root: set[str] = set()
    for tier_modules in tiers.values():
        for name, _ in tier_modules:
            at_root.add(name)
    missing = installed - at_root
    extra = at_root - installed
    return sorted(missing), sorted(extra)
