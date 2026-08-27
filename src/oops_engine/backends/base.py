# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: base.py — oops_engine/backends/base.py

"""Backend protocol shared by SQLiteBackend and PostgresBackend."""

from __future__ import annotations

from oops_engine.compat import Any, List, Protocol, Sequence


class Backend(Protocol):
    """A storage backend for oops_engine.store.

    Implementations own dialect differences only — the DDL shape, the
    upsert syntax, and the parameter placeholder style. Every other part of
    ``store.py`` (schema semantics, repo_id scoping, the read/write API) is
    dialect-agnostic and shared by both backends.
    """

    def connect(self) -> Any:
        """Return a DB-API 2.0 connection, with the schema already applied."""
        ...

    def ddl_statements(self) -> List[str]:
        """Return the CREATE TABLE/INDEX statements for this dialect."""
        ...

    def upsert_sql(self, table: str, columns: Sequence[str], conflict_columns: Sequence[str]) -> str:
        """Return an upsert (insert-or-replace) statement for one row.

        Args:
            table: Target table name.
            columns: Full ordered column list (values are bound positionally
                in this order).
            conflict_columns: The columns forming the table's PRIMARY KEY —
                used by dialects that need an explicit conflict target
                (e.g. Postgres's ``ON CONFLICT``).
        """
        ...

    def placeholder(self) -> str:
        """Return this dialect's bound-parameter placeholder (``"?"``/``"%s"``)."""
        ...
