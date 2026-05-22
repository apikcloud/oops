# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: presenters.py — src/oops/output/presenters.py

# The presenter receives the typed domain Result from the command,
# transforms it into neutral dicts ready to render, and is the ONLY
# place where the difference of content between formats lives.
#
# Rules:
#   - No imports from `formatters/`.
#   - No imports from Rich or any rendering library.
#   - Receives Result[SomeDataclass], returns list[dict].

from __future__ import annotations

from oops.core.models import (
    ClassSummary,
    Conclusion,
    MetricsPanel,
    ModuleSummary,
    Result,
    Section,
    StructureSummary,
    SummaryView,
    Table,
    ViewsSummary,
)
from oops.utils.compat import Optional
from oops.utils.render import (
    colorize,
    human_readable,
)

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


def _render_views_table(vs: "ViewsSummary") -> Optional[Table]:

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

    return Table(title="Views", counter=primary_total + ext_total, columns=columns, rows=rows)


def _render_structure_table(s: StructureSummary) -> Optional[Table]:

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

    return Table(title="Structure", columns=columns, rows=rows)


def _render_model_table(classes: list[ClassSummary]) -> Table:

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

    return Table(title="Models", columns=columns, rows=rows, counter=len(rows))


def _render_overrides_table(overrides: list[dict[str, str]]) -> Table:

    columns = [
        ("Model", "brand.primary", "left"),
        ("Method", "dim", "left"),
        ("Origin", "dim", "left"),
    ]
    rows = [[ov["model"], ov["method"], ov["origin_module"]] for ov in overrides]

    return Table(title="Overrides", columns=columns, rows=rows, counter=len(rows))


def _render_inherited_methods_table(items: list[dict[str, str]]) -> Table:

    columns = [
        ("Model", "brand.primary", "left"),
        ("Method", "dim", "left"),
        ("Origin", "dim", "left"),
    ]
    rows = [[it["model"], it["method"], it["origin_module"]] for it in items]

    return Table(title="Inherited", columns=columns, rows=rows, counter=len(rows))


