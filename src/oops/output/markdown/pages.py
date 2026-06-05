# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: pages.py — src/oops/output/markdown/pages.py

"""Markdown page builders for the documentation site.

Each builder takes the DocModel (from ``ProjectDocPresenter.to_machine``) plus
the slice it renders and returns a Markdown string. Cross-page references are
resolved by ``docmodel.resolve_ref`` upstream; here we only turn the resulting
link/external descriptors into Markdown, relativising paths per source page.
"""

from __future__ import annotations

import posixpath

from oops.core.compat import Any, Dict, List, Optional
from oops.output.docmodel import anchor_for, model_page_path
from oops.output.markdown.cards import descriptor_table
from oops.output.markdown.mermaid import override_map, view_graph
from oops.utils.render import render_markdown_table

# Descriptor key order for the manifest / loc / metrics cards.
_MANIFEST_KEYS = [
    "name",
    "version",
    "author",
    "license",
    "category",
    "summary",
    "application",
    "installable",
    "website",
]
_LOC_KEYS = ["python", "xml", "javascript", "docs", "total", "pct"]


def _rel_link(target: str, from_page: str) -> str:
    """Relativise a site-root-relative ``target`` against the ``from_page``."""
    base = posixpath.dirname(from_page)
    return posixpath.relpath(target, base or ".")


def humanize(name: str) -> str:
    """Turn a technical field name into a human label (``dev_hours`` → ``Dev Hours``)."""
    return name.replace("_", " ").strip().title()


def render_ref(ref: Optional[Dict[str, Any]], from_page: str, label: Optional[str] = None) -> str:
    """Render a resolved reference (from ``resolve_ref``) as Markdown.

    ``link`` → ``[label](relpath#anchor)``; ``external`` → ``label (origin)``
    (origin omitted when unknown). No edge is dropped.
    """
    if not ref:
        return label or ""
    if ref["kind"] == "link":
        text = label or ref["anchor"]
        href = f"{_rel_link(ref['path'], from_page)}#{ref['anchor']}"
        return f"[{text}]({href})"
    name = label or ref.get("name") or ""
    origin = ref.get("origin")
    return f"{name} ({origin})" if origin else name


# ---------------------------------------------------------------------------
# index.md
# ---------------------------------------------------------------------------


