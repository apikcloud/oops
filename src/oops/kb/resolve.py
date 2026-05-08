# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: resolve.py — oops/kb/resolve.py

"""Dependency graph resolution for KB symbol precedence.

Given a custom module and a list of symbol entries (each from a different
upstream module), this module selects the most relevant entry — i.e. the
one that is closest to the custom module in the dependency graph.

Algorithm
---------
1. Build the full transitive dependency list of the custom module by walking
   the `depends` graph from the KB (BFS, closest-first).
2. For each symbol entry, compute its position in that list
   (lower index = closer to the custom module = higher precedence).
3. Return the entry with the lowest index (most specific).
4. Tie-break with the static tier order: third-party > apik > enterprise > odoo.
5. If the symbol is not found in the depends chain at all, fall back to
   tier order and emit a warning.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

log = logging.getLogger(__name__)

# Static tier precedence used as tie-breaker (lower index = higher precedence).
TIER_PRECEDENCE = ["third-party", "apik", "enterprise", "odoo"]


def _tier_rank(origin: str) -> int:
    """Return the static precedence rank of a tier (lower = higher precedence)."""
    try:
        return TIER_PRECEDENCE.index(origin)
    except ValueError:
        return len(TIER_PRECEDENCE)


def build_depends_chain(
    module: str,
    modules_index: dict[str, dict[str, Any]],
) -> list[str]:
    """Return the ordered transitive dependency list of a module (BFS).

    The result is ordered from most specific (direct depends of `module`)
    to least specific (deep transitive dependencies). `module` itself is
    NOT included.

    Args:
        module:         the starting module name.
        modules_index:  { name: {"origin": str, "depends": [str, ...]} }
                        as returned by KBReader.get_modules().

    Returns:
        Ordered list of module names, closest first.
        Modules absent from the index are silently skipped.
    """
    visited: set[str] = {module}
    chain: list[str] = []
    queue: deque[str] = deque()

    # Seed with direct depends.
    for dep in modules_index.get(module, {}).get("depends", []):
        if dep not in visited:
            visited.add(dep)
            queue.append(dep)
            chain.append(dep)

    # BFS for transitive depends.
    while queue:
        current = queue.popleft()
        for dep in modules_index.get(current, {}).get("depends", []):
            if dep not in visited:
                visited.add(dep)
                queue.append(dep)
                chain.append(dep)

    return chain


def resolve_symbol(
    entries: list[dict[str, Any]],
    custom_module: str,
    modules_index: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Select the most relevant KB entry for a symbol.

    Args:
        entries:        list of dicts from KBReader.get_symbol(), each with
                        at least 'module' and 'origin' keys.
        custom_module:  name of the module being refactored.
        modules_index:  full modules dict from KBReader.get_modules().

    Returns:
        The selected entry dict, or None if entries is empty.
    """
    if not entries:
        return None
    if len(entries) == 1:
        return entries[0]

    chain = build_depends_chain(custom_module, modules_index)
    chain_index = {mod: i for i, mod in enumerate(chain)}

    def sort_key(entry: dict[str, Any]) -> tuple[int, int]:
        mod = entry["module"]
        # Position in depends chain (lower = closer = more specific).
        pos = chain_index.get(mod, len(chain))
        # Tier rank as tie-breaker.
        rank = _tier_rank(entry.get("origin", ""))
        return (pos, rank)

    sorted_entries = sorted(entries, key=sort_key)
    best = sorted_entries[0]

    # Warn if the winning module is not in the depends chain at all —
    # likely a missing depends declaration.
    if best["module"] not in chain_index:
        log.warning(
            "Symbol resolved via tier fallback (module '%s' not in depends chain "
            "of '%s'). Consider adding it to the manifest depends.",
            best["module"],
            custom_module,
        )

    return best


def format_source_line(entry: dict[str, Any]) -> str:
    """Format a Source: line for a docstring from a KB entry.

    Returns a string like:
        [odoo] addons/sale/models/sale_order.py, line 234
    """
    origin = entry.get("origin", "?")
    source_file = entry.get("source_file", "?")
    source_line = entry.get("source_line", "?")
    return f"[{origin}] {source_file}, line {source_line}"
