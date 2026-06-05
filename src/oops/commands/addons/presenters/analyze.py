# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: analyze.py — src/oops/commands/addons/presenters/analyze.py

# The presenter receives the typed domain Result from the command,
# transforms it into neutral dicts ready to render, and is the ONLY
# place where the difference of content between formats lives.
#
# Rules:
#   - No imports from `formatters/`.
#   - No imports from Rich or any rendering library.
#   - Receives Result[SomeDataclass], returns Output[Generic].

from __future__ import annotations

from oops.core.compat import TYPE_CHECKING, Optional
from oops.core.models import (
    ClassSummary,
    ModuleSummary,
    Result,
    ResultCollection,
    Stat,
    StatGroup,
    StructureSummary,
    ViewsSummary,
)
from oops.kb.identity import field_id, method_id, model_id, normalize_source_file
from oops.kb.provenance import normalize_origin
from oops.output.base import Presenter
from oops.output.descriptors import label_of
from oops.output.layout import ConclusionBlock, SectionBlock, SummaryLayout, TableBlock, statgroup_to_panel
from oops.services.loc import LocStats
from oops.utils.render import (
    colorize,
)

if TYPE_CHECKING:
    pass
_METHOD_COLUMNS: list[tuple[str, str]] = [
    ("COMPUTE METHODS", "Compute"),
    ("SELECTION METHODS", "Select"),
    ("DEFAULT METHODS", "Default"),
    ("ONCHANGE METHODS", "Onchange"),
    ("CONSTRAINT METHODS", "Constrain"),
    ("CRUD METHODS", "CRUD"),
    ("HELPER METHODS", "Helper"),
    ("ACTION METHODS", "Action"),
    ("BUSINESS METHODS", "Business"),
]
_VIEW_TYPE_COLUMNS: tuple = (
    "form",
    "list",
    "kanban",
    "search",
    "pivot",
    "graph",
    "calendar",
    "gantt",
    "activity",
    "qweb",
    "cohort",
    "map",
)


def _build_views_table(vs: "ViewsSummary") -> Optional[TableBlock]:

    primary_total = sum(vs.primary_by_type.values())
    ext_total = sum(vs.extensions_by_type.values())
    if not primary_total and not ext_total:
        return

    known = set(_VIEW_TYPE_COLUMNS)
    extra = sorted(
        t for t in (set(vs.primary_by_type) | set(vs.extensions_by_type)) if t not in known and t != "unresolved"
    )
    cols = list(_VIEW_TYPE_COLUMNS) + extra

    def _cell(d: "dict[str, int]", key: str) -> str:
        v = d.get(key, 0)
        return str(v) if v else ""

    columns = [("", "dim", "left")] + [(t, "green", "right") for t in cols] + [("total", "green", "right")]
    rows = [
        ["Primary"] + [_cell(vs.primary_by_type, t) for t in cols] + [str(primary_total)],
        ["Inherited"] + [_cell(vs.extensions_by_type, t) for t in cols] + [str(ext_total)],
    ]

    return TableBlock(title="Views", counter=primary_total + ext_total, columns=columns, rows=rows)


def _build_structure_table(s: StructureSummary) -> Optional[TableBlock]:

    rows = []

    for subdir, ext_counts in sorted(s.data.items()):
        for ext, count in sorted(ext_counts.items()):
            if ext == "xml" and any(e.startswith(subdir + "/") and e.endswith(".xml") for e in s.xml_analysed):
                analysed_cell = colorize("✓", "green")
            else:
                analysed_cell = colorize("✗", "red")
            rows.append(["Data", subdir, str(count), ext, analysed_cell])

    for subdir, ext_counts in sorted(s.demo.items()):
        for ext, count in sorted(ext_counts.items()):
            rows.append(["Demo", subdir, str(count), ext, colorize("✗", "red")])

    for label, count in [
        ("wizard/", s.wizard_py),
        ("controllers/", s.controllers_py),
        ("report/", s.report_py),
    ]:
        if count:
            rows.append(["Other py", label, str(count), "py", colorize("✗", "red")])

    for ext, count in sorted(s.static_by_ext.items()):
        rows.append(["Static", f"static/src/{ext}", str(count), ext, colorize("✗", "red")])

    if not rows:
        return

    columns = [
        ("Section", "dim", "left"),
        ("Subdir", "dim", "left"),
        ("Count", "", "right"),
        ("Ext", "dim", "left"),
        ("Analysed", "", "center"),
    ]

    return TableBlock(title="Structure", columns=columns, rows=rows)