def build_index(dm: Dict[str, Any]) -> str:
    meta = dm.get("metadata", {})
    modules = dm.get("modules", [])
    lines: List[str] = ["# Project documentation", ""]

    generated = meta.get("generated_at")
    tool = meta.get("tool_version")
    schema = meta.get("schema_version")
    stamp = " · ".join(
        part
        for part in (
            f"generated {generated}" if generated else "",
            f"tool {tool}" if tool else "",
            f"schema v{schema}" if schema else "",
        )
        if part
    )
    if stamp:
        lines += [f"_{stamp}_", ""]

    # Counts by classification (inventory) — origin folding noted in limitations.
    by_class: Dict[str, int] = {}
    total_missing = 0
    total_loc = 0
    for mod in modules:
        cls = (mod.get("inventory") or {}).get("classification") or "unknown"
        by_class[cls] = by_class.get(cls, 0) + 1
        total_missing += (mod.get("metrics") or {}).get("missing_docs", 0)
        total_loc += (mod.get("loc") or {}).get("total", 0)

    lines += ["## Overview", ""]
    overview_rows = [["Modules", str(len(modules))]]
    overview_rows += [[f"— {cls}", str(n)] for cls, n in sorted(by_class.items())]
    overview_rows += [["Total LOC", str(total_loc)], ["Doc debt (missing docstrings)", str(total_missing)]]
    lines += [render_markdown_table(["Name", "Value"], overview_rows), ""]

    # Module index.
    lines += ["## Modules", ""]
    module_rows = []
    for mod in sorted(modules, key=lambda m: m["module"]):
        name = mod["module"]
        manifest = mod.get("manifest", {})

        module_rows += [
            [
                f"[{name}](modules/{name}.md)",
                manifest.get("name", name),
                manifest.get("version", "--"),
                manifest.get("summary", ""),
            ]
        ]

    lines += [render_markdown_table(["Technical name", "Name", "Version", "Summary"], module_rows), ""]

    # Model index.
    models_by_bare = dm.get("models_by_bare", {})
    if models_by_bare:
        lines += ["## Models", ""]
        bare_model_rows = []

        for bare in sorted(models_by_bare):
            vals = models_by_bare[bare]
            contributions = vals.get("contributions", [])

            bare_model_rows += [
                [
                    f"[{bare}]({model_page_path(bare)})",
                    "",
                    str(len(contributions)),
                    str(sum(len(c.get("fields", [])) for c in contributions)),
                    str(sum(len(c.get("methods", [])) for c in contributions)),
                ]
            ]

        lines += [
            render_markdown_table(["Name", "Description", "Contributions", "Fields", "Methods"], bare_model_rows),
            "",
        ]

    # Audit pages.
    lines += [
        "## Audit",
        "",
        "- [Project economics](audit/index.md)",
        "- [Overrides & inheritance](audit/overrides.md)",
        "- [View extensions](audit/views.md)",
        "",
    ]

    # Warnings + limitations.
    warnings = dm.get("warnings", [])
    limitations = meta.get("limitations", [])
    if warnings:
        lines += ["## Warnings", ""] + [f"- {w}" for w in warnings] + [""]
    if limitations:
        lines += ["## Limitations", ""] + [f"- {lim}" for lim in limitations] + [""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# modules/<name>.md
# ---------------------------------------------------------------------------


def build_module(dm: Dict[str, Any], mod: Dict[str, Any]) -> str:
    name = mod["module"]
    from_page = f"modules/{name}.md"
    in_repo_modules = {m["module"] for m in dm.get("modules", [])}
    lines: List[str] = [f"# {name}", ""]

    manifest = mod.get("manifest") or {}
    manifest_table = descriptor_table("manifest", manifest, _MANIFEST_KEYS)
    if manifest_table:
        lines += ["## Manifest", "", manifest_table, ""]

    # Inventory facts joined from Stage A.
    inv = mod.get("inventory") or {}
    inv_rows = []
    for label, key in (
        ("Classification", "classification"),
        ("Location", "location"),
        ("Submodule", "submodule"),
        ("Branch", "branch"),
        ("Version", "version"),
    ):
        val = inv.get(key)
        if val:
            inv_rows.append([label, str(val)])
    if inv.get("pr"):
        inv_rows.append(["Pull request", "yes"])
    if inv_rows:
        lines += ["## Project facts", "", render_markdown_table(["Name", "Value"], inv_rows), ""]

    loc_table = descriptor_table("loc", mod.get("loc") or {}, _LOC_KEYS)
    if loc_table:
        lines += ["## Lines of code", "", loc_table, ""]

    # Dependencies, linked when in-repo.
    depends = mod.get("depends", [])
    if depends:
        lines += ["## Dependencies", ""]
        for dep in depends:
            if dep in in_repo_modules:
                lines.append(f"- [{dep}](./{dep}.md)")
            else:
                lines.append(f"- `{dep}`")
        lines.append("")

    # README — embed raw; rst fenced with a conversion note.
    readme = mod.get("readme") or {}
    if readme.get("present") and readme.get("content"):
        lines += ["## README", ""]
        if readme.get("format") == "md":
            lines += [readme["content"], ""]
        else:
            fmt = readme.get("format") or "txt"
            lines += [
                f"_Raw {fmt.upper()} (conversion to Markdown deferred):_",
                "",
                f"```{fmt}",
                readme["content"],
                "```",
                "",
            ]

    # Table of contents — model pages this module touches.
    touched = sorted(
        {
            dm["index"][node["model"]]["name"]
            for kind in ("fields", "methods")
            for node in mod.get(kind, [])
            if node.get("model") in dm["index"]
        }
        | {m["model"] for m in mod.get("models", [])}
    )
    if touched:
        lines += ["## Models touched", ""]
        for bare in touched:
            lines.append(f"- [{bare}]({_rel_link(model_page_path(bare), from_page)})")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# models/<bare>.md
# ---------------------------------------------------------------------------


def _field_row(field: Dict[str, Any], module: str, from_page: str) -> List[str]:
    name = field["name"]
    # Explicit anchor so cross-file links (e.g. a field's compute ref) land here.
    anchor = f'<a id="{anchor_for(field["id"])}"></a>' if field.get("id") else ""

    label = field.get("label")
    if label is None and field.get("label_inferred"):
        label = humanize(name)
    label = label or ""

    flags = ",".join(
        flag for flag, key in (("req", "required"), ("ro", "readonly"), ("store", "store")) if field.get(key)
    )

    type_cell = field.get("type") or ""
    comodel_ref = field.get("comodel_ref")
    if comodel_ref:
        type_cell = f"{type_cell} → {render_ref(comodel_ref, from_page)}".strip()

    origin = ""
    ov = field.get("overrides")
    if field.get("origin_status") == "extended" and ov:
        origin = ov.get("origin") or ""

    help_text = (field.get("help") or "").replace("\n", " ").replace("|", "\\|")
    return [f"{anchor}`{name}`", type_cell, label, help_text, flags, module, origin]


def _render_methods(methods: List[Dict[str, Any]], module: str) -> List[str]:
    out: List[str] = []
    for m in sorted(methods, key=lambda x: (x.get("section", ""), x["name"])):
        anchor = anchor_for(m["id"]) if m.get("id") else ""
        sig = m.get("signature") or "()"
        out.append(f'### <a id="{anchor}"></a>`{m["name"]}{sig}` <small>({module})</small>')
        meta_bits = []
        if m.get("section"):
            meta_bits.append(f"section: {m['section']}")
        depends = [d for d in (m.get("decorators") or []) if "depends" in d]
        if depends:
            meta_bits.append("depends: " + ", ".join(depends))
        if meta_bits:
            out.append("")
            out.append("_" + " · ".join(meta_bits) + "_")
        if m.get("docstring"):
            out += ["", m["docstring"]]
        out.append("")
    return out


def build_model(dm: Dict[str, Any], bare: str, entry: Dict[str, Any]) -> str:
    from_page = entry["page"]
    lines: List[str] = [f"# {bare}", ""]

    contributions = entry.get("contributions", [])

    # Provenance — one line per contributing model node.
    lines += ["## Provenance", ""]
    for contrib in contributions:
        node = contrib["model_node"]
        status = node.get("status", "")
        origin = node.get("inherit_origin")
        ancestor = node.get("ancestor_model")
        if status == "new":
            lines.append(f"- **{contrib['module']}** defines `{bare}` (new model)")
        else:
            tail = f" of `{ancestor or bare}`" + (f" ({origin})" if origin else "")
            lines.append(f"- **{contrib['module']}** extends `{bare}`{tail}")
    lines.append("")

    # Fields — aggregated across all contributions; same-named fields coexist.
    field_rows: List[List[str]] = []
    for contrib in contributions:
        for field in contrib["fields"]:
            field_rows.append(_field_row(field, contrib["module"], from_page))
    if field_rows:
        header = ["Field", "Type", "Label", "Help", "Flags", "Module", "Origin"]
        lines += ["## Fields", "", render_markdown_table(header, field_rows), ""]

    # Methods — grouped by contributing module.
    method_lines: List[str] = []
    for contrib in contributions:
        method_lines += _render_methods(contrib["methods"], contrib["module"])
    if method_lines:
        lines += ["## Methods", ""] + method_lines

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# audit/*.md
# ---------------------------------------------------------------------------


def build_audit_overrides(dm: Dict[str, Any]) -> str:
    """Audit: override/inheritance map of local symbols to upstream origins."""
    lines = ["# Audit — overrides & inheritance", ""]
    graph = override_map(dm.get("modules", []))
    if graph:
        lines += [
            "Each local symbol that overrides or inherits an upstream symbol, "
            "linked to its origin (node color = origin).",
            "",
            graph,
            "",
        ]
    else:
        lines += ["_No overrides or inherited symbols found._", ""]
    return "\n".join(lines)


def build_audit_views(dm: Dict[str, Any]) -> str:
    """Audit: ``inherit_id`` chains, child view → parent view → parent module."""
    lines = ["# Audit — view extensions", ""]
    graph = view_graph(dm.get("modules", []))
    if graph:
        lines += ["View inheritance (`inherit_id`) chains.", "", graph, ""]
    else:
        lines += ["_No view extensions found._", ""]
    return "\n".join(lines)


def build_audit_index(dm: Dict[str, Any]) -> str:
    """Audit: per-module dependencies, LOC economics and doc debt."""
    modules = dm.get("modules", [])
    lines = ["# Audit — project economics", ""]

    # Dependencies by classification (origin proxy from the inventory).
    by_class: Dict[str, int] = {}
    for mod in modules:
        cls = (mod.get("inventory") or {}).get("classification") or "unknown"
        by_class[cls] = by_class.get(cls, 0) + 1
    if by_class:
        lines += [
            "## Modules by classification",
            "",
            render_markdown_table(["Classification", "Modules"], [[c, str(n)] for c, n in sorted(by_class.items())]),
            "",
        ]

    # Per-module LOC + doc debt.
    rows: List[List[str]] = []
    for mod in sorted(modules, key=lambda m: m["module"]):
        loc = (mod.get("loc") or {}).get("total", 0)
        missing = (mod.get("metrics") or {}).get("missing_docs", 0)
        deps = len(mod.get("depends", []))
        rows.append([mod["module"], str(deps), str(loc), str(missing)])
    if rows:
        lines += [
            "## Per-module economics",
            "",
            render_markdown_table(["Module", "Depends", "LOC", "Missing docstrings"], rows),
            "",
        ]

    return "\n".join(lines)
