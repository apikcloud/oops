# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: load_order.py — oops/kb/load_order.py

"""Phase 1 of the Odoo inheritance resolver: module load order.

Algorithm matches Odoo's Graph.__iter__ (graph.py, stable across 10.0–19.0):
  depth(m) = max(depth(d) for d in depends(m) ∩ installed, default=-1) + 1
  load_order = sorted(installed, key=lambda m: (depth(m), m))
  load_index[m] = position in load_order

Returns dict: module_name -> (depth, load_index).
Drops depends entries not in `installed`; caller may log them as inconsistencies.
"""
from __future__ import annotations


def compute_load_order(
    installed: set[str],
    depends: dict[str, list[str]],
) -> dict[str, tuple[int, int]]:
    """Compute depth and load_index for every installed module.

    Args:
        installed: Set of module names to include in the ordering.
        depends: Mapping of module name to its declared dependency list.

    Returns:
        Mapping of module name to ``(depth, load_index)``.
        Depth is the longest path to a root (module with no installed deps).
        Load index is the 0-based position in ``sorted(installed, key=(depth, name))``.
    """
    depths: dict[str, int] = {}

    def depth_of(name: str) -> int:
        if name in depths:
            return depths[name]
        deps = [d for d in depends.get(name, []) if d in installed]
        d = max((depth_of(dep) for dep in deps), default=-1) + 1
        depths[name] = d
        return d

    for m in installed:
        depth_of(m)

    ordered = sorted(installed, key=lambda m: (depths[m], m))
    return {m: (depths[m], idx) for idx, m in enumerate(ordered)}