def _build_model_table(classes: list[ClassSummary]) -> TableBlock:

    columns = [
        ("Model", "brand.primary", "left"),
        ("Type", "dim", "left"),
        ("Origin", "dim", "left"),
        ("Own", "green", "right"),
        ("Inh", "green", "right"),
    ] + [(label, "green", "right") for _, label in _METHOD_COLUMNS]
    rows = []
    for c in sorted(classes, key=lambda item: item.class_name):
        label = c.model_name or ", ".join(c.inherit) or c.class_name
        origin = "new" if c.is_new_model else "inherit"
        own = str(c.fields_base if c.is_new_model else c.fields_new) if (c.fields_base or c.fields_new) else ""
        inh = str(c.fields_inherited) if c.fields_inherited else ""
        row = [label, c.model_type, origin, own, inh] + [
            str(c.methods_by_section.get(sec, "")) or "" for sec, _ in _METHOD_COLUMNS
        ]
        rows.append(row)

    return TableBlock(title="Models", columns=columns, rows=rows, counter=len(rows))


def _build_overrides_table(overrides: list[dict[str, str]]) -> TableBlock:

    columns = [
        ("Model", "brand.primary", "left"),
        ("Method", "dim", "left"),
        ("Origin", "dim", "left"),
    ]
    rows = [[ov["model"], ov["method"], ov["origin_module"]] for ov in overrides]

    return TableBlock(title="Overrides", columns=columns, rows=rows, counter=len(rows))


def _build_inherited_methods_table(items: list[dict[str, str]]) -> TableBlock:

    columns = [
        ("Model", "brand.primary", "left"),
        ("Method", "dim", "left"),
        ("Origin", "dim", "left"),
    ]
    rows = [[it["model"], it["method"], it["origin_module"]] for it in items]

    return TableBlock(title="Inherited methods", columns=columns, rows=rows, counter=len(rows))


def _build_metrics(summary: "ModuleSummary") -> StatGroup:

    total_methods = sum(c.methods_total for c in summary.classes)
    total_overrides = sum(c.overrides for c in summary.classes)
    total_inherited_methods = sum(c.inherited_methods for c in summary.classes)
    total_missing = sum(c.missing_docstrings for c in summary.classes)
    total_missing_desc = sum(1 for c in summary.classes if c.missing_description)
    data_count = sum(n for ext in summary.structure.data.values() for n in ext.values())
    fields_own_total = sum((c.fields_base if c.is_new_model else c.fields_new) for c in summary.classes)
    fields_inherited_total = sum(c.fields_inherited for c in summary.classes)

    def _m(key: str, value, kind: str = "count") -> Stat:
        # Labels are resolved from the descriptor registry (spec §0a); the
        # literal fallback equals the registry title so text stays identical.
        return Stat(name=key, label=label_of("metrics", key, key), value=value, kind=kind)

    res = StatGroup(
        name="metrics",
        label="Metrics",
        values=[
            _m("models", len(summary.classes)),
            _m("own_fields", fields_own_total),
            _m("inherited_fields", fields_inherited_total),
            _m("methods", total_methods),
            _m("inherited_methods", total_inherited_methods),
            _m("overridden_methods", total_overrides),
            _m("missing_docs", total_missing),
            _m("models_missing_description", total_missing_desc),
            _m("data", data_count),
        ],
    )

    vs = summary.views_summary
    if vs is not None:
        primary_total = sum(vs.primary_by_type.values())
        if primary_total or vs.extensions or vs.actions or vs.menus:
            res.values.append(_m("primary_views", primary_total))
            if vs.extensions:
                ext_str = str(vs.extensions)
                if vs.extensions_upstream:
                    ext_str += f" ({vs.extensions_upstream} upstream)"
                res.values.append(_m("extension_views", ext_str, kind="text"))
            if vs.actions:
                res.values.append(_m("actions", vs.actions))
            if vs.menus:
                res.values.append(_m("menus", vs.menus))
            if vs.unresolved:
                res.values.append(_m("unresolved_views", vs.unresolved))

    return res


