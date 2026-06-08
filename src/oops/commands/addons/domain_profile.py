# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: domain_profile.py — oops/commands/addons/domain_profile.py

"""Domain profile computation for the analyze command.

Produces a deterministic ``domain_profile`` dict from a ``ModuleSummary`` + KB,
quantifying how much a module touches each Odoo functional domain (Sales,
Accounting, …) and which transversal pillars it touches.

Public entry point:
    compute_domain_profile(summary, kb, weights) -> dict
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from oops.kb.domains import EXCLUDED_TECHNICAL_MODULES, PILLAR_MODULES, domain_label

if TYPE_CHECKING:
    from oops.core.models import ModuleSummary
    from oops.kb.store import KBReader


# ---------------------------------------------------------------------------
# Internal accumulator
# ---------------------------------------------------------------------------


def _empty_indicators() -> Dict[str, Any]:
    return {
        "models_extended": 0,
        "fields_new": 0,
        "fields_override": 0,
        "methods_new": 0,
        "methods_inherited": 0,
        "methods_override": 0,
        "views_primary": 0,
        "views_extended": 0,
        "loc": 0,
    }


# ---------------------------------------------------------------------------
# Model classification
# ---------------------------------------------------------------------------


def _classify_model(model: str, kb: "KBReader") -> Tuple[str, Optional[str]]:
    """Return (kind, anchor) for a model based on its creator's owning app.

    kind:   'noise'  — technical; skip.
            'pillar' — transversal pillar module.
            'domain' — functional Odoo application.
    anchor: app or pillar technical name (None for noise).
    """
    creators = kb.get_model_creators(model)
    if not creators:
        return ("noise", None)

    creator_module = creators[0]["module"]

    if creator_module in EXCLUDED_TECHNICAL_MODULES:
        return ("noise", None)

    if creator_module in PILLAR_MODULES:
        return ("pillar", creator_module)

    app = kb.get_module_app(creator_module)

    if app is None:
        return ("noise", None)

    if app in EXCLUDED_TECHNICAL_MODULES:
        # Owning app is a technical module (e.g. mail=application in Odoo 18).
        # The creator module itself is not technical — use it as the domain anchor.
        return ("domain", creator_module)

    if app in PILLAR_MODULES:
        return ("pillar", app)

    return ("domain", app)


# ---------------------------------------------------------------------------
# New-model domain resolution (Option C)
# ---------------------------------------------------------------------------


def _resolve_new_model_domain(ci: Any, kb: "KBReader") -> Tuple[str, Optional[str]]:
    """Attribute a brand-new custom model to a domain/pillar via structural links.

    Priority:
      1. _inherits parents (via KB model_origins).
      2. First required Many2one comodel (source-line order).
      3. First Many2one comodel (source-line order).

    Returns ('noise', None) when no link can be classified.
    """
    model_name = ci.model_name or ""

    # 1. _inherits parents
    for parent in kb.get_model_inherits(model_name):
        kind, anchor = _classify_model(parent, kb)
        if kind in ("domain", "pillar"):
            return (kind, anchor)

    # 2 & 3. Many2one fields, sorted by source line
    m2o_fields = sorted(
        (
            s
            for s in ci.symbols
            if s.kind == "field"
            and s.field_details
            and s.field_details.get("type") == "Many2one"
            and s.field_details.get("comodel")
        ),
        key=lambda s: s.lineno,
    )

    # Required first, then any
    required_m2o = [s for s in m2o_fields if s.field_details.get("required")]
    candidates = required_m2o + m2o_fields  # required first, rest after

    seen_comodels: set = set()
    for sym in candidates:
        comodel = sym.field_details.get("comodel")
        if not comodel or comodel in seen_comodels:
            continue
        seen_comodels.add(comodel)
        kind, anchor = _classify_model(comodel, kb)
        if kind in ("domain", "pillar"):
            return (kind, anchor)

    return ("noise", None)


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------


def compute_domain_profile(
    summary: "ModuleSummary",
    kb: "KBReader",
    weights: Dict[str, float],
) -> dict:
    """Compute the domain profile for a module summary.

    Args:
        summary: Fully-populated ModuleSummary (post-analyze).
        kb:      Open KBReader for the project KB.
        weights: Coefficient dict; keys match the AnalyzeConfig defaults.

    Returns:
        {
          "domains":       [{"domain", "label", "weight_raw", "score_proportional",
                             "score_relative", "indicators"}, ...],   # sorted by weight_raw desc
          "pillars":       [...same shape...],
          "custom_models": int,
        }
    """
    # Per-anchor accumulator keyed by technical name.
    anchors: Dict[str, Dict[str, Any]] = {}
    anchor_kind: Dict[str, str] = {}  # anchor → 'domain' | 'pillar'

    # Set of distinct extended models per anchor (for dedup).
    extended_models_seen: Dict[str, set] = {}

    custom_models = 0

    pairs = list(zip(summary.classes, summary.class_infos))

    for cs, ci in pairs:
        is_new = ci.is_new_model

        # Determine anchor via model classification.
        if is_new:
            kind, anchor = _resolve_new_model_domain(ci, kb)
        else:
            target_model = ci.inherit[0] if ci.inherit else ""
            kind, anchor = _classify_model(target_model, kb)

        if kind == "noise" or anchor is None:
            if is_new:
                custom_models += 1
            continue

        # Initialise accumulator for this anchor.
        if anchor not in anchors:
            anchors[anchor] = _empty_indicators()
            anchor_kind[anchor] = kind
            extended_models_seen[anchor] = set()

        ind = anchors[anchor]

        # models_extended: distinct upstream models extended by this module.
        if not is_new:
            model_name = ci.inherit[0] if ci.inherit else ci.class_name
            if model_name not in extended_models_seen[anchor]:
                extended_models_seen[anchor].add(model_name)
                ind["models_extended"] += 1

        # fields
        ind["fields_new"] += (cs.fields_base if is_new else cs.fields_new)
        ind["fields_override"] += cs.fields_inherited

        # methods
        for sym in ci.symbols:
            if sym.kind != "method":
                continue
            if sym.is_override:
                ind["methods_override"] += 1
            elif sym.kb_entry is not None and not is_new:
                ind["methods_inherited"] += 1
            else:
                ind["methods_new"] += 1

        # loc: sum of (end_lineno - lineno) over methods
        for sym in ci.symbols:
            if sym.kind == "method" and sym.end_lineno and sym.lineno:
                ind["loc"] += max(0, sym.end_lineno - sym.lineno)

    # views: classify by model, attribute to anchor
    vs = summary.views_summary
    if vs is not None:
        for view in vs.view_list:
            vmodel = view.get("model")
            if not vmodel:
                continue
            vkind, vanchor = _classify_model(vmodel, kb)
            if vkind == "noise" or vanchor is None:
                continue
            if vanchor not in anchors:
                anchors[vanchor] = _empty_indicators()
                anchor_kind[vanchor] = vkind
                extended_models_seen[vanchor] = set()
            if view.get("mode") == "primary":
                anchors[vanchor]["views_primary"] += 1
            else:
                anchors[vanchor]["views_extended"] += 1

    if not anchors:
        return {"domains": [], "pillars": [], "custom_models": custom_models}

    # LOC normalisation: divide each anchor's raw loc by max across all anchors.
    max_loc = max(d["loc"] for d in anchors.values()) or 1
    loc_normalized: Dict[str, float] = {
        a: d["loc"] / max_loc for a, d in anchors.items()
    }

    # Scoring
    def _weight_raw(a: str) -> float:
        d = anchors[a]
        ln = loc_normalized[a]
        return (
            weights.get("w_model_extend", 5.0) * d["models_extended"]
            + weights.get("w_field_new", 1.0) * d["fields_new"]
            + weights.get("w_field_override", 2.0) * d["fields_override"]
            + weights.get("w_method_new", 2.0) * d["methods_new"]
            + weights.get("w_method_inherit", 3.0) * d["methods_inherited"]
            + weights.get("w_method_override", 5.0) * d["methods_override"]
            + weights.get("w_view_extend", 2.0) * d["views_extended"]
            + weights.get("w_view_primary", 3.0) * d["views_primary"]
            + weights.get("w_loc", 1.0) * ln
        )

    weight_raws = {a: _weight_raw(a) for a in anchors}
    total_weight = sum(weight_raws.values()) or 1.0
    max_weight = max(weight_raws.values()) or 1.0

    def _entry(a: str) -> dict:
        wr = weight_raws[a]
        return {
            "domain": a,
            "label": domain_label(a),
            "weight_raw": round(wr, 4),
            "score_proportional": round(wr / total_weight, 4),
            "score_relative": round(wr / max_weight, 4),
            "indicators": dict(anchors[a]),
        }

    domains: List[dict] = sorted(
        [_entry(a) for a, k in anchor_kind.items() if k == "domain"],
        key=lambda e: e["weight_raw"],
        reverse=True,
    )
    pillars: List[dict] = sorted(
        [_entry(a) for a, k in anchor_kind.items() if k == "pillar"],
        key=lambda e: e["weight_raw"],
        reverse=True,
    )

    return {
        "domains": domains,
        "pillars": pillars,
        "custom_models": custom_models,
    }
