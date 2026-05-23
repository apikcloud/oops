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

from pathlib import Path

import click
from oops.commands.base import command
from oops.core.config import config
from oops.core.exceptions import OopsError
from oops.core.logger import live_progress, log
from oops.core.models import ClassSummary, ModuleSummary, Result, StructureSummary, ViewsSummary
from oops.core.paths import global_kb_path, project_kb_path
from oops.io.file import find_addons
from oops.io.installed_modules import read_installed_modules
from oops.io.manifest import load_manifest
from oops.io.python_imports import discover_imported_files
from oops.io.refactor import ClassInfo, analyse_file
from oops.kb.build import build_project_kb, compute_root_drift, is_project_kb_stale
from oops.kb.scanner import build_module_field_refs
from oops.kb.store import KBReader
from oops.output.formatters import AnalysisReportFormatter, JsonFormatter, OutputFormatter, SummaryConsoleFormatter
from oops.output.sinks import write_output
from oops.presenters.analyze import prepare
from oops.services.git import require_repository
from oops.services.loc import get_addon_loc
from oops.services.project import require_project
from oops.utils.helpers import deep_visit

FORMATTERS: dict[str, type[OutputFormatter]] = {
    "text": SummaryConsoleFormatter,
    "json": JsonFormatter,
    "html": AnalysisReportFormatter,
}


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
    type=click.Choice(["text", "json", "html"]),
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
@click.option(
    "--output-path",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the output to this path instead of stdout (json) or a temp file (html).",
)
def main(  # noqa: C901, PLR0912, PLR0915
    module_paths: tuple[Path, ...],
    refresh: bool,
    output_format: str,
    verbose: bool,
    output_path: Path,
) -> None:

    formatter: OutputFormatter = FORMATTERS[output_format]()

    json_mode = output_format == "json"
    outer: Result[None] = Result()
    if not json_mode:
        outer.add_warning("This command is experimental and may change without notice between releases.")

    resolved_paths = [mp.resolve() for mp in module_paths]
    _, repo_path = require_repository()
    odoo_image = require_project(repo_path)

    # 1. Long-running processing — produces a typed Result of domain dataclasses.

    with live_progress("Analysis..."):
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
                outer.add_warning(f"Modules in installed_modules.txt with no addon at the repo root: {missing}")
            if extra:
                outer.add_warning(
                    f"Addons at the repo root not in installed_modules.txt "
                    f"(will not be scanned by the project KB): {extra}"
                )

        stale, reason = is_project_kb_stale(repo_path, version)
        needs_build = refresh or stale

        kb_path: Path | None = None
        if needs_build:
            log.info("Rebuild project KB...")
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
                log.info(f"Analysing {module_path.name} ({i}/{len(resolved_paths)})...")
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

                views_summary, xml_analysed = _build_views_summary(module_name, manifest, kb)
                structure = _build_structure(module_path, manifest, xml_analysed)
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
                    views_summary=views_summary,
                )

                module_results.append(module_result)

    # 2. Presenter prepares neutral dicts according to the formatter's audience.
    output = prepare(module_results, outer, target=formatter.target)

    # 3. Formatter renders. It does not know the domain dataclasses.
    if formatter.target == "human":
        formatter.render(output)
        return

    # 4. Write the output into a file or print on stdout (only for machine target)
    content = formatter.render(output)
    assert content

    path = write_output(content, output_format, output_path)
    if path:
        print(path)


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
    inherited_method_details = [
        {
            "model": model_label,
            "method": m.name,
            "origin_module": m.kb_entry.get("module", "") if m.kb_entry else "",
        }
        for m in methods
        if m.kb_entry and not m.is_override and not ci.is_new_model
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
        inherited_methods=len(inherited_method_details),
        inherited_method_details=inherited_method_details,
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


def _build_views_summary(
    module_name: str,
    manifest: dict,
    kb: "KBReader",
) -> "tuple[ViewsSummary, frozenset[str]]":
    views = kb.get_module_views(module_name)
    actions = kb.get_module_action_count(module_name)
    menus = kb.get_module_menu_count(module_name)

    primary_by_type: dict[str, int] = {}
    extensions = 0
    extensions_by_type: dict[str, int] = {}
    extensions_upstream = 0
    unresolved = 0

    for v in views:
        if v["mode"] == "primary":
            vt = v["view_type"] or "unknown"
            primary_by_type[vt] = primary_by_type.get(vt, 0) + 1
        else:
            extensions += 1
            vt = v["view_type"] or "unknown"
            extensions_by_type[vt] = extensions_by_type.get(vt, 0) + 1
            iid = v.get("inherit_id") or ""
            if iid and not iid.startswith(f"{module_name}."):
                extensions_upstream += 1
        if v.get("view_type") == "unresolved":
            unresolved += 1

    # source_file in KB is tier-root-relative (e.g. "my_module/views/form.xml");
    # manifest entry is module-relative (e.g. "views/form.xml"). Match via endswith.
    # Edge case: a top-level entry like "views.xml" could match a path ending in
    # "/views.xml" from another module — acceptable given Odoo's convention of
    # always placing XML in subdirectories.
    indexed_source_files = {v["source_file"] for v in views}
    data_entries = manifest.get("data", []) or []
    xml_analysed_list: list[str] = []
    for entry in data_entries:
        if not entry.endswith(".xml"):
            continue
        if any(sf.endswith("/" + entry) or sf == entry for sf in indexed_source_files):
            xml_analysed_list.append(entry)

    return (
        ViewsSummary(
            primary_by_type=primary_by_type,
            extensions=extensions,
            extensions_by_type=extensions_by_type,
            extensions_upstream=extensions_upstream,
            actions=actions,
            menus=menus,
            unresolved=unresolved,
        ),
        frozenset(xml_analysed_list),
    )


def _build_structure(
    module_path: Path, manifest: dict, xml_analysed: "frozenset[str] | None" = None
) -> StructureSummary:
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
        xml_analysed=xml_analysed if xml_analysed is not None else frozenset(),
    )