def _build_manifest(summary: "ModuleSummary") -> StatGroup:
    m = summary.manifest

    summary_text = m.get("summary", "")

    def _mf(key: str, value, kind: str = "text") -> Stat:
        return Stat(name=key, label=label_of("manifest", key, key), value=value, kind=kind)

    res = StatGroup(
        name="manifest",
        label="Manifest",
        values=[
            _mf("name", m.get("name", "<unknown>")),
            _mf("version", m.get("version", "")),
            _mf("author", m.get("author", "")),
            _mf("license", m.get("license", "")),
            _mf("category", m.get("category", "")),
            _mf("installable", m.get("installable", True), kind="boolean"),
        ],
    )
    if summary_text:
        res.values.append(_mf("summary", summary_text))

    return res


def _build_loc(data: "Optional[LocStats]", pct: float = 0.0) -> StatGroup:

    # Back to default values, aka 0
    if data is None:
        data = LocStats()

    def _l(key: str, value, kind: str = "count") -> Stat:
        return Stat(name=key, label=label_of("loc", key, key), value=value, kind=kind)

    return StatGroup(
        name="loc",
        label="Lines of code",
        values=[
            _l("python", data.python),
            _l("xml", data.xml),
            _l("javascript", data.javascript),
            _l("docs", data.docs),
            _l("total", data.total),
            _l("pct", f"{pct}%", kind="text"),
        ],
    )


def _build_section(result: "Result[ModuleSummary]") -> SectionBlock:
    summary = result.unwrap

    info = []
    tables = []

    m = summary.manifest

    manifest_values = _build_manifest(summary)
    stats_values = _build_metrics(summary)
    panels = [manifest_values, stats_values]

    if summary.loc and summary.loc.total:
        p_loc = _build_loc(summary.loc, summary.loc_pct)
        panels.append(p_loc)

    depends = m.get("depends", [])
    info += [f"Depends ({len(depends)}): {', '.join(depends) or '—'}"]

    if summary.classes:
        tables.append(_build_model_table(summary.classes))

        all_overrides = [d for c in summary.classes for d in c.override_details]
        if all_overrides:
            tables.append(_build_overrides_table(all_overrides))
        all_inherited = [d for c in summary.classes for d in c.inherited_method_details]
        if all_inherited:
            tables.append(_build_inherited_methods_table(all_inherited))

    if summary.views_summary is not None:
        vt = _build_views_table(summary.views_summary)
        if vt is not None:
            tables.append(vt)

    st = _build_structure_table(summary.structure)
    if st is not None:
        tables.append(st)

    return SectionBlock(
        title=summary.module_name,
        panels=[statgroup_to_panel(panel) for panel in panels],
        tables=tables,
        info=info,
        warnings=result.warnings,
    )


# ---------------------------------------------------------------------------
# IR v2 machine payload — flat node builders (spec §0b, §2–§5)
# ---------------------------------------------------------------------------

# Internal METHOD_SECTION_* → bare IR section (strip " METHODS"); OTHER fallback.
_SECTION_MAP = {
    "COMPUTE METHODS": "COMPUTE",
    "ONCHANGE METHODS": "ONCHANGE",
    "CONSTRAINT METHODS": "CONSTRAINT",
    "CRUD METHODS": "CRUD",
    "ACTION METHODS": "ACTION",
    "HELPER METHODS": "HELPER",
    "SELECTION METHODS": "SELECTION",
    "DEFAULT METHODS": "DEFAULT",
    "BUSINESS METHODS": "BUSINESS",
}

# Internal field section → IR origin_status.
_FIELD_ORIGIN_STATUS = {
    "BASE FIELDS": "base",
    "NEW FIELDS": "new",
    "INHERITED FIELDS": "extended",
}

_MANIFEST_KEYS = (
    "name",
    "version",
    "author",
    "license",
    "category",
    "summary",
    "application",
    "installable",
    "website",
)


def _canonical_model(ci) -> str:
    """Canonical model name, always populated: ``_name`` else ``_inherit[0]``."""
    return ci.model_name or (ci.inherit[0] if ci.inherit else ci.class_name)


def _override_ref(sym, model: str) -> "Optional[dict]":
    """Descriptive cross-module override reference from the symbol's KB entry."""
    e = sym.kb_entry or {}
    return {
        "origin_module": e.get("module") or None,
        "origin": normalize_origin(e.get("origin")),
        "ancestor_model": model,
        "source_file": normalize_source_file(e.get("source_file"), e.get("module") or ""),
        "line_start": e.get("source_line"),
        "line_end": e.get("source_end_line"),
    }


