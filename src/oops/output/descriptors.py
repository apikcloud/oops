# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: descriptors.py — src/oops/output/descriptors.py

"""Loader for the analyze IR v2 descriptor registry (spec §0a).

The registry (``schema/analyze_ir_v2.json``) is the single source of truth that
*describes* every ``manifest`` / ``metrics`` / ``loc`` metric key — its display
``title``, its ``x-kind`` (count | percent | text | bytes | boolean | …) and its
``x-unit``. The per-module JSON payload carries only raw values; each formatter
joins the two at render time. The text and (future) HTML formatters resolve
labels/kinds from here instead of hardcoding them.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files

from oops.core.compat import Any, Dict, Optional

_SCHEMA_RESOURCE = files("oops.output") / "schema" / "analyze_ir_v2.json"


@lru_cache(maxsize=1)
def load_descriptors() -> Dict[str, Any]:
    """Load and cache the parsed descriptor registry."""
    return json.loads(_SCHEMA_RESOURCE.read_text(encoding="utf-8"))


def _group_props(group: str) -> Dict[str, Any]:
    return load_descriptors().get("definitions", {}).get(group, {}).get("properties", {})


def descriptor(group: str, key: str) -> Optional[Dict[str, Any]]:
    """Return the descriptor dict for ``group.key`` (e.g. ``"metrics", "own_fields"``)."""
    return _group_props(group).get(key)


def label_of(group: str, key: str, default: Optional[str] = None) -> Optional[str]:
    """Return the display ``title`` for a metric key, or ``default`` when undescribed."""
    d = descriptor(group, key)
    return d.get("title") if d else default


def kind_of(group: str, key: str, default: str = "count") -> str:
    """Return the ``x-kind`` for a metric key, or ``default`` when undescribed."""
    d = descriptor(group, key)
    return d["x-kind"] if d and "x-kind" in d else default


def schema_version() -> Optional[int]:
    """Return the registry's ``x-schema-version`` (the IR schema version, 2)."""
    return load_descriptors().get("x-schema-version")
