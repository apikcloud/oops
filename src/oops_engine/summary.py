# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: summary.py — oops_engine/summary.py

"""Per-module analysis orchestration: the core of `oops addons analyze`,
extracted so it's callable without the CLI/config/git.

Moved from oops.commands.addons.analyze.run_analysis()'s per-module loop —
see that module for the CLI-side wrapper (KB rebuild-if-stale, total LOC,
per-module loop driving this function, AnalysisRun assembly).
"""

from __future__ import annotations

import json
from pathlib import Path

from oops.core.compat import Optional
from oops.core.models import Result
from oops.io.file import detect_readme
from oops.io.manifest import load_manifest
from oops.io.python_imports import discover_imported_files
from oops.utils.helpers import deep_visit
from oops_engine.domain_profile import compute_domain_profile
from oops_engine.fingerprint import chain_fingerprint, fingerprint_directory
from oops_engine.identity import local_repo_id
from oops_engine.inspect_module import ClassInfo, SymbolInfo, analyse_file
from oops_engine.loc import get_addon_loc_cached
from oops_engine.models import ClassSummary, ModuleSummary, StructureSummary, ViewsSummary
from oops_engine.provenance import normalize_origin
from oops_engine.resolver import InheritanceResolver
from oops_engine.scanner import build_module_field_refs
from oops_engine.store import KBReader, write_cached_analysis


def build_module_summary(  # noqa: C901, PLR0912
    module_path: Path,
    repo_path: Path,
    kb: "KBReader",
    modules_index: dict,
    resolver: "InheritanceResolver",
    fingerprints: "dict[str, str]",
    installed: "Optional[set[str]]",
    total_loc: int,
    domain_weights: dict,
    kb_generated_at: str,
    kb_path: Path,
    *,
    no_cache: bool = False,
) -> "Result[ModuleSummary]":
    """Analyze one module: fingerprint, cache check, AST scan, IR build,
    domain profile, cache write.

    ``fingerprints`` is mutated in place — the caller passes the same dict
    across every module in one analysis run so a dependency's chained
    fingerprint is available before its dependent's is computed (bottom-up
    load order is the caller's responsibility, same as today).
    """
    module_name = module_path.name
    result: "Result[ModuleSummary]" = Result()

    # depends is needed to chain the fingerprint before the cache lookup, so
    # the manifest is loaded up front regardless of cache hit/miss (cheap —
    # ast.literal_eval, not the expensive part).
    manifest = load_manifest(module_path)
    depends = manifest.get("depends", []) if manifest else []
    own_fingerprint = fingerprint_directory(module_path)
    dep_fingerprints = [fingerprints[dep] for dep in depends if dep in fingerprints]
    content_fingerprint = chain_fingerprint(own_fingerprint, dep_fingerprints)
    fingerprints[module_name] = content_fingerprint

    cached = None if no_cache else kb.get_cached_analysis(module_name, content_fingerprint)
    if cached is not None:
        result.data = ModuleSummary.from_dict(cached["summary"])
        for w in cached.get("warnings", []):
            result.add_warning(w)
        for e in cached.get("errors", []):
            result.add_error(e)
        return result

    if not manifest:
        result.add_warning(f"{module_name}: no manifest found — header will show <unknown>")

    models_dir = module_path / "models"
    model_py_files = discover_imported_files(models_dir)

    if not model_py_files:
        if models_dir.is_dir():
            result.add_warning(f"{module_name}: models/ has no imported .py files")
        else:
            result.add_warning(f"{module_name}: no models/ directory")

    module_local_refs = build_module_field_refs(model_py_files)

    all_classes: "list[ClassSummary]" = []
    all_class_infos: "list[ClassInfo]" = []
    method_symbols: "list[dict]" = []
    method_stacks: dict = {}

    def _get_resolved(model: str) -> dict:
        try:
            return resolver.resolve_cached(model, installed_modules=installed)
        except Exception as exc:
            result.add_warning(f"Resolver failed for {model!r}: {exc}")
            return {}

    for py_file in model_py_files:
        rel_file = f"{module_name}/{py_file.relative_to(module_path).as_posix()}"
        class_infos = analyse_file(py_file, kb, modules_index, module_name, module_local_refs)
        for ci in class_infos:
            ci.source_file = rel_file  # IR v2: own-module source path
            all_class_infos.append(ci)
            cs = _summarize_class(ci)
            cs.missing_description = cs.is_new_model and not ci.description
            cs.resolved_description = ci.description
            if not cs.is_new_model and cs.inherit:
                inherited_model = cs.inherit[0]
                cs.ancestor_model = inherited_model
                resolved = _get_resolved(inherited_model)
                mro = resolved.get("mro", [])
                # Find immediate upstream layer (first MRO entry after module_name)
                mro_modules = [r["module"] for r in mro]
                try:
                    idx = mro_modules.index(module_name)
                    upstream = mro[idx + 1] if idx + 1 < len(mro) else None
                except ValueError:
                    upstream = mro[0] if mro else None
                if upstream:
                    cs.ancestor_module = upstream["module"]
                    cs.ancestor_origin = upstream.get("origin", "")
                # Root = original creator: chain[0] (earliest-loaded).
                # mro[-1] is wrong in multi-inherit C3 (last mixin, not base).
                chain = resolved.get("chain", [])
                root = chain[0] if chain else (mro[-1] if mro else None)
                if root:
                    cs.root_module = root["module"]
                    cs.root_origin = root.get("origin", "")
                if not upstream and root:
                    cs.ancestor_module = root["module"]
                    cs.ancestor_origin = root.get("origin", "")
                # Description: prefer upstream, fall back to root
                if not cs.resolved_description:
                    for candidate in (upstream, root):
                        if candidate:
                            desc = kb.get_model_description(inherited_model)
                            if desc:
                                cs.resolved_description = desc
                                cs.description_inherited_from = candidate["module"]
                                break
            all_classes.append(cs)
            model_label = ci.model_name or (ci.inherit[0] if ci.inherit else "")
            resolved_m = _get_resolved(model_label) if model_label else {}
            resolver_methods = resolved_m.get("methods", {})
            method_symbols.extend(
                _enrich_method_sym(s, rel_file, model_label, module_name, resolver_methods)
                for s in ci.symbols
                if s.kind == "method"
            )
            for mname, mdata in resolver_methods.items():
                method_stacks[(model_label, mname)] = mdata.get("stack", [])

    views_summary, xml_analysed = _build_views_summary(module_name, manifest, kb)
    structure = _build_structure(module_path, manifest, xml_analysed)
    loc = get_addon_loc_cached(repo_path, str(module_path))
    loc_pct = round(100.0 * loc.total / total_loc, 1) if total_loc else 0.0

    result.data = ModuleSummary(
        module_name=module_name,
        module_path=module_path,
        manifest=manifest,
        classes=all_classes,
        structure=structure,
        loc=loc,
        loc_pct=loc_pct,
        views_summary=views_summary,
        method_symbols=method_symbols,
        class_infos=all_class_infos,
        readme=detect_readme(module_path),
        method_stacks=method_stacks,
        origin=modules_index.get(module_name, {}).get("origin"),
    )
    result.data.domain_profile = compute_domain_profile(result.data, kb, domain_weights)

    write_cached_analysis(
        kb_path,
        local_repo_id(repo_path),
        module_name,
        content_fingerprint,
        kb_generated_at,
        {
            "summary": result.data.to_cache_dict(),
            "warnings": result.warnings,
            "errors": result.errors,
        },
    )
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _enrich_method_sym(
    s: "SymbolInfo",
    rel_file: str,
    model_label: str,
    module_name: str,
    resolver_methods: dict,
) -> dict:
    """Build method_symbols IR entry, enriching with resolver stack if available."""
    overrides_ref = None
    method_stack = resolver_methods.get(s.name, {}).get("stack", [])
    if method_stack and s.is_override:
        # upstream reference = root of the resolver stack (original definer)
        root = method_stack[0]
        overrides_ref = {
            "module": root["module"],
            "origin": normalize_origin(root.get("origin")),
            "source_file": root.get("source_file"),
            "source_line": root.get("source_line"),
        }
    return {
        "model": model_label,
        "kind": "method",
        "name": s.name,
        "section": s.section,
        "line_start": s.lineno,
        "line_end": s.end_lineno,
        "source_file": rel_file,
        "is_override": s.is_override,
        "has_docstring": s.has_docstring,
        "overrides": overrides_ref,
    }