def _inherited_ref(sym) -> dict:
    """Descriptive inherited-from reference from the symbol's KB entry."""
    e = sym.kb_entry or {}
    return {
        "origin_module": e.get("module") or None,
        "origin": normalize_origin(e.get("origin")),
        "source_file": normalize_source_file(e.get("source_file"), e.get("module") or ""),
    }


def _model_nodes(module: str, pairs: list) -> list:
    out = []
    for cs, ci in pairs:
        model = _canonical_model(ci)
        out.append(
            {
                "id": model_id(module, model),
                "model": model,
                "class_name": ci.class_name,
                "status": "new" if cs.is_new_model else "extension",
                "inherit": ci.inherit,
                "inherit_origin": normalize_origin(cs.ancestor_origin),
                "ancestor_model": cs.ancestor_model,
                "ancestor_module": cs.ancestor_module,
                "description": cs.resolved_description,
                "own_description": ci.description,
                "description_inherited_from": cs.description_inherited_from,
                "missing_description": cs.missing_description,
                "docstring": ci.docstring,
            }
        )
    return out


def _field_nodes(module: str, pairs: list, in_repo_models: set, in_repo_methods: set) -> list:
    out = []
    for cs, ci in pairs:  # noqa: B007 — cs unused here, kept for pair symmetry
        model = _canonical_model(ci)
        mid = model_id(module, model)
        for sym in ci.symbols:
            if sym.kind != "field":
                continue
            fd = sym.field_details or {}
            origin_status = _FIELD_ORIGIN_STATUS.get(sym.section, "new")

            compute = fd.get("compute")
            if compute and (model, compute) in in_repo_methods:
                compute = method_id(module, model, compute)

            comodel = fd.get("comodel")
            if comodel and comodel in in_repo_models:
                comodel = model_id(module, comodel)

            label = fd.get("label")
            out.append(
                {
                    "id": field_id(module, model, sym.name),
                    "name": sym.name,
                    "model": mid,
                    "type": fd.get("type") or sym.field_type,
                    "label": label,
                    "label_inferred": label is None,
                    "help": fd.get("help"),
                    "required": fd.get("required"),
                    "readonly": fd.get("readonly"),
                    "store": fd.get("store"),
                    "comodel": comodel,
                    "inverse_name": fd.get("inverse_name"),
                    "relation": fd.get("relation"),
                    "compute": compute,
                    "related": fd.get("related"),
                    "default": fd.get("default"),
                    "selection": fd.get("selection"),
                    "origin_status": origin_status,
                    "overrides": _override_ref(sym, model) if origin_status == "extended" else None,
                    "dynamic": fd.get("dynamic", False),
                    "source_file": normalize_source_file(ci.source_file, module),
                    "line_start": sym.lineno,
                    "line_end": sym.end_lineno,
                }
            )
    return out


def _method_nodes(module: str, pairs: list) -> list:
    out = []
    for cs, ci in pairs:
        model = _canonical_model(ci)
        mid = model_id(module, model)
        for sym in ci.symbols:
            if sym.kind != "method":
                continue
            is_inherited = bool(sym.kb_entry) and not sym.is_override and not cs.is_new_model
            out.append(
                {
                    "id": method_id(module, model, sym.name),
                    "name": sym.name,
                    "model": mid,
                    "signature": sym.signature,
                    "section": _SECTION_MAP.get(sym.section, "OTHER"),
                    "decorators": sym.decorators,
                    "docstring": sym.docstring,
                    "is_override": sym.is_override,
                    "overrides": _override_ref(sym, model) if sym.is_override else None,
                    "is_inherited": is_inherited,
                    "inherited_from": _inherited_ref(sym) if is_inherited else None,
                    "source_file": normalize_source_file(ci.source_file, module),
                    "line_start": sym.lineno,
                    "line_end": sym.end_lineno,
                }
            )
    return out


def _view_nodes(module: str, vs: "Optional[ViewsSummary]", in_repo_models: set) -> list:
    if vs is None:
        return []
    out = []
    for v in vs.view_list:
        vmodel = v.get("model")
        model_ref = model_id(module, vmodel) if vmodel and vmodel in in_repo_models else vmodel
        out.append(
            {
                "id": v["xml_id"],
                "xml_id": v["xml_id"],
                "model": model_ref,
                "mode": v.get("mode"),
                "view_type": v.get("view_type"),
                "origin": normalize_origin(v.get("origin")),
                "inherit_origin": normalize_origin(v.get("ancestor_origin")),
                "inherit_id": v.get("inherit_id"),
                "name": v.get("name") or v["xml_id"],
                "fields_count": v.get("fields_count", 0),
                "buttons_count": v.get("buttons_count", 0),
                "ancestor_module": v.get("ancestor_module"),
                "source_file": normalize_source_file(v.get("source_file"), module),
                "line_start": v.get("line_start"),
                "line_end": v.get("line_end"),
            }
        )
    return out


