# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: cards.py — src/oops/output/markdown/cards.py

"""Descriptor-driven stat formatting for the Markdown site.

Values in the IR are raw; their display ``title`` and ``x-kind`` live in the
descriptor registry (``schema/analyze_ir_v2.json``). These helpers join the two
at render time — the same lookup the text and HTML formatters use — and emit
small Markdown tables (``| Label | Value |``).
"""

from __future__ import annotations

from oops.core.compat import Any, Dict, List, Optional
from oops.core.config import config
from oops.output.descriptors import kind_of, label_of
from oops.utils.render import render_markdown_table


def format_value(kind: str, value: Any) -> str:
    """Format a raw metric value for display according to its ``x-kind``."""
    if value is None:
        return ""
    if kind == "boolean":
        return config.check_symbol if value else ""
    if kind == "percent":
        # IR percent values are already numeric (e.g. 3.4) or "3.4%".
        text = str(value)
        return text if text.endswith("%") else f"{text}%"
    return str(value)


def descriptor_table(group: str, data: Dict[str, Any], keys: Optional[List[str]] = None) -> str:
    """Render ``data`` as a two-column ``| Label | Value |`` Markdown table.

    Labels and kinds are resolved from the descriptor registry for ``group``.
    Only keys present in ``data`` are emitted; ``keys`` fixes the order when
    given, otherwise insertion order is used.
    """
    ordered = [k for k in (keys or list(data)) if k in data]
    rows = [[label_of(group, key, key) or key, format_value(kind_of(group, key), data[key])] for key in ordered]
    return render_markdown_table(["Name", "Value"], rows) if rows else ""