def _summarize_class(ci: "ClassInfo") -> "ClassSummary":
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

    def _detail(m: "SymbolInfo") -> dict:
        e = m.kb_entry or {}
        return {
            "model": model_label,
            "method": m.name,
            "origin_module": e.get("module", ""),
            "origin": e.get("origin", ""),
            "line_start": e.get("source_line"),
            "line_end": e.get("source_end_line"),
            "source_file": e.get("source_file", ""),
        }

    override_details = [_detail(m) for m in methods if m.is_override]
    inherited_method_details = [_detail(m) for m in methods if m.kb_entry and not m.is_override and not ci.is_new_model]

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
    view_list: list[dict] = []

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

        inherit_id = v.get("inherit_id")
        parent = kb.get_view(inherit_id) if inherit_id else None
        view_list.append(
            {
                "xml_id": v["xml_id"],
                "mode": v["mode"],
                "view_type": v.get("view_type"),
                "name": v.get("name"),
                "model": v.get("model"),
                "origin": v["origin"],
                "inherit_id": inherit_id,
                "fields_count": len(json.loads(v.get("fields_json") or "[]")),
                "buttons_count": len(json.loads(v.get("buttons_json") or "[]")),
                "ancestor_module": parent["module"] if parent else None,
                "ancestor_origin": parent["origin"] if parent else None,
                "source_file": v.get("source_file"),
                "line_start": v.get("source_line"),
                "line_end": v.get("source_end_line"),
            }
        )

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
            view_list=view_list,
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
