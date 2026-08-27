# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: project_pipeline.py — oops/services/project_pipeline.py

"""Shared inventory + analysis pipeline for `project serve`, `mcp`, and the dashboard.

Stage A (``build_inventory``) reuses the ``addons list`` data layer to build a
per-module inventory enriched with git-state facts. Stage B (``build_ir``)
analyzes those modules in-process (via ``oops addons analyze``'s
``run_analysis()``) and reshapes the result into the IR v3 payload dict.
"""

from __future__ import annotations

from pathlib import Path

from oops.core.config import config
from oops.core.logger import log
from oops.core.metadata import get_metadata
from oops.output.base import RenderTarget
from oops.services.git import list_submodules
from oops.services.loc import get_addon_loc_cached
from oops_engine.addons import dedup_addons_by_path, enrich_addon_from_subs


def build_inventory(
    repo,
    repo_path: Path,
    show_all: bool,
    names: tuple[str, ...],
) -> dict[str, dict]:
    """Stage A — reuse the ``list`` data layer to build a per-module inventory.

    Returns a mapping ``technical_name -> row`` where each row carries the
    addon's path plus the git-state facts (classification, location,
    submodule/branch/PR, LOC) used to enrich the documentation pages.
    """
    subs = list_submodules(repo)
    active_paths = {path for path, info in subs.items() if info["name"] in names} if names else None

    seen = dedup_addons_by_path(repo_path, shallow=not show_all)

    inventory: dict[str, dict] = {}
    for addon in seen.values():
        if active_paths is not None and addon.rel_path not in active_paths:
            continue

        log.info(f"Inventory of {addon.technical_name}")
        enrich_addon_from_subs(
            addon, subs, author=config.manifest.author, prefix=config.project.prefix, owner=config.github.owner
        )

        loc = get_addon_loc_cached(repo_path, addon.path)

        inventory[addon.technical_name] = {
            "module": addon.technical_name,
            "path": addon.path,
            "location": addon.location,
            "symlink": addon.symlink,
            "submodule": addon.submodule or "",
            "branch": addon.branch or "",
            "pr": addon.pull_request or False,
            "version": addon.version,
            "classification": addon.classification,
            "author": addon.author,
            "loc": {
                "python": loc.python,
                "xml": loc.xml,
                "javascript": loc.javascript,
                "docs": loc.docs,
                "total": loc.total,
            },
        }

    return inventory


def build_ir(repo, repo_path: Path, module_paths: list[Path], refresh: bool) -> dict:
    """Stage B — analyze the given modules in-process, returning the IR dict."""
    from oops.commands.addons.analyze import run_analysis
    from oops.commands.addons.presenters.analyze import AnalyzePresenter

    run = run_analysis(repo, repo_path, module_paths, refresh)
    target = RenderTarget(audience="machine", verbosity="full")
    output = AnalyzePresenter(installed=run.installed, load_order=run.load_order).prepare(
        run.results, target=target, metadata=get_metadata()
    )
    metadata = output.metadata.to_dict() if output.metadata else {}
    return {**output.layout, "metadata": metadata}
