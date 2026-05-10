# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: analyze.py — oops/commands/addons/analyze.py

"""Print a structured summary of an Odoo module.

Reads the project KB and the module's source to produce a human-
readable (or JSON) overview: manifest header, depends, per-class field
and method breakdown, plus counts of declared data files and assets.

This command is read-only. It rebuilds the project KB if stale (same
semantics as `oops addons refactor`) but performs no source rewriting,
no git operations, and no manifest edits.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.config import config
from oops.core.paths import global_kb_path, project_kb_path
from oops.io.file import parse_odoo_version
from oops.io.installed_modules import read_installed_modules
from oops.io.manifest import load_manifest
from oops.io.python_imports import discover_imported_files
from oops.io.refactor import ClassInfo, analyse_file
from oops.kb import setup_kb_logging
from oops.kb.build import build_project_kb, compute_root_drift, is_project_kb_stale
from oops.kb.scanner import build_module_field_refs
from oops.kb.store import KBReader
from oops.services.git import get_local_repo
from oops.utils.helpers import deep_visit
from oops.utils.render import OopsError, print_rule, print_success, print_warning
from tabulate import tabulate

# ---------------------------------------------------------------------------
# Internal dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ClassSummary:
    class_name: str
    model_name: str | None
    is_new_model: bool
    inherit: list[str]
    fields_total: int
    fields_base: int
    fields_new: int
    fields_inherited: int
    fields_by_type: dict[str, int]
    methods_total: int
    methods_by_section: dict[str, int]
    overrides: int
    missing_docstrings: int


@dataclass
class StructureSummary:
    data: dict[str, dict[str, int]]
    demo: dict[str, dict[str, int]]
    controllers_py: int
    wizard_py: int
    report_py: int
    static_by_ext: dict[str, int]


@dataclass
class ModuleSummary:
    module_name: str
    module_path: Path
    manifest: dict
    classes: list[ClassSummary]
    structure: StructureSummary
    warnings: list[str] = field(default_factory=list)


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
    "--kb",
    "kb_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Use an explicit KB file instead of the project KB.",
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
    kb_path: Path | None,
    refresh: bool,
    output_format: str,
    verbose: bool,
) -> None:
    setup_kb_logging(verbose)
    log = logging.getLogger(__name__)
    json_mode = output_format == "json"

    resolved_paths = [mp.resolve() for mp in module_paths]

    if kb_path is None:
        try:
            _, repo_path = get_local_repo()
        except click.ClickException:
            raise OopsError(
                "Not in a git repository, and --kb was not provided."
            ) from None

        try:
            version = str(parse_odoo_version(repo_path).major_version)
        except (ValueError, OSError):
            raise OopsError(
                f"Could not read Odoo version from {config.project.file_odoo_version}."
            ) from None

        info = read_installed_modules(repo_path)

        if info is not None:
            _gkb = global_kb_path(version)
            _odoo_mods: set[str] = set()
            if _gkb.exists():
                with KBReader(_gkb) as _kb:
                    _odoo_mods = {
                        n for n, d in _kb.get_modules().items()
                        if d["origin"] in {"odoo", "enterprise"}
                    }
            _project_modules = [m for m in info.modules if m not in _odoo_mods]

            missing, extra = compute_root_drift(repo_path, _project_modules)
            if missing:
                _warn(
                    f"Modules in installed_modules.txt with no addon at the "
                    f"repo root: {missing}",
                    json_mode,
                    [],
                )
            if extra:
                _warn(
                    f"Addons at the repo root not in installed_modules.txt "
                    f"(will not be scanned by the project KB): {extra}",
                    json_mode,
                    [],
                )

        stale, reason = is_project_kb_stale(repo_path, version)
        needs_build = refresh or stale

        if needs_build:
            if info is None:
                raise OopsError(
                    f"installed_modules.txt not found at "
                    f"{repo_path / config.project.file_installed_modules}.\n"
                    "Create the file (one module per line) and re-run oops analyze."
                )
            why = "forced via --refresh" if refresh else f"stale: {reason}"
            log.info("Rebuilding project KB (%s)…", why)
            _warn(f"Rebuilding project KB: {why}", json_mode, [])
            try:
                kb_path = build_project_kb(repo_path, version, info.modules)
            except FileNotFoundError as exc:
                raise OopsError(str(exc)) from None
        else:
            kb_path = project_kb_path(repo_path)
            if not kb_path.exists():
                raise OopsError(f"Project KB not found: {kb_path}")

    assert kb_path is not None
    log.info("Using KB: %s", kb_path)

    json_results: list[dict] = []

    with KBReader(kb_path) as kb:
        modules_index = kb.get_modules()

        for module_path in resolved_paths:
            module_name = module_path.name
            module_warnings: list[str] = []

            manifest = load_manifest(module_path)
            if not manifest:
                msg = f"{module_name}: no manifest found — header will show <unknown>"
                _warn(msg, json_mode, module_warnings)

            models_dir = module_path / "models"
            model_py_files = discover_imported_files(models_dir)

            if not model_py_files:
                if models_dir.is_dir():
                    msg = f"{module_name}: models/ has no imported .py files"
                else:
                    msg = f"{module_name}: no models/ directory"
                _warn(msg, json_mode, module_warnings)

            module_local_refs = build_module_field_refs(model_py_files)

            all_classes: list[ClassSummary] = []
            for py_file in model_py_files:
                class_infos = analyse_file(
                    py_file, kb, modules_index, module_name, module_local_refs
                )
                for ci in class_infos:
                    all_classes.append(_summarize_class(ci))

            structure = _build_structure(module_path, manifest)

            summary = ModuleSummary(
                module_name=module_name,
                module_path=module_path,
                manifest=manifest,
                classes=all_classes,
                structure=structure,
                warnings=module_warnings,
            )

            if json_mode:
                json_results.append(_to_json_dict(summary))
            else:
                render_text(summary)

    if json_mode:
        payload = json_results if len(json_results) > 1 else (json_results[0] if json_results else {})
        click.echo(json.dumps(payload, indent=2, default=str))
    else:
        print_success(f"Done — analysed {len(resolved_paths)} module(s).")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _warn(msg: str, json_mode: bool, warnings: list[str]) -> None:
    if json_mode:
        warnings.append(msg)
    else:
        print_warning(msg)


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

    return ClassSummary(
        class_name=ci.class_name,
        model_name=ci.model_name,
        is_new_model=ci.is_new_model,
        inherit=ci.inherit,
        fields_total=len(fields),
        fields_base=fields_base,
        fields_new=fields_new,
        fields_inherited=fields_inherited,
        fields_by_type=fields_by_type,
        methods_total=len(methods),
        methods_by_section=methods_by_section,
        overrides=sum(1 for m in methods if m.is_override),
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


# ---------------------------------------------------------------------------
# Text renderer
# ---------------------------------------------------------------------------


def render_text(summary: ModuleSummary) -> None:
    print_rule(f"oops analyze — {summary.module_name}")
    m = summary.manifest
    name = m.get("name", "<unknown>")
    version = m.get("version", "")
    author = m.get("author", "")
    license_ = m.get("license", "")
    category = m.get("category", "")
    summary_text = m.get("summary", "")
    installable = m.get("installable", True)

    click.echo(f"Name:     {name:<25} Version:  {version}")
    click.echo(f"Author:   {author:<25} License:  {license_}")
    click.echo(f"Category: {category:<25} Installable: {'yes' if installable else 'no'}")
    if summary_text:
        click.echo(f"Summary:  {summary_text}")
    click.echo()

    depends = m.get("depends", [])
    click.echo(f"Depends ({len(depends)}): {', '.join(depends) or '—'}")
    click.echo()

    if summary.classes:
        click.echo("Models")
        for c in summary.classes:
            tag = "NEW    " if c.is_new_model else "INHERIT"
            if c.is_new_model:
                fields_summary = f"{c.fields_total} fields (base)"
            else:
                fields_summary = f"{c.fields_new} new / {c.fields_inherited} inherited"
            label = c.model_name or ", ".join(c.inherit) or "—"
            click.echo(
                f"  {label:<22} {tag}   {fields_summary:<30} {c.methods_total} methods"
            )
        click.echo()
        _render_model_table(summary.classes)
        overrides = sum(c.overrides for c in summary.classes)
        missing = sum(c.missing_docstrings for c in summary.classes)
        click.echo(f"  Overrides: {overrides}   Missing docstrings: {missing}")
        click.echo()

    _render_structure_section("Data files (from manifest)", summary.structure.data)
    if summary.structure.demo:
        _render_structure_section("Demo files (from manifest)", summary.structure.demo)

    other_py = [
        ("controllers/", summary.structure.controllers_py),
        ("wizard/", summary.structure.wizard_py),
        ("report/", summary.structure.report_py),
    ]
    if any(n for _, n in other_py):
        click.echo("Other Python")
        for label, count in other_py:
            if count:
                click.echo(f"  {label:<13} {count} py   ⚬ not analysed")
        click.echo()

    if summary.structure.static_by_ext:
        click.echo("Static")
        for ext, count in sorted(summary.structure.static_by_ext.items()):
            click.echo(f"  static/src/{ext:<5} {count} {ext}   ⚬ not analysed")
        click.echo()


def _render_model_table(classes: list[ClassSummary]) -> None:
    all_sections = sorted({s for c in classes for s in c.methods_by_section})
    headers = ["Model", "New fld", "Inh fld"] + all_sections
    rows = []
    for c in classes:
        label = c.model_name or ", ".join(c.inherit) or c.class_name
        new_fld = c.fields_base if c.is_new_model else c.fields_new
        inh_fld = c.fields_inherited
        row = (
            [label, new_fld or "", inh_fld or ""]
            + [c.methods_by_section.get(sec, "") or "" for sec in all_sections]
        )
        rows.append(row)
    click.echo(tabulate(rows, headers=headers, tablefmt="rounded_grid"))
    click.echo()


def _render_structure_section(
    title: str,
    data: dict[str, dict[str, int]],
) -> None:
    if not data:
        return
    click.echo(title)
    for subdir, ext_counts in sorted(data.items()):
        for ext, count in sorted(ext_counts.items()):
            click.echo(f"  {subdir:<13} {count} {ext}   ⚬ not analysed")
    click.echo()


# ---------------------------------------------------------------------------
# JSON renderer
# ---------------------------------------------------------------------------


def _to_json_dict(summary: ModuleSummary) -> dict:
    not_analysed: list[str] = []
    s = summary.structure
    if s.data:
        not_analysed.append("data")
    if s.demo:
        not_analysed.append("demo")
    if s.controllers_py:
        not_analysed.append("controllers/")
    if s.wizard_py:
        not_analysed.append("wizard/")
    if s.report_py:
        not_analysed.append("report/")
    if s.static_by_ext:
        not_analysed.append("static/")

    return {
        "module": summary.module_name,
        "manifest": {
            "name": summary.manifest.get("name", "<unknown>"),
            "version": summary.manifest.get("version", ""),
            "author": summary.manifest.get("author", ""),
            "license": summary.manifest.get("license", ""),
            "category": summary.manifest.get("category", ""),
            "installable": summary.manifest.get("installable", True),
            "depends": summary.manifest.get("depends", []),
            "summary": summary.manifest.get("summary", ""),
        },
        "models": [
            {
                "class_name": c.class_name,
                "model_name": c.model_name,
                "is_new_model": c.is_new_model,
                "inherit": c.inherit,
                "fields": {
                    "total": c.fields_total,
                    "base": c.fields_base,
                    "new": c.fields_new,
                    "inherited": c.fields_inherited,
                    "by_type": c.fields_by_type,
                },
                "methods": {
                    "total": c.methods_total,
                    "by_section": c.methods_by_section,
                    "overrides": c.overrides,
                    "missing_docstrings": c.missing_docstrings,
                },
            }
            for c in summary.classes
        ],
        "structure": {
            "data": s.data,
            "demo": s.demo,
            "controllers_py": s.controllers_py,
            "wizard_py": s.wizard_py,
            "report_py": s.report_py,
            "static_by_ext": s.static_by_ext,
        },
        "not_analysed": not_analysed,
        "warnings": summary.warnings,
    }