def _derived_metrics(summary: "ModuleSummary", models: list, fields: list, methods: list) -> dict:
    s = summary.structure
    data_count = sum(n for ext in s.data.values() for n in ext.values())
    metrics = {
        "models": len(models),
        "own_fields": sum(1 for f in fields if f["origin_status"] in ("base", "new")),
        "inherited_fields": sum(1 for f in fields if f["origin_status"] == "extended"),
        "methods": len(methods),
        "inherited_methods": sum(1 for m in methods if m["is_inherited"]),
        "overridden_methods": sum(1 for m in methods if m["is_override"]),
        "missing_docs": sum(1 for m in methods if m["docstring"] is None),
        "models_missing_description": sum(1 for m in models if m["missing_description"]),
        "data": data_count,
    }
    vs = summary.views_summary
    if vs is not None:
        metrics.update(
            {
                "primary_views": sum(vs.primary_by_type.values()),
                "extension_views": vs.extensions,
                "extension_views_upstream": vs.extensions_upstream,
                "actions": vs.actions,
                "menus": vs.menus,
                "unresolved_views": vs.unresolved,
            }
        )
    return metrics


def _manifest_raw(summary: "ModuleSummary") -> dict:
    m = summary.manifest
    return {k: m[k] for k in _MANIFEST_KEYS if k in m}


def _loc_raw(summary: "ModuleSummary") -> dict:
    loc = summary.loc or LocStats()
    return {
        "python": loc.python,
        "xml": loc.xml,
        "javascript": loc.javascript,
        "docs": loc.docs,
        "total": loc.total,
        "pct": summary.loc_pct,
    }


class AnalyzePresenter(Presenter[ResultCollection[ModuleSummary]]):
    def to_human(self, results: ResultCollection[ModuleSummary]) -> SummaryLayout:
        """Reduced payload for console output."""

        sections = [_build_section(result) for result in results]

        return SummaryLayout(
            title="",
            sections=sections,
            warnings=results.warnings,
            conclusion=ConclusionBlock(results.ok, f"Done — analysed {len(results)} module(s)"),
        )

    def to_machine(self, results: ResultCollection[ModuleSummary]) -> dict:
        """Full IR v2 payload: four flat sibling lists of id-addressable nodes."""

        def _make(result: "Result[ModuleSummary]") -> dict:
            summary = result.unwrap
            module = summary.module_name

            # ClassSummary (ancestor enrichment) paired with raw ClassInfo
            # (enriched symbols/content) — aligned 1:1 by the analyze loop.
            pairs = list(zip(summary.classes, summary.class_infos))
            in_repo_models = {_canonical_model(ci) for _, ci in pairs}
            in_repo_methods = {
                (_canonical_model(ci), sym.name) for _, ci in pairs for sym in ci.symbols if sym.kind == "method"
            }

            models = _model_nodes(module, pairs)
            fields = _field_nodes(module, pairs, in_repo_models, in_repo_methods)
            methods = _method_nodes(module, pairs)
            views = _view_nodes(module, summary.views_summary, in_repo_models)

            s = summary.structure
            not_analysed: list[str] = []
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
                "module": module,
                "manifest": _manifest_raw(summary),
                "readme": summary.readme or {"present": False, "format": None, "path": None, "content": None},
                "depends": summary.manifest.get("depends", []),
                "models": models,
                "fields": fields,
                "methods": methods,
                "views": views,
                "structure": {
                    "data": s.data,
                    "demo": s.demo,
                    "controllers_py": s.controllers_py,
                    "wizard_py": s.wizard_py,
                    "report_py": s.report_py,
                    "static_by_ext": s.static_by_ext,
                },
                "metrics": _derived_metrics(summary, models, fields, methods),
                "loc": _loc_raw(summary),
                "not_analysed": not_analysed,
                "warnings": result.warnings,
            }

        return {
            "warnings": results.warnings,
            "modules": [_make(r) for r in results],
        }
