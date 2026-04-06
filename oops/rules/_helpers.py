# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: _helpers.py — oops/rules/_helpers.py

"""Shared helpers for oops fixit rules.

\b
Import from here in every rule module so future rules don't duplicate code::

    from oops.rules._helpers import (
        load_manifest_cfg,
        extract_kv,
        string_value,
        key_name,
        sort_key,
        Elements,
        VERSION_PATTERN,
    )
"""

from typing import Any, List, Optional, Sequence, Tuple, Union  # noqa: UP035

import libcst as cst

from oops.core.config import ManifestConfig

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Fallback version pattern when odoo_version is not set in config.
# Matches the 5-part Odoo format: <odoo_major>.<odoo_minor>.<x>.<y>.<z>
# e.g. "16.0.1.0.0", "19.0.3.2.1"
VERSION_PATTERN = r"^\d+\.\d+\.\d+\.\d+\.\d+$"

# Type alias for the sequence of elements inside a cst.Dict.
Elements = Sequence[Union[cst.DictElement, cst.StarredDictElement]]

# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------


def load_manifest_cfg() -> Optional[ManifestConfig]:
    """Return the manifest section of .oops.yaml, or None if unavailable.

    Rules call this in ``__init__`` and fall back to class-level defaults when
    config is not present (e.g. standalone fixit invocation or CI without a
    project-level ``.oops.yaml``).
    """
    try:
        from oops.core.config import config as _cfg  # noqa: PLC0415

        return _cfg.manifest
    except Exception:
        return None


# ---------------------------------------------------------------------------
# CST helpers
# ---------------------------------------------------------------------------


def extract_kv(node: cst.Dict) -> "dict[str, cst.BaseExpression]":
    """Return a ``{key_str: value_node}`` map for all plain-string-keyed entries.

    Non-string keys (variables, f-strings, …) are silently skipped.
    """
    kv: dict[str, cst.BaseExpression] = {}
    for el in node.elements or []:
        if not isinstance(el, cst.DictElement):
            continue
        if isinstance(el.key, cst.SimpleString):
            kv[el.key.value.strip("'\"")] = el.value
    return kv


def string_value(node: cst.BaseExpression) -> "str | None":
    """Return the unquoted Python str for a ``SimpleString`` node, or None.

    Use this instead of accessing ``.value`` directly — it handles evaluation
    (escape sequences, raw strings) and skips f-strings or concatenations.
    """
    if isinstance(node, cst.SimpleString):
        val = node.evaluated_value
        return val if isinstance(val, str) else None
    return None


def key_name(element: Any) -> "str | None":
    """Return the string key of a ``DictElement``, or None if not a plain string."""
    key = element.key
    if isinstance(key, cst.SimpleString):
        return key.value.strip("'\"")
    return None


def sort_key(name: "str | None", order: List[str]) -> Tuple[int, str]:
    """Return a ``(position, name)`` tuple for sorting dict elements into *order*.

    Keys absent from *order* are pushed after all known keys; ties are broken
    by name so the sort is stable and deterministic.
    """
    if name is None:
        return (len(order), "")
    try:
        return (order.index(name), name)
    except ValueError:
        return (len(order), name)
