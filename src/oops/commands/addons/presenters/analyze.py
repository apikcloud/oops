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
from oops.core.metadata import Metadata
from oops.core.models import (
    ClassSummary,
    ModuleSummary,
    Result,
    Stat,
    StatGroup,
    StructureSummary,
    ViewsSummary,
)
from oops.output.layout import ConclusionBlock, Output, SectionBlock, SummaryLayout, TableBlock, statgroup_to_panel
from oops.services.loc import LocStats
from oops.utils.render import (
    colorize,
)

if TYPE_CHECKING:
    from oops.output.base import RenderTarget
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
    data_count = sum(n for ext in summary.structure.data.values() for n in ext.values())
    fields_own_total = sum((c.fields_base if c.is_new_model else c.fields_new) for c in summary.classes)
    fields_inherited_total = sum(c.fields_inherited for c in summary.classes)

    res = StatGroup(
        name="metrics",
        label="Metrics",
        values=[
            Stat(name="models", label="Models", value=len(summary.classes)),
            Stat(name="own_fields", label="Fields (own)", value=fields_own_total),
            Stat(name="inherited_fields", label="Fields (inherited)", value=fields_inherited_total),
            Stat(name="methods", label="Methods", value=total_methods),
            Stat(name="inherited_methods", label="Inherited methods", value=total_inherited_methods),
            Stat(name="overrided_methods", label="Overrides", value=total_overrides),
            Stat(name="missing_docs", label="Missing docs", value=total_missing),
            Stat(name="data", label="Data files", value=data_count),
        ],
    )

    vs = summary.views_summary
    if vs is not None:
        primary_total = sum(vs.primary_by_type.values())
        if primary_total or vs.extensions or vs.actions or vs.menus:
            res.values.append(Stat(name="primary_views", label="Views (primary)", value=primary_total))
            if vs.extensions:
                ext_str = str(vs.extensions)
                if vs.extensions_upstream:
                    ext_str += f" ({vs.extensions_upstream} upstream)"
                res.values.append(Stat(name="extensions_views", label="Views (ext.)", value=ext_str, kind="text"))
            if vs.actions:
                res.values.append(Stat(name="actions", label="Actions", value=vs.actions))
            if vs.menus:
                res.values.append(Stat(name="menus", label="Menus", value=vs.menus))
            if vs.unresolved:
                res.values.append(Stat(name="unresolved_views", label="Views unresolved", value=vs.unresolved))

    return res


def _build_manifest(summary: "ModuleSummary") -> StatGroup:
    m = summary.manifest

    summary_text = m.get("summary", "")

    res = StatGroup(
        name="manifest",
        label="Manifest",
        values=[
            Stat(name="name", label="Name", value=m.get("name", "<unknown>"), kind="text"),
            Stat(name="version", label="Version", value=m.get("version", ""), kind="text"),
            Stat(name="author", label="Author", value=m.get("author", ""), kind="text"),
            Stat(name="license", label="License", value=m.get("license", ""), kind="text"),
            Stat(name="category", label="Category", value=m.get("category", ""), kind="text"),
            Stat(name="installable", label="Installable", value=m.get("installable", True), kind="boolean"),
        ],
    )
    if summary_text:
        res.values.append(Stat(name="summary", label="Summary", value=summary_text, kind="text"))

    return res


def _build_loc(data: "Optional[LocStats]", pct: float = 0.0) -> StatGroup:

    # Back to default values, aka 0
    if data is None:
        data = LocStats()

    return StatGroup(
        name="loc",
        label="Lines of code",
        values=[
            Stat(name="python", label="Python", value=data.python),
            Stat(name="xml", label="XML", value=data.xml),
            Stat(name="javascript", label="JavaScript", value=data.javascript),
            Stat(name="docs", label="Docs", value=data.docs),
            Stat(name="total", label="Total", value=data.total),
            Stat(name="pct", label="% of total", value=f"{pct}%", kind="text"),
        ],
    )


def _build_section(result: "Result[ModuleSummary]") -> SectionBlock:
    assert result.data is not None
    summary = result.data

    info = []
    tables = []

    m = summary.manifest

    manifest_values = _build_manifest(result.data)
    stats_values = _build_metrics(result.data)
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


def _views_block(vs: "Optional[ViewsSummary]") -> dict:
    if vs is None:
        return {
            "primary": {},
            "extensions": 0,
            "extensions_by_type": {},
            "extensions_upstream": 0,
            "actions": 0,
            "menus": 0,
            "unresolved": 0,
            "list": [],
        }
    return {
        "primary": vs.primary_by_type,
        "extensions": vs.extensions,
        "extensions_by_type": vs.extensions_by_type,
        "extensions_upstream": vs.extensions_upstream,
        "actions": vs.actions,
        "menus": vs.menus,
        "unresolved": vs.unresolved,
        "list": vs.view_list,
    }


def prepare_full(results: "list[Result[ModuleSummary]]", outer: "Result[None]", metadata: Metadata) -> Output[dict]:
    """Full payload for JSON / scripts / downstream agents."""

    def _make(result: "Result[ModuleSummary]") -> dict:
        assert result.data is not None
        summary = result.data

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

        # Common stats, shared with summary
        metrics = _build_metrics(result.data)
        loc = _build_loc(summary.loc, summary.loc_pct)
        manifest = _build_manifest(result.data)

        return {
            "module": summary.module_name,
            "metrics": metrics.to_dict(),
            "manifest": manifest.to_dict(),
            "depends": summary.manifest.get("depends", []),
            "models": [
                {
                    "class_name": c.class_name,
                    "model_name": c.model_name,
                    "is_new_model": c.is_new_model,
                    "inherit": c.inherit,
                    "ancestor_model": c.ancestor_model,
                    "ancestor_module": c.ancestor_module,
                    "ancestor_origin": c.ancestor_origin,
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
                        "override_details": c.override_details,
                        "inherited": c.inherited_methods,
                        "inherited_details": c.inherited_method_details,
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
            "loc": loc.to_dict(),
            "views": _views_block(summary.views_summary),
            "not_analysed": not_analysed,
            "warnings": result.warnings,
        }

    return Output(
        {
            "warnings": outer.warnings,
            "modules": [_make(r) for r in results],
            "metadata": metadata.to_dict(),
        }
    )


def prepare_summary(results: "list[Result[ModuleSummary]]", outer: "Result[None]") -> "Output[SummaryLayout]":
    """Reduced payload for console output."""

    all_ok = outer.ok and all(r.ok for r in results)
    sections = [_build_section(result) for result in results]

    return Output(
        SummaryLayout(
            title="",
            sections=sections,
            warnings=outer.warnings,
            conclusion=ConclusionBlock(all_ok, f"Done — analysed {len(results)} module(s)"),
        )
    )


def prepare(
    results: "list[Result[ModuleSummary]]", outer: "Result[None]", target: RenderTarget, metadata: Metadata
) -> Output:
    """Single entry point — dispatches based on the formatter target."""

    if target.audience == "machine":
        return prepare_full(results, outer, metadata)
    return prepare_summary(results, outer)
