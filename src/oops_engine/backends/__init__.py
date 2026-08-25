# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: __init__.py — oops_engine/backends/__init__.py

"""Pluggable storage backends for oops_engine.store.

``SQLiteBackend`` is today's local-CLI behavior, byte-for-byte. ``PostgresBackend``
targets a shared, multi-tenant database (see the module docstring in
``oops_engine.store`` for the repo_id scoping model both backends share).
"""

from oops_engine.backends.base import Backend
from oops_engine.backends.sqlite import SQLiteBackend

__all__ = ["Backend", "SQLiteBackend"]
