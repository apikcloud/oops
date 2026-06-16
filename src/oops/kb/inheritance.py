# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: inheritance.py — oops/kb/inheritance.py

"""Phases 2–4 of the Odoo inheritance resolver.

build_class_chain  → ordered class list per _name
compute_mro        → C3 MRO
merge_fields       → attribute-level field merge
"""
from __future__ import annotations

import json
from typing import Any

_MERGE_ATTRS = [
    "string", "required", "readonly", "compute", "related",
    "selection", "default", "help", "store", "comodel",
    "inverse_name", "relation", "depends", "domain",
]


def build_class_chain(
    model_name: str,
    reader: Any,
    load_order: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return class records for model_name ordered by (load_index, import_index).

    Args:
        model_name: Dotted Odoo model name, e.g. ``'res.partner'``.
        reader: KBReader instance.
        load_order: Mapping from ``compute_load_order`` (module → (depth, index)).
            Pass ``{}`` to rely on the DB's stored load_index values.

    Returns:
        List of model_origin dicts ordered earliest-loaded first, with
        ``inherit`` and ``inherits`` fields parsed from JSON.
    """
    records = reader.get_model_origins_with_order(model_name)
    for r in records:
        if load_order:
            r["load_index"] = load_order.get(r["module"], (None, None))[1]
        r["inherit"] = json.loads(r["inherit_json"])
        r["inherits"] = json.loads(r["inherits_json"])
    records.sort(key=lambda r: (
        r["load_index"] if r["load_index"] is not None else 10 ** 9,
        r["import_index"] if r["import_index"] is not None else 10 ** 9,
    ))
    return records


def compute_mro(  # noqa: C901
    chain: list[dict[str, Any]],
    reader: Any = None,
    load_order: dict[str, Any] | None = None,
    _seen: "set[str] | None" = None,
) -> list[dict[str, Any]]:
    """C3 linearization over the class chain.

    For single-inherit chains (the 95%+ case): returns the chain reversed
    (most-derived first). For multi-inherit / prototype edges: full C3 over
    model names, then expands each name to its own chain records.

    Args:
        chain: Output of ``build_class_chain`` (earliest-loaded first).
        reader: KBReader instance; required for prototype/multi-inherit C3.
        load_order: load_order dict; forwarded to recursive calls.
        _seen: model names already on the call stack (cycle guard).

    Returns:
        Class records ordered most-derived first (standard Python MRO order).
    """
    if not chain:
        return []

    multi = any(len(r["inherit"]) > 1 or r.get("role") == "prototype" for r in chain)
    if not multi:
        return list(reversed(chain))

    if reader is None:
        return list(reversed(chain))

    if _seen is None:
        _seen = set()

    model_name: str = chain[0]["model"]
    _seen = _seen | {model_name}

    # Collect unique parent model names that differ from this model
    parent_names: list[str] = []
    for r in chain:
        for parent in r["inherit"]:
            if parent != model_name and parent not in parent_names:
                parent_names.append(parent)

    if not parent_names:
        return list(reversed(chain))

    def _c3_merge(seqs: list[list[str]]) -> list[str]:
        result: list[str] = []
        while True:
            seqs = [s for s in seqs if s]
            if not seqs:
                return result
            for seq in seqs:
                candidate = seq[0]
                if not any(candidate in s[1:] for s in seqs):
                    result.append(candidate)
                    for s in seqs:
                        if s and s[0] == candidate:
                            s.pop(0)
                    break
            else:
                raise ValueError("C3 linearisation failed — inconsistent hierarchy")

    def _name_seq(mro: list[dict[str, Any]]) -> list[str]:
        seen_n: set[str] = set()
        result: list[str] = []
        for r in mro:
            n = r["model"]
            if n not in seen_n:
                seen_n.add(n)
                result.append(n)
        return result

    # Recursively resolve each parent model's MRO (as name sequence)
    parent_name_seqs: list[list[str]] = []
    for parent in parent_names:
        if parent in _seen:
            continue
        p_chain = build_class_chain(parent, reader, load_order or {})
        if p_chain:
            p_mro = compute_mro(p_chain, reader=reader, load_order=load_order, _seen=_seen)
            parent_name_seqs.append(_name_seq(p_mro))

    if not parent_name_seqs:
        return list(reversed(chain))

    direct_heads = [seq[0] for seq in parent_name_seqs if seq]
    c3_inputs = [[model_name]] + parent_name_seqs + [direct_heads]

    try:
        name_order = _c3_merge(c3_inputs)
    except ValueError:
        return list(reversed(chain))

    # Expand model name order → actual records (most-derived-first within each model)
    result: list[dict[str, Any]] = []
    for name in name_order:
        if name == model_name:
            result.extend(reversed(chain))
        else:
            sub_chain = build_class_chain(name, reader, load_order or {})
            result.extend(reversed(sub_chain))

    return result


def _dyn_load_idx(module: str, load_order: dict[str, Any] | None, stored: Any) -> int:
    """Resolve the effective load index for sorting, preferring dynamic load_order."""
    if load_order:
        entry = load_order.get(module)
        return entry[1] if entry is not None else 10 ** 9
    return stored or 0


def merge_methods(
    mro: list[dict[str, Any]],
    reader: Any,
    load_order: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build the full ordered method override stack along MRO.

    Args:
        mro: Output of ``compute_mro`` (most-derived first).
        reader: KBReader instance.

    Returns:
        Mapping of method_name → ``{"stack": [...], "root": {...}}``.
        Each stack entry has keys: module, origin, source_file, source_line,
        section, has_super, reachable, is_override.
        ``reachable`` is True for layers reachable via super() chains from the
        top. ``is_override`` is True for a non-top layer that does NOT call
        super() (replaces upstream).
    """
    if not mro:
        return {}

    # Bulk-fetch all method layers for every model in the MRO in one query
    # instead of O(methods × MRO_depth) individual queries.
    unique_models: list[str] = list(dict.fromkeys(r["model"] for r in mro))
    all_layers = reader.get_method_layers_bulk(unique_models)
    method_names: set[str] = {name for (_, name) in all_layers}

    merged: dict[str, dict[str, Any]] = {}
    for mname in method_names:
        layers: list[Any] = []
        seen_models: set[str] = set()
        for record in mro:
            m = record["model"]
            if m not in seen_models:
                seen_models.add(m)
                layers.extend(all_layers.get((m, mname), []))

        if not layers:
            continue

        # Drop layers from modules not in the installed set.
        if load_order:
            layers = [layer for layer in layers if layer["module"] in load_order]
        if not layers:
            continue

        # Sort most-derived first, using dynamic load_order when available.
        layers.sort(key=lambda r: (
            -_dyn_load_idx(r["module"], load_order, r["load_index"]),
            -(r["import_index"] or 0),
        ))

        # Walk top→down computing reachability and is_override.
        # Layer N is reachable iff every layer 0..N-1 called super().
        # Root (last entry, oldest/original definer) is never is_override.
        n = len(layers)
        stack: list[dict[str, Any]] = []
        reachable = True
        for i, layer in enumerate(layers):
            is_root = (i == n - 1)
            entry = {
                "module":          layer["module"],
                "origin":          layer["origin"],
                "source_file":     layer["source_file"],
                "source_line":     layer["source_line"],
                "source_end_line": layer["source_end_line"],
                "section":         layer["section"],
                "has_super":       bool(layer["has_super"]) if layer["has_super"] is not None else None,
                "reachable":       reachable,
                "is_override":     not is_root and layer["has_super"] is not None and not layer["has_super"],
            }
            stack.append(entry)
            # If this layer does not forward via super(), subsequent layers are unreachable.
            # NULL (unknown) does not break the chain.
            if layer["has_super"] is not None and not layer["has_super"]:
                reachable = False

        # Reverse so root (oldest/original) comes first — bottom-up display order.
        stack.reverse()
        merged[mname] = {"stack": stack, "root": stack[0] if stack else None}

    return merged


def merge_fields(
    mro: list[dict[str, Any]],
    reader: Any,
    inherits_delegation: dict[str, str] | None = None,
    load_order: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Attribute-level field merge along MRO.

    Args:
        mro: Output of ``compute_mro`` (most-derived first).
        reader: KBReader instance.
        inherits_delegation: Ignored for now (future _inherits support).

    Returns:
        Mapping of field_name → ``{"attrs": {...}, "sources": {attr: (module, file, line)}}``.
        ``selection_add`` entries are accumulated in load order (earliest layer first).
    """
    if not mro:
        return {}

    model = mro[0]["model"]

    field_names: set = set()
    for record in mro:
        for sym in reader.get_symbols_by_module_model(record["module"], record["model"]):
            if sym["kind"] == "field":
                field_names.add(sym["name"])

    merged: dict[str, dict[str, Any]] = {}
    for fname in field_names:
        attrs_per_layer = reader.get_field_attrs(model, fname)
        # Most-derived (highest load_index) first, using dynamic load_order when available.
        attrs_per_layer.sort(key=lambda r: (
            -_dyn_load_idx(r["module"], load_order, r["load_index"]),
            -(r["import_index"] or 0),
        ))

        merged_attrs: dict[str, Any] = {}
        sources: dict[str, Any] = {}
        selection_additions: list[Any] = []

        for layer in attrs_per_layer:
            a = layer["attrs"]
            if "selection_add" in a:
                selection_additions = a["selection_add"] + selection_additions
            for attr in _MERGE_ATTRS:
                if attr not in merged_attrs and attr in a and a[attr] is not None:
                    merged_attrs[attr] = a[attr]
                    sources[attr] = (
                        layer["module"],
                        layer["source_file"],
                        layer["source_line"],
                    )

        if selection_additions:
            merged_attrs.setdefault("selection", [])
            merged_attrs["selection"] = selection_additions + merged_attrs.get("selection", [])

        merged[fname] = {"attrs": merged_attrs, "sources": sources}

    return merged
