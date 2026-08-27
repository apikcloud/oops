# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: analyze.py — oops/commands/addons/analyze.py

"""Print a structured summary of an Odoo module.

EXPERIMENTAL — This command is part of the KB pipeline. Its interface may
change without notice between releases.

Reads the project KB and the module's source to produce a human-
readable (or JSON) overview: manifest header, depends, per-class field
and method breakdown, plus counts of declared data files and assets.

This command is read-only. It rebuilds the project KB if stale (same
semantics as `oops addons refactor`) but performs no source rewriting,
no git operations, and no manifest edits.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.config import AnalyzeConfig, config
from oops.core.exceptions import OopsError
from oops.core.logger import live_progress, log
from oops.core.metadata import get_metadata, update_metadata
from oops.core.models import ResultCollection
from oops.io.file import find_addons
from oops.io.installed_modules import read_installed_modules
from oops.output.formatters import (
    FormatterRegistry,
    JsonFormatter,
    OutputFormatter,
    SpaReportFormatter,
    SummaryConsoleFormatter,
)
from oops.output.sinks import deliver
from oops.services.git import require_repository
from oops.services.kb import discover_project_addons, set_kb_metadata
from oops.services.loc import get_addon_loc_cached
from oops.services.project import require_project
from oops.services.project_pipeline import build_inventory
from oops_engine.build import build_project_kb, compute_root_drift, is_project_kb_stale, odoo_core_repo_id
from oops_engine.identity import local_repo_id
from oops_engine.models import ModuleSummary
from oops_engine.paths import global_kb_path, project_kb_path
from oops_engine.resolver import InheritanceResolver
from oops_engine.store import KBReader
from oops_engine.summary import build_module_summary

from .presenters.analyze import AnalyzePresenter

FORMATTERS: FormatterRegistry = {
    "text": SummaryConsoleFormatter,
    "json": JsonFormatter,
    "html": SpaReportFormatter,
}


@dataclass
class AnalysisRun:
    """Result of run_analysis(): per-module results plus AnalyzePresenter inputs."""

    results: "ResultCollection[ModuleSummary]"
    installed: "set[str] | None"
    load_order: dict


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@command("analyze", help=__doc__)
@click.argument(
    "module_paths",
    nargs=-1,
    required=False,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--all",
    "analyze_all",
    is_flag=True,
    help="Analyze every addon active at the repo root instead of specifying paths.",
)
@click.option(
    "--refresh",
    is_flag=True,
    default=False,
    help="Force a project KB rebuild before analysis.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "html"]),
    default="text",
    show_default=True,
    help="Output format. 'json' is suited for downstream LLM agent consumption.",
)
@click.option(
    "--output-path",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the output to this path instead of stdout (json) or a temp file (html).",
)
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Skip the per-module analysis cache read (a fresh result is still cached afterwards).",
)
@click.option(
    "--installed-only",
    is_flag=True,
    default=False,
    help=(
        "Only scan addons listed in installed_modules.txt for the project KB. "
        "By default, addons present at the repo root but missing from "
        "installed_modules.txt are scanned too."
    ),
)
@click.pass_context
def main(  # noqa: C901, PLR0912, PLR0915
    ctx,
    module_paths: tuple[Path, ...],
    analyze_all: bool,
    refresh: bool,
    output_format: str,
    output_path: Path,
    no_cache: bool,
    installed_only: bool,
) -> None:

    if analyze_all and module_paths:
        raise click.UsageError("Pass either MODULE_PATHS or --all, not both.")
    if not analyze_all and not module_paths:
        raise click.UsageError("Pass MODULE_PATHS or use --all.")

    metadata = get_metadata()

    formatter: OutputFormatter = FORMATTERS[output_format]()
    json_mode = output_format == "json"

    local_repo, repo_path = require_repository()
    if analyze_all:
        # show_all=False: root-level addons only (symlinked/local at the repo
        # root — i.e. actually part of the project). Unlike `addons list
        # --all`, analyzing addons that were never activated at the root
        # (dormant in a submodule) doesn't make sense — analyze reasons about
        # the project's installed set, not the full submodule inventory.
        inventory = build_inventory(local_repo, repo_path, show_all=False, names=())
        resolved_paths = [Path(row["path"]) for row in inventory.values()]
    else:
        resolved_paths = list(module_paths)

    run = run_analysis(local_repo, repo_path, resolved_paths, refresh, no_cache, installed_only)
    results = run.results
    if not json_mode:
        results.add_warning("This command is experimental and may change without notice between releases.")

    # 2. Presenter prepares neutral dicts according to the formatter's audience.
    output = AnalyzePresenter(installed=run.installed, load_order=run.load_order).prepare(
        results, target=formatter.target, metadata=metadata
    )
    deliver(formatter, output, output_format, output_path)


def run_analysis(  # noqa: C901, PLR0912, PLR0915
    repo,
    repo_path: Path,
    module_paths: list[Path],
    refresh: bool,
    no_cache: bool = False,
    installed_only: bool = False,
) -> AnalysisRun:
    """Analyze the given module paths, returning per-module results.

    Shared by the `analyze` CLI command and `project_pipeline.build_ir()`.

    By default, addons present at the repo root but absent from
    installed_modules.txt are still scanned into the project KB. Pass
    ``installed_only=True`` to restrict the KB scan to the installed set only.
    """
    results: ResultCollection[ModuleSummary] = ResultCollection(title="Addons analyze")

    resolved_paths = [mp.resolve() for mp in module_paths]
    odoo_image = require_project(repo_path)

    # 1. Long-running processing — produces a typed Result of domain dataclasses.

    installed: set[str] | None = None
    load_order: dict = {}

    with live_progress("Analysis..."):
        version = str(odoo_image.major_version)
        info = read_installed_modules(repo_path)
        installed = set(info.modules) if info is not None else None

        if info is not None:
            _gkb = global_kb_path(version)
            _odoo_mods: set[str] = set()
            if _gkb.exists():
                with KBReader(_gkb, repo_ids=[odoo_core_repo_id(version)]) as _kb:
                    _odoo_mods = {
                        n
                        for n, d in _kb.get_modules().items()
                        if d["origin"] in {"odoo", "community", "enterprise", "themes"}
                    }
            _project_modules = [m for m in info.modules if m not in _odoo_mods]

            missing, extra = compute_root_drift(repo_path, _project_modules)
            if missing:
                results.add_warning(f"Modules in installed_modules.txt with no addon at the repo root: {missing}")
            if extra:
                if installed_only:
                    results.add_warning(
                        f"Addons at the repo root not in installed_modules.txt "
                        f"(excluded from the project KB scan — --installed-only): {extra}"
                    )
                else:
                    results.add_warning(
                        f"Addons at the repo root not in installed_modules.txt "
                        f"(scanned anyway; pass --installed-only to exclude): {extra}"
                    )

            scan_modules = set(info.modules)
            if extra and not installed_only:
                scan_modules |= set(extra)

        stale, reason = is_project_kb_stale(repo_path, version, config.project.file_installed_modules)
        needs_build = refresh or stale

        kb_path: Path | None = None
        if needs_build:
            log.info("Rebuild project KB...")
            if info is None:
                raise OopsError(
                    f"installed_modules.txt not found at "
                    f"{repo_path / config.project.file_installed_modules}.\n"
                    "Create the file from the command below and re-run oops analyze:\n"
                    "odoo shell --no-http << EOF\n"
                    "res = env['ir.module.module'].search([('state', 'in', ['installed', 'to upgrade', 'to remove'])]).mapped('name')\n"  # noqa: E501
                    "print('\\n'.join(sorted(res)))\n"
                    "EOF"
                )
            why = "forced via --refresh" if refresh else f"stale: {reason}"
            results.add_warning(f"Rebuilding project KB: {why}")
            try:
                addons = discover_project_addons(repo, repo_path, scan_modules)
                kb_result = build_project_kb(repo_path, version, scan_modules, addons)
            except FileNotFoundError as exc:
                raise OopsError(str(exc)) from None
            results.merge(kb_result)
            kb_path = kb_result.data
        else:
            kb_path = project_kb_path(repo_path)
            if not kb_path.exists():
                raise OopsError(f"Project KB not found: {kb_path}")

        assert kb_path is not None

        if len(resolved_paths) == 1:
            try:
                total_loc = sum(
                    get_addon_loc_cached(repo_path, a.path).total for a in find_addons(repo_path, shallow=True)
                )
            except Exception:
                total_loc = get_addon_loc_cached(repo_path, str(resolved_paths[0])).total
        else:
            total_loc = sum(get_addon_loc_cached(repo_path, str(mp)).total for mp in resolved_paths)

        with KBReader(kb_path, repo_ids=[local_repo_id(repo_path), odoo_core_repo_id(version)]) as kb:
            modules_index = kb.get_modules()
            load_order = kb.get_module_load_order()
            resolver = InheritanceResolver(kb)
            kb_generated_at = kb.get_meta().get("generated_at", "")

            # Bottom-up order: a dependency's chained fingerprint must exist
            # before its dependent's is computed. Modules with no recorded
            # load_index (not in the KB's load order) sort last.
            def _load_index(mp: Path) -> float:
                depth_and_index = load_order.get(mp.name)
                idx = depth_and_index[1] if depth_and_index else None
                return idx if idx is not None else float("inf")

            resolved_paths = sorted(resolved_paths, key=_load_index)
            fingerprints: dict[str, str] = {}

            weights = {**AnalyzeConfig().domain_weights, **config.analyze.domain_weights}

            for i, module_path in enumerate(resolved_paths, start=1):
                log.info(f"Analysing {module_path.name} ({i}/{len(resolved_paths)})...")
                module_result = build_module_summary(
                    module_path,
                    repo_path,
                    kb,
                    modules_index,
                    resolver,
                    fingerprints,
                    installed,
                    total_loc,
                    weights,
                    kb_generated_at,
                    kb_path,
                    no_cache=no_cache,
                )
                results.add(module_result)

    set_kb_metadata(repo_path, version)

    # IR v3 contract: stamp the schema version and the recorded limitations.
    update_metadata(
        schema_version=3,
        limitations=[
            "controllers/wizard/report/data not analysed (see each module's not_analysed)",
            "module load order is installed-scoped; model nodes carry start-line only",
        ],
    )

    return AnalysisRun(results=results, installed=installed, load_order=load_order)
