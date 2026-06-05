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
from oops.output.docmodel import anchor_for, method_page_path, model_page_path, resolve_ref
from oops.output.markdown.cards import descriptor_table
from oops.output.markdown.mermaid import override_map, pie_chart, view_graph
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


def _truncate(text: str, limit: int = 80) -> str:
    """Collapse newlines and truncate ``text`` to ``limit`` chars with an ellipsis."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def _module_classification_map(dm: Dict[str, Any]) -> Dict[str, str]:
    """Prebuilt module → classification map to avoid O(n) scans per method."""
    return {
        m["module"]: (m.get("inventory") or {}).get("classification", "") or ""
        for m in dm.get("modules", [])
    }


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
    total_missing_desc = 0
    total_loc = 0
    for mod in modules:
        cls = (mod.get("inventory") or {}).get("classification") or "unknown"
        by_class[cls] = by_class.get(cls, 0) + 1
        total_missing += (mod.get("metrics") or {}).get("missing_docs", 0)
        total_missing_desc += (mod.get("metrics") or {}).get("models_missing_description", 0)
        total_loc += (mod.get("loc") or {}).get("total", 0)

    lines += ["## Overview", ""]
    overview_rows = [["Modules", str(len(modules))]]
    overview_rows += [[f"— {cls}", str(n)] for cls, n in sorted(by_class.items())]
    overview_rows += [
        ["Total LOC", str(total_loc)],
        ["Doc debt (missing docstrings)", str(total_missing)],
        ["Models without _description", str(total_missing_desc)],
    ]
    lines += [render_markdown_table(["Name", "Value"], overview_rows), ""]
    lines += [pie_chart("Addons classification", [(k, v) for k, v in sorted(by_class.items())])]

    # Module index.
    lines += ["## Modules", ""]
    module_rows = []
    for mod in sorted(modules, key=lambda m: m["module"]):
        name = mod["module"]
        manifest = mod.get("manifest", {})
        inventory = mod.get("inventory") or {}

        module_rows += [
            [
                f"[{name}](modules/{name}.md)",
                manifest.get("name", name),
                manifest.get("version", "--"),
                manifest.get("summary", ""),
                manifest.get("author", "") or inventory.get("author", ""),
                inventory.get("classification", ""),
            ]
        ]

    lines += [
        render_markdown_table(
            ["Technical name", "Name", "Version", "Summary", "Author", "Classification"], module_rows
        ),
        "",
    ]

    # Methods index.
    total_methods = sum(len(mod.get("methods", [])) for mod in modules)
    if total_methods > 0:
        lines += [f"## [Methods](methods/index.md) ({total_methods} total)", ""]

    # Model index.
    models_by_bare = dm.get("models_by_bare", {})
    if models_by_bare:
        lines += ["## Models", ""]
        bare_model_rows = []

        for bare in sorted(models_by_bare):
            vals = models_by_bare[bare]
            contributions = vals.get("contributions", [])
            desc = vals.get("description") or ""

            bare_model_rows += [
                [
                    f"[{bare}]({model_page_path(bare)})",
                    _truncate(desc) if desc else "",
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

    # Field type: map origin_status to base/addition/inheritance
    origin_status = field.get("origin_status", "")
    field_type = {"base": "base", "new": "addition", "extended": "inheritance"}.get(origin_status, "")

    help_text = (field.get("help") or "").replace("\n", " ").replace("|", "\\|")
    return [f"{anchor}`{name}`", type_cell, label, help_text, flags, module, origin, field_type]


def _method_row(
    method: Dict[str, Any],
    module: str,
    from_page: str,
    cls_map: Dict[str, str],
) -> List[str]:
    method_id = method.get("id", "")
    name = method["name"]
    method_type = _method_type(method)
    section = method.get("section", "")
    origin = _method_origin(method, module, cls_map)
    target = method_page_path(method_id)
    method_link = f"[{name}]({_rel_link(target, from_page)})"
    return [method_link, method_type, section, origin]


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

    # Description — own or inherited; a new model lacking one is flagged.
    description = entry.get("description")
    inherited_from = entry.get("description_inherited_from")
    is_new = any(c["model_node"].get("status") == "new" for c in contributions)
    missing = any(c["model_node"].get("missing_description") for c in contributions)
    if description:
        body = description
        if inherited_from:
            body += f" *(inherited from `{inherited_from}`)*"
        lines += ["## Description", "", body, ""]
    elif is_new and missing:
        lines += ["## Description", "", "_no `_description`_", ""]

    # Origin — single canonical origin (the new model contribution)
    canonical_contrib = next((c for c in contributions if c["model_node"].get("status") == "new"), None)
    if canonical_contrib:
        node = canonical_contrib["model_node"]
        origin_value = node.get("inherit_origin") or ""
        lines += [
            "## Origin",
            "",
            f"Created by **{canonical_contrib['module']}**" + (f" ({origin_value})" if origin_value else ""),
            "",
        ]

    # Extending modules
    extending = [c for c in contributions if c["model_node"].get("status") != "new"]
    if extending:
        ext_modules = [c["module"] for c in extending]
        lines += ["## Extended by", "", ", ".join(f"**{m}**" for m in ext_modules), ""]

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
        header = ["Field", "Type", "Label", "Help", "Flags", "Module", "Origin", "Kind"]
        lines += ["## Fields", "", render_markdown_table(header, field_rows), ""]

    # Methods — summary table with links to detail pages.
    method_rows: List[List[str]] = []
    cls_map = _module_classification_map(dm)
    for contrib in contributions:
        for method in contrib["methods"]:
            method_rows.append(_method_row(method, contrib["module"], from_page, cls_map))
    if method_rows:
        lines += ["## Methods", "", render_markdown_table(["Method", "Type", "Section", "Origin"], method_rows), ""]

    return "\n".join(lines)


def _method_type(method: Dict[str, Any]) -> str:
    if method.get("is_override"):
        return "override"
    if method.get("is_inherited"):
        return "inheritance"
    return "addition"


def _method_origin(method: Dict[str, Any], module: str, cls_map: Dict[str, str]) -> str:
    if method.get("is_override"):
        ov = method.get("overrides") or {}
        return ov.get("origin", "") or ""
    if method.get("is_inherited"):
        ih = method.get("inherited_from") or {}
        return ih.get("origin", "") or ""
    return cls_map.get(module, "") or ""


def build_method(dm: Dict[str, Any], method: Dict[str, Any], module: str) -> str:
    method_id = method.get("id", "")
    from_page = method_page_path(method_id)
    lines: List[str] = [f"# {method['name']}", ""]

    # Metadata section — model cell resolved via index for a proper link.
    lines += ["## Metadata", ""]
    index = dm.get("index", {})
    model_id_val = method.get("model", "")
    model_ref = resolve_ref(model_id_val, index)
    bare_name = (index.get(model_id_val) or {}).get("name") or model_id_val
    model_cell = render_ref(model_ref, from_page, label=bare_name)

    cls_map = _module_classification_map(dm)
    meta_rows = [
        ["Model", model_cell],
        ["Module", module],
        ["Signature", method.get("signature", "()")],
        ["Type", _method_type(method)],
        ["Section", method.get("section", "")],
        ["Origin", _method_origin(method, module, cls_map)],
        ["Length", str((method.get("line_end") or 0) - (method.get("line_start") or 0))],
    ]
    lines += [render_markdown_table(["Name", "Value"], meta_rows), ""]

    # Docstring
    if method.get("docstring"):
        lines += ["## Docstring", "", method["docstring"], ""]

    return "\n".join(lines)


def build_methods_index(dm: Dict[str, Any]) -> str:
    lines: List[str] = ["# Methods", ""]
    from_page = "methods/index.md"

    # Collect (module, method) pairs — module is known in the outer loop, no re-scan needed.
    all_pairs: List[tuple] = []
    for mod in dm.get("modules", []):
        module = mod["module"]
        for method in mod.get("methods", []):
            all_pairs.append((module, method))

    if not all_pairs:
        lines += ["_No methods found._"]
        return "\n".join(lines)

    cls_map = _module_classification_map(dm)
    method_rows = []
    for module, method in sorted(all_pairs, key=lambda p: (p[1].get("section", ""), p[1].get("name", ""))):
        method_id = method.get("id", "")
        target = method_page_path(method_id)
        method_rows.append(
            [
                method.get("section", ""),
                _method_origin(method, module, cls_map),
                module,
                _method_type(method),
                f"[{method['name']}]({_rel_link(target, from_page)})",
            ]
        )

    lines += [render_markdown_table(["Section", "Origin", "Module", "Type", "Method"], method_rows), ""]
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
        missing_desc = (mod.get("metrics") or {}).get("models_missing_description", 0)
        deps = len(mod.get("depends", []))
        rows.append([mod["module"], str(deps), str(loc), str(missing), str(missing_desc)])
    if rows:
        lines += [
            "## Per-module economics",
            "",
            render_markdown_table(["Module", "Depends", "LOC", "Missing docstrings", "Missing descriptions"], rows),
            "",
        ]

    return "\n".join(lines)
