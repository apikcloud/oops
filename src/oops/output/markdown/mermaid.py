# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: mermaid.py — src/oops/output/markdown/mermaid.py

"""Mermaid graph emitters for the audit pages.

Two graphs:

- **override map** — every local symbol that overrides / inherits an upstream
  symbol, linked to its origin, with origin nodes colored by the origin enum
  ({core, enterprise, oca, third_party, custom}). No edge is dropped.
- **view-extension graph** — ``inherit_id`` chains, child view → parent view →
  the module that owns the parent.

Emitters return a fenced ```mermaid block (or an empty string when there is
nothing to draw).
"""

from __future__ import annotations

from oops.core.compat import Any, Dict, List

# Origin enum → node fill color. oca is currently folded into third_party by the
# scanner (see metadata.limitations); its class stays defined for when it lands.
ORIGIN_COLORS: Dict[str, str] = {
    "core": "#cfe8ff",
    "enterprise": "#e0d4ff",
    "oca": "#d6f5d6",
    "third_party": "#ffe7c2",
    "custom": "#ffd6d6",
}


def _safe(node_id: str) -> str:
    """Mermaid-safe node id (alphanumeric + underscore)."""
    return "".join(c if c.isalnum() else "_" for c in node_id)


def _classdefs() -> List[str]:
    return [f"classDef {origin} fill:{color},stroke:#888;" for origin, color in ORIGIN_COLORS.items()]


def _fence(body: List[str]) -> str:
    return "\n".join(["```mermaid", "graph LR", *body, *_classdefs(), "```"])


def override_map(modules: List[Dict[str, Any]]) -> str:
    """Emit the override/inheritance map: local symbols → their upstream origin."""
    body: List[str] = []
    classed: List[str] = []
    seen_origin: Dict[str, str] = {}  # origin-node id → origin enum
    has_edge = False

    for mod in modules:
        module = mod["module"]
        symbols = [(m, m.get("overrides")) for m in mod.get("methods", []) if m.get("is_override")]
        symbols += [(m, m.get("inherited_from")) for m in mod.get("methods", []) if m.get("is_inherited")]
        symbols += [
            (f, f.get("overrides"))
            for f in mod.get("fields", [])
            if f.get("origin_status") == "extended" and f.get("overrides")
        ]

        for sym, ref in symbols:
            if not ref:
                continue
            has_edge = True
            origin = ref.get("origin") or "third_party"
            origin_module = ref.get("origin_module") or "upstream"
            local_id = _safe(f"{module}__{sym['name']}__{id(sym)}")
            origin_node = _safe(f"origin__{origin_module}")
            body.append(f'{local_id}["{module}: {sym["name"]}"] --> {origin_node}["{origin_module} ({origin})"]')
            if origin_node not in seen_origin:
                seen_origin[origin_node] = origin

    if not has_edge:
        return ""

    for origin_node, origin in seen_origin.items():
        if origin in ORIGIN_COLORS:
            classed.append(f"class {origin_node} {origin};")

    return _fence(body + classed)


def view_graph(modules: List[Dict[str, Any]]) -> str:
    """Emit the view-extension graph: child view → parent view → parent module."""
    body: List[str] = []
    has_edge = False

    for mod in modules:
        for v in mod.get("views", []):
            inherit_id = v.get("inherit_id")
            if not inherit_id:
                continue
            has_edge = True
            child = _safe(v["xml_id"]) if v.get("xml_id") else _safe(v["id"])
            parent = _safe(inherit_id)
            ancestor_module = v.get("ancestor_module") or "?"
            origin = v.get("inherit_origin") or ""
            tail = f" ({origin})" if origin else ""
            body.append(f'{child}["{v.get("xml_id") or v["id"]}"] --> {parent}["{inherit_id}"]')
            parent_mod = _safe(f"mod__{ancestor_module}")
            body.append(f'{parent} --> {parent_mod}["{ancestor_module}{tail}"]')

    return _fence(body) if has_edge else ""
