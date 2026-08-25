# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: resolver.py — oops_engine/resolver.py

"""Top-level inheritance resolver API.

Usage::

    from oops_engine.resolver import InheritanceResolver
    resolver = InheritanceResolver.from_project_kb(kb_path, repo_ids=["my-project"])
    result = resolver.resolve("res.partner", installed_modules={"base", "mail"})
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from oops_engine.inheritance import build_class_chain, compute_mro, merge_fields, merge_methods
from oops_engine.load_order import compute_load_order
from oops_engine.store import KBReader


class InheritanceResolver:
    """Resolve Odoo model inheritance without a live Odoo instance."""

    def __init__(self, reader: KBReader, _owns_reader: bool = False) -> None:
        self._reader = reader
        self._owns_reader = _owns_reader

    @classmethod
    def from_project_kb(cls, kb_path: Path, repo_ids: Sequence[str]) -> "InheritanceResolver":
        """Open a KB and return a resolver.

        Use as a context manager to ensure the connection is closed::

            with InheritanceResolver.from_project_kb(kb_path, repo_ids=["my-project"]) as resolver:
                result = resolver.resolve("sale.order")

        Args:
            kb_path: Path to a project KB ``.db`` file.
            repo_ids: repo_id(s) to search across (see ``KBReader``).
        """
        return cls(KBReader(kb_path, repo_ids=repo_ids), _owns_reader=True)

    def close(self) -> None:
        """Close the underlying KB connection if this resolver owns it."""
        if self._owns_reader:
            self._reader.close()

    def __enter__(self) -> "InheritanceResolver":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

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
        mro = compute_mro(chain, reader=reader, load_order=load_order)
        fields = merge_fields(mro, reader, load_order=load_order)
        methods = merge_methods(mro, reader, load_order=load_order)

        return {
            "model": model_name,
            "chain": chain,
            "mro": mro,
            "fields": fields,
            "methods": methods,
        }