def _make_section(result: "Result[ModuleSummary]") -> Section:
    assert result.data is not None
    summary = result.data

    info = []
    tables = []
    panels = []

    m = summary.manifest
    name = m.get("name", "<unknown>")
    version = m.get("version", "")
    author = m.get("author", "")
    license_ = m.get("license", "")
    category = m.get("category", "")
    summary_text = m.get("summary", "")
    installable = m.get("installable", True)

    manifest_values = [
        ["Name", name],
        ["Version", version],
        ["Author", author],
        ["License", license_],
        ["Category", category],
        ["Installable", "yes" if installable else "no"],
    ]
    if summary_text:
        manifest_values.append(["Summary", human_readable(summary_text, width=40)])

    total_methods = sum(c.methods_total for c in summary.classes)
    total_overrides = sum(c.overrides for c in summary.classes)
    total_inherited_methods = sum(c.inherited_methods for c in summary.classes)
    total_missing = sum(c.missing_docstrings for c in summary.classes)
    data_count = sum(n for ext in summary.structure.data.values() for n in ext.values())
    fields_own_total = sum((c.fields_base if c.is_new_model else c.fields_new) for c in summary.classes)
    fields_inherited_total = sum(c.fields_inherited for c in summary.classes)

    stats_values = [
        ["Models", str(len(summary.classes))],
        ["Fields (own)", str(fields_own_total)],
        ["Fields (inherited)", str(fields_inherited_total)],
        ["Methods", str(total_methods)],
        ["Inherited methods", str(total_inherited_methods)],
        ["Overrides", str(total_overrides)],
        ["Missing docs", str(total_missing)],
        ["Data files", str(data_count)],
    ]

    vs = summary.views_summary
    if vs is not None:
        primary_total = sum(vs.primary_by_type.values())
        if primary_total or vs.extensions or vs.actions or vs.menus:
            stats_values.append(["Views (primary)", str(primary_total)])
            if vs.extensions:
                ext_str = str(vs.extensions)
                if vs.extensions_upstream:
                    ext_str += f" ({vs.extensions_upstream} upstream)"
                stats_values.append(["Views (ext.)", ext_str])
            if vs.actions:
                stats_values.append(["Actions", str(vs.actions)])
            if vs.menus:
                stats_values.append(["Menus", str(vs.menus)])
            if vs.unresolved:
                stats_values.append(["Views unresolved", str(vs.unresolved)])

    panels += [MetricsPanel("Manifest", manifest_values), MetricsPanel("Stats", stats_values)]

    if summary.loc and summary.loc.total:
        lc = summary.loc
        loc_rows = [
            ["Python", str(lc.python)],
            ["XML", str(lc.xml)],
            ["JavaScript", str(lc.javascript)],
            ["Docs", str(lc.docs)],
            ["Total", str(lc.total)],
        ]
        if summary.loc_pct:
            loc_rows.append(["% of total", f"{summary.loc_pct}%"])
        p_loc = MetricsPanel("Lines of code", loc_rows)
        panels.append(p_loc)

    depends = m.get("depends", [])
    info += [f"Depends ({len(depends)}): {', '.join(depends) or '—'}"]

    if summary.classes:
        tables.append(_render_model_table(summary.classes))

        all_overrides = [d for c in summary.classes for d in c.override_details]
        if all_overrides:
            tables.append(_render_overrides_table(all_overrides))
        all_inherited = [d for c in summary.classes for d in c.inherited_method_details]
        if all_inherited:
            tables.append(_render_inherited_methods_table(all_inherited))

    if summary.views_summary is not None:
        tables.append(_render_views_table(summary.views_summary))

    tables.append(_render_structure_table(summary.structure))

    # if result.warnings:
    #     warning_section(result.warnings)

    return Section(title=summary.module_name, panels=panels, tables=tables, info=info, warnings=result.warnings)


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
        }
    return {
        "primary": vs.primary_by_type,
        "extensions": vs.extensions,
        "extensions_by_type": vs.extensions_by_type,
        "extensions_upstream": vs.extensions_upstream,
        "actions": vs.actions,
        "menus": vs.menus,
        "unresolved": vs.unresolved,
    }


def prepare_full(results: "list[Result[ModuleSummary]]", outer: "Result[None]") -> Result[dict]:
    """Full payload for JSON / scripts / downstream agents.

    Includes every field: ids, metadata, timestamps, internal details.
    """

    def _make(result) -> dict:
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

        loc = summary.loc
        loc_block = (
            {
                "python": loc.python,
                "xml": loc.xml,
                "javascript": loc.javascript,
                "docs": loc.docs,
                "total": loc.total,
                "pct": summary.loc_pct,
            }
            if loc is not None
            else {"python": 0, "xml": 0, "javascript": 0, "docs": 0, "total": 0, "pct": 0.0}
        )

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
            "loc": loc_block,
            "views": _views_block(summary.views_summary),
            "not_analysed": not_analysed,
            "warnings": result.warnings,
        }

    return Result(
        {
            "warnings": outer.warnings,
            "modules": [_make(r) for r in results],
        }
    )


def prepare_summary(results: "list[Result[ModuleSummary]]", outer: "Result[None]") -> "Result[SummaryView]":  # noqa: C901
    """Reduced payload for console / HTML.

    Drops internal fields (ids, refs, metadata) and keeps only what is
    relevant to read.
    """

    # warning_section(outer.warnings)

    all_ok = outer.ok and all(r.ok for r in results)
    sections = [_make_section(result) for result in results]

    return Result(
        SummaryView(
            title="",
            sections=sections,
            warnings=outer.warnings,
            conclusion=Conclusion(all_ok, f"Done — analysed {len(results)} module(s)"),
        )
    )


def prepare(results: "list[Result[ModuleSummary]]", outer: "Result[None]", target: str) -> Result:
    """Single entry point — dispatches based on the formatter target."""
    if target == "full":
        return prepare_full(results, outer)
    return prepare_summary(results, outer)
