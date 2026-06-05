# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: docmodel.py — src/oops/output/docmodel.py

"""Pure DocModel helpers for ``oops project doc`` (Stage C).

This module holds the *presenter logic* that turns the analyze IR v2 payload
into a render-ready model: an id index, a bare-model grouping that aggregates
all modules contributing to one Odoo model, stable per-node anchors, and a
single reference-resolution rule shared by every page builder.

Everything here is pure (no I/O, no rendering) so it can be unit-tested in
isolation. The Markdown formatter (``output/markdown/``) consumes the dict
returned by :func:`ProjectDocPresenter.to_machine`, which is built from these
helpers.

Id scheme (from ``kb.identity``)::

    model  → "{module}:{model}"
    field  → "{module}:{model}#field:{name}"
    method → "{module}:{model}#method:{name}"
    view   → its xml_id ("{module}.{xml_id}")

Reference resolution rule (spec): a ref whose target id is in the index becomes
a ``{"kind": "link", "path", "anchor"}``; any other target becomes a
``{"kind": "external", "name", "origin"}``. No edge is ever dropped.
"""

from __future__ import annotations

from oops.core.compat import Any, Dict, List, Optional
from oops.utils.helpers import slugify


def model_page_path(bare: str) -> str:
    """Return the site-root-relative path of a bare model's page."""
    return f"models/{bare}.md"


def anchor_for(node_id: str) -> str:
    """Return a stable, unique anchor slug for any node id.

    The full id is slugified so two same-named fields contributed by different
    modules (same ``#field:<name>`` suffix) never collide on the shared model
    page. ``slugify`` maps ``:``, ``#``, ``.`` and ``_`` runs to single hyphens,
    so ``"pm:project.project#field:dev_hours"`` →
    ``"pm-project-project-field-dev-hours"``.
    """
    return slugify(node_id)


def _bare_of_model_node(node: Dict[str, Any]) -> str:
    """The canonical bare model name carried by a model node."""
    return node["model"]


def build_index(modules: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Index every model / field / method / view node by its id.

    Returns a mapping ``id -> {type, module, page, anchor, name}`` where ``page``
    is the site-root-relative page hosting the node and ``anchor`` is its
    in-page anchor. The page/anchor are precomputed so :func:`resolve_ref` is a
    pure lookup.
    """
    index: Dict[str, Dict[str, Any]] = {}

    # Pass 1 — models, so field/method/view nodes can find their owning page.
    model_bare: Dict[str, str] = {}
    for mod in modules:
        module = mod["module"]
        for node in mod.get("models", []):
            bare = _bare_of_model_node(node)
            model_bare[node["id"]] = bare
            index[node["id"]] = {
                "type": "model",
                "module": module,
                "page": model_page_path(bare),
                "anchor": anchor_for(node["id"]),
                "name": bare,
            }

    # Pass 2 — fields and methods hang off their owning model's page.
    for mod in modules:
        module = mod["module"]
        for kind in ("fields", "methods"):
            for node in mod.get(kind, []):
                bare = model_bare.get(node["model"])
                page = model_page_path(bare) if bare else None
                index[node["id"]] = {
                    "type": kind[:-1],  # "field" / "method"
                    "module": module,
                    "page": page,
                    "anchor": anchor_for(node["id"]),
                    "name": node["name"],
                }
        for node in mod.get("views", []):
            index[node["id"]] = {
                "type": "view",
                "module": module,
                "page": "audit/views.md",
                "anchor": anchor_for(node["id"]),
                "name": node.get("name") or node["id"],
            }

    return index


def resolve_ref(
    target: Optional[str],
    index: Dict[str, Dict[str, Any]],
    origin: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve a single id reference to a link or an external label.

    Args:
        target: the referenced id (e.g. a model id, a method id) or a bare name
            for an out-of-repo target. ``None`` returns ``None``.
        index: the id index from :func:`build_index`.
        origin: optional origin tag to carry on external refs (e.g. ``"core"``).

    Returns:
        ``{"kind": "link", "path", "anchor"}`` when the target is in the index,
        otherwise ``{"kind": "external", "name", "origin"}``. Never drops the
        edge.
    """
    if not target:
        return None
    entry = index.get(target)
    if entry is not None and entry.get("page"):
        return {"kind": "link", "path": entry["page"], "anchor": entry["anchor"]}
    return {"kind": "external", "name": target, "origin": origin}


def group_models_by_bare(modules: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Group model nodes by bare model name, aggregating every contributor.

    Returns a mapping ``bare -> {bare, page, contributions[]}`` where each
    contribution is ``{module, model_node, fields[], methods[]}``. Same-named
    fields from two modules coexist as separate entries under separate
    contributions, disambiguated downstream by their module.
    """
    grouped: Dict[str, Dict[str, Any]] = {}

    for mod in modules:
        module = mod["module"]
        fields_by_model: Dict[str, List[dict]] = {}
        methods_by_model: Dict[str, List[dict]] = {}
        for f in mod.get("fields", []):
            fields_by_model.setdefault(f["model"], []).append(f)
        for m in mod.get("methods", []):
            methods_by_model.setdefault(m["model"], []).append(m)

        for node in mod.get("models", []):
            bare = _bare_of_model_node(node)
            entry = grouped.setdefault(
                bare,
                {
                    "bare": bare,
                    "page": model_page_path(bare),
                    "contributions": [],
                    "description": None,
                    "description_inherited_from": None,
                },
            )
            entry["contributions"].append(
                {
                    "module": module,
                    "model_node": node,
                    "fields": fields_by_model.get(node["id"], []),
                    "methods": methods_by_model.get(node["id"], []),
                }
            )

    for entry in grouped.values():
        _set_canonical_description(entry)

    return grouped


def _set_canonical_description(entry: Dict[str, Any]) -> None:
    """Pick the canonical description for a bare-model entry.

    Prefers the ``status == "new"`` contribution's description; otherwise the
    first contribution carrying a non-empty description. Records the
    inherited-from module when the chosen description was resolved upstream.
    """
    contributions = entry["contributions"]
    chosen = next(
        (c for c in contributions if c["model_node"].get("status") == "new" and c["model_node"].get("description")),
        None,
    )
    if chosen is None:
        chosen = next((c for c in contributions if c["model_node"].get("description")), None)
    if chosen is None:
        return
    node = chosen["model_node"]
    entry["description"] = node.get("description")
    entry["description_inherited_from"] = node.get("description_inherited_from")
