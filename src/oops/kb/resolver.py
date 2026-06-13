# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: resolver.py — oops/kb/resolver.py

"""Top-level inheritance resolver API.

Usage::

    from oops.kb.resolver import InheritanceResolver
    resolver = InheritanceResolver.from_project_kb(kb_path)
    result = resolver.resolve("res.partner", installed_modules={"base", "mail"})
"""
from __future__ import annotations

from pathlib import Path

from oops.kb.inheritance import build_class_chain, compute_mro, merge_fields
from oops.kb.load_order import compute_load_order
from oops.kb.store import KBReader


class InheritanceResolver:
    """Resolve Odoo model inheritance without a live Odoo instance."""

    def __init__(self, reader: KBReader) -> None:
        self._reader = reader

    @classmethod
    def from_project_kb(cls, kb_path: Path) -> "InheritanceResolver":
        """Open a KB and return a resolver.

        Args:
            kb_path: Path to a project KB ``.db`` file.
        """
        return cls(KBReader(kb_path))

    def resolve(
        self,
        model_name: str,
        installed_modules: set[str] | None = None,
    ) -> dict:
        """Return the full resolver output for model_name.

        Args:
            model_name: Dotted Odoo model name, e.g. ``'sale.order'``.
            installed_modules: Restrict resolution to this module set.
                ``None`` uses all modules present in the KB.

        Returns:
            Dict with keys ``model``, ``chain``, ``mro``, ``fields``.
        """
        reader = self._reader
        all_depends = reader.get_modules_with_depends()

        if installed_modules is None:
            installed_modules = set(all_depends.keys())

        load_order = compute_load_order(installed_modules, all_depends)
        chain = build_class_chain(model_name, reader, load_order)
        mro = compute_mro(chain)
        fields = merge_fields(mro, reader)

        return {
            "model": model_name,
            "chain": chain,
            "mro": mro,
            "fields": fields,
        }
