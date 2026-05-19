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

JSON output shape (--format json)::

    {
      "warnings": ["pre-loop drift or rebuild messages"],
      "modules": [
        {
          "module": "...",
          "manifest": { ... },
          "models": [ ... ],
          "structure": { ... },
          "loc": {"python": 0, "xml": 0, "javascript": 0, "docs": 0, "total": 0, "pct": 0.0},
          "not_analysed": [ ... ],
          "warnings": ["module-level warnings"]
        }
      ]
    }
"""

from __future__ import annotations

import json
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.config import config
from oops.core.exceptions import OopsError, get_error_console
from oops.core.models import ClassSummary, ModuleSummary, Result, StructureSummary
from oops.core.paths import global_kb_path, project_kb_path
from oops.io.file import find_addons
from oops.io.installed_modules import read_installed_modules
from oops.io.manifest import load_manifest
from oops.io.python_imports import discover_imported_files
from oops.io.refactor import ClassInfo, analyse_file
from oops.kb import setup_kb_logging
from oops.kb.build import build_project_kb, compute_root_drift, is_project_kb_stale
from oops.kb.scanner import build_module_field_refs
from oops.kb.store import KBReader
from oops.services.git import require_repository
from oops.services.loc import get_addon_loc
from oops.services.project import require_project
from oops.utils.helpers import deep_visit
from oops.utils.render import conclude, render_json, render_text, warning_section
from rich.live import Live
from rich.spinner import Spinner

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@command("analyze", help=__doc__)
@click.argument(
    "module_paths",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
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
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format. 'json' is suited for downstream LLM agent consumption.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Enable verbose KB logging.",
)
def main(  # noqa: C901, PLR0912, PLR0915
    module_paths: tuple[Path, ...],
    refresh: bool,
    output_format: str,
    verbose: bool,
) -> None:
    setup_kb_logging(verbose)
    json_mode = output_format == "json"
    outer: Result[None] = Result()
    if not json_mode:
        outer.add_warning("This command is experimental and may change without notice between releases.")

    resolved_paths = [mp.resolve() for mp in module_paths]
    _, repo_path = require_repository()
    odoo_image = require_project(repo_path)

    # using Live for long-time processing
    with Live(Spinner("dots", text="Initialisation..."), refresh_per_second=10, console=get_error_console()) as live:
        version = str(odoo_image.major_version)
        info = read_installed_modules(repo_path)

        if info is not None:
            _gkb = global_kb_path(version)
            _odoo_mods: set[str] = set()
            if _gkb.exists():
                with KBReader(_gkb) as _kb:
                    _odoo_mods = {
                        n
                        for n, d in _kb.get_modules().items()
                        if d["origin"] in {"odoo", "community", "enterprise", "themes"}
                    }
            _project_modules = [m for m in info.modules if m not in _odoo_mods]

            missing, extra = compute_root_drift(repo_path, _project_modules)
            if missing:
                outer.add_warning(
                    f"Modules in installed_modules.txt with no addon at the repo root: {missing}"
                )
            if extra:
                outer.add_warning(
                    f"Addons at the repo root not in installed_modules.txt "
                    f"(will not be scanned by the project KB): {extra}"
                )

        stale, reason = is_project_kb_stale(repo_path, version)
        needs_build = refresh or stale

        kb_path: Path | None = None
        if needs_build:
            live.update(Spinner("dots", text="Rebuild project KB..."))
            if info is None:
                raise OopsError(
                    f"installed_modules.txt not found at "
                    f"{repo_path / config.project.file_installed_modules}.\n"
                    "Create the file (one module per line) and re-run oops analyze."
                )
            why = "forced via --refresh" if refresh else f"stale: {reason}"
            outer.add_warning(f"Rebuilding project KB: {why}")
            try:
                kb_result = build_project_kb(repo_path, version, info.modules)
            except FileNotFoundError as exc:
                raise OopsError(str(exc)) from None
            outer.merge(kb_result)
            kb_path = kb_result.data
        else:
            kb_path = project_kb_path(repo_path)
            if not kb_path.exists():
                raise OopsError(f"Project KB not found: {kb_path}")

        assert kb_path is not None

        if len(resolved_paths) == 1:
            try:
                _, _root = require_repository()
                total_loc = sum(get_addon_loc(a.path).total for a in find_addons(_root, shallow=True))
            except Exception:
                total_loc = get_addon_loc(str(resolved_paths[0])).total
        else:
            total_loc = sum(get_addon_loc(str(mp)).total for mp in resolved_paths)

        module_results: list[Result[ModuleSummary]] = []

        with KBReader(kb_path) as kb:
            modules_index = kb.get_modules()

            for i, module_path in enumerate(resolved_paths, start=1):
                live.update(Spinner("dots", text=f"Analysing {module_path.name} ({i}/{len(resolved_paths)})..."))
                module_name = module_path.name
                module_result: Result[ModuleSummary] = Result()

                manifest = load_manifest(module_path)
                if not manifest:
                    module_result.add_warning(f"{module_name}: no manifest found — header will show <unknown>")

                models_dir = module_path / "models"
                model_py_files = discover_imported_files(models_dir)

                if not model_py_files:
                    if models_dir.is_dir():
                        module_result.add_warning(f"{module_name}: models/ has no imported .py files")
                    else:
                        module_result.add_warning(f"{module_name}: no models/ directory")

                module_local_refs = build_module_field_refs(model_py_files)

                all_classes: list[ClassSummary] = []
                for py_file in model_py_files:
                    class_infos = analyse_file(py_file, kb, modules_index, module_name, module_local_refs)
                    for ci in class_infos:
                        all_classes.append(_summarize_class(ci))

                structure = _build_structure(module_path, manifest)
                loc = get_addon_loc(str(module_path))
                loc_pct = round(100.0 * loc.total / total_loc, 1) if total_loc else 0.0

                module_result.data = ModuleSummary(
                    module_name=module_name,
                    module_path=module_path,
                    manifest=manifest,
                    classes=all_classes,
                    structure=structure,
                    loc=loc,
                    loc_pct=loc_pct,
                )

                module_results.append(module_result)

    if json_mode:
        payload = {
            "warnings": outer.warnings,
            "modules": [render_json(r) for r in module_results],
        }
        click.echo(json.dumps(payload, indent=2, default=str))
    else:
        warning_section(outer.warnings)
        for r in module_results:
            render_text(r)
        all_ok = outer.ok and all(r.ok for r in module_results)
        conclude(all_ok, f"Done — analysed {len(resolved_paths)} module(s)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _summarize_class(ci: ClassInfo) -> ClassSummary:
    fields = [s for s in ci.symbols if s.kind == "field"]
    methods = [s for s in ci.symbols if s.kind == "method"]

    fields_base = sum(1 for f in fields if f.section == "BASE FIELDS")
    fields_new = sum(1 for f in fields if f.section == "NEW FIELDS")
    fields_inherited = sum(1 for f in fields if f.section == "INHERITED FIELDS")

    fields_by_type: dict[str, int] = {}
    for f in fields:
        if f.field_type:
            fields_by_type[f.field_type] = fields_by_type.get(f.field_type, 0) + 1

    methods_by_section: dict[str, int] = {}
    for m in methods:
        methods_by_section[m.section] = methods_by_section.get(m.section, 0) + 1

    model_label = ci.model_name or (ci.inherit[0] if ci.inherit else "")
    override_details = [
        {
            "model": model_label,
            "method": m.name,
            "origin_module": m.kb_entry.get("module", "") if m.kb_entry else "",
        }
        for m in methods
        if m.is_override
    ]

    return ClassSummary(
        class_name=ci.class_name,
        model_name=ci.model_name,
        is_new_model=ci.is_new_model,
        inherit=ci.inherit,
        model_type=ci.model_type,
        fields_total=len(fields),
        fields_base=fields_base,
        fields_new=fields_new,
        fields_inherited=fields_inherited,
        fields_by_type=fields_by_type,
        methods_total=len(methods),
        methods_by_section=methods_by_section,
        overrides=len(override_details),
        override_details=override_details,
        missing_docstrings=sum(1 for m in methods if not m.has_docstring),
    )


def _group_manifest_data(entries: list) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for entry in entries:
        parts = Path(entry).parts
        subdir = parts[0] if len(parts) > 1 else "."
        ext = Path(entry).suffix.lstrip(".")
        result.setdefault(subdir, {})
        result[subdir][ext] = result[subdir].get(ext, 0) + 1
    return result


def _build_structure(module_path: Path, manifest: dict) -> StructureSummary:
    data = _group_manifest_data(manifest.get("data", []))
    demo = _group_manifest_data(manifest.get("demo", []))

    controllers_py = len(discover_imported_files(module_path / "controllers"))
    wizard_py = len(discover_imported_files(module_path / "wizard"))
    report_py = len(discover_imported_files(module_path / "report"))

    static_by_ext: dict[str, int] = {}
    for _, value in deep_visit(manifest.get("assets", {})):
        if isinstance(value, str):
            ext = Path(value).suffix.lstrip(".")
            if ext:
                static_by_ext[ext] = static_by_ext.get(ext, 0) + 1

    return StructureSummary(
        data=data,
        demo=demo,
        controllers_py=controllers_py,
        wizard_py=wizard_py,
        report_py=report_py,
        static_by_ext=static_by_ext,
    )


