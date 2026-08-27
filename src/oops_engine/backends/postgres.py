# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: postgres.py — oops_engine/backends/postgres.py

"""Postgres backend — shared, multi-tenant database target.

Requires the ``postgres`` extra (``psycopg[binary]``), imported lazily so the
base ``oops_engine`` install never needs it.
"""

from __future__ import annotations

from oops_engine.compat import Any, List, Sequence

# Same table/column/index shapes as SQLiteBackend.DDL, translated:
#   INTEGER (bool flags) -> BOOLEAN, *_json TEXT -> JSONB, no PRAGMA statements,
#   SQLite's implicit rowid tables -> plain Postgres tables.
DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS repo_meta (
        repo_id TEXT NOT NULL,
        key     TEXT NOT NULL,
        value   TEXT NOT NULL,
        PRIMARY KEY (repo_id, key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sources (
        repo_id TEXT NOT NULL,
        origin  TEXT NOT NULL,
        path    TEXT NOT NULL,
        PRIMARY KEY (repo_id, origin)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS modules (
        repo_id     TEXT    NOT NULL,
        name        TEXT    NOT NULL,
        origin      TEXT    NOT NULL,
        depends     TEXT    NOT NULL DEFAULT '[]',
        application BOOLEAN NOT NULL DEFAULT FALSE,
        app         TEXT,
        depth       INTEGER,
        load_index  INTEGER,
        PRIMARY KEY (repo_id, name)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_modules_origin ON modules (repo_id, origin)",
    """
    CREATE TABLE IF NOT EXISTS symbols (
        repo_id     TEXT    NOT NULL,
        model       TEXT    NOT NULL,
        name        TEXT    NOT NULL,
        kind        TEXT    NOT NULL,
        origin      TEXT    NOT NULL,
        module      TEXT    NOT NULL,
        source_file TEXT    NOT NULL,
        source_line INTEGER NOT NULL,
        source_end_line INTEGER,
        field_type  TEXT,
        section     TEXT,
        import_index INTEGER,
        attrs_json  JSONB,
        has_super   BOOLEAN,
        PRIMARY KEY (repo_id, model, name, kind, module)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_symbols_lookup ON symbols (repo_id, model, name, kind)",
    "CREATE INDEX IF NOT EXISTS idx_symbols_module ON symbols (repo_id, module)",
    """
    CREATE TABLE IF NOT EXISTS field_refs (
        repo_id       TEXT NOT NULL,
        model         TEXT NOT NULL,
        field_name    TEXT NOT NULL,
        module        TEXT NOT NULL,
        kwarg         TEXT NOT NULL,
        target_method TEXT NOT NULL,
        PRIMARY KEY (repo_id, model, field_name, module, kwarg)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_field_refs_target ON field_refs (repo_id, model, target_method)",
    """
    CREATE TABLE IF NOT EXISTS model_origins (
        repo_id       TEXT    NOT NULL,
        model         TEXT    NOT NULL,
        module        TEXT    NOT NULL,
        origin        TEXT    NOT NULL,
        role          TEXT    NOT NULL,
        model_type    TEXT    NOT NULL DEFAULT 'model',
        inherit_json  TEXT    NOT NULL DEFAULT '[]',
        inherits_json TEXT    NOT NULL DEFAULT '{}',
        source_file   TEXT    NOT NULL,
        source_line   INTEGER NOT NULL,
        description   TEXT,
        import_index  INTEGER,
        PRIMARY KEY (repo_id, model, module)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_model_origins_model ON model_origins (repo_id, model)",
    "CREATE INDEX IF NOT EXISTS idx_model_origins_role  ON model_origins (repo_id, model, role)",
    """
    CREATE TABLE IF NOT EXISTS views (
        repo_id      TEXT NOT NULL,
        xml_id       TEXT NOT NULL,
        module       TEXT NOT NULL,
        origin       TEXT NOT NULL,
        name         TEXT,
        model        TEXT,
        view_type    TEXT,
        inherit_id   TEXT,
        mode         TEXT NOT NULL,
        source_file  TEXT NOT NULL,
        source_line  INTEGER NOT NULL,
        source_end_line INTEGER,
        fields_json  JSONB NOT NULL DEFAULT '[]',
        buttons_json JSONB NOT NULL DEFAULT '[]',
        PRIMARY KEY (repo_id, xml_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_views_model   ON views (repo_id, model)",
    "CREATE INDEX IF NOT EXISTS idx_views_inherit ON views (repo_id, inherit_id)",
    "CREATE INDEX IF NOT EXISTS idx_views_module  ON views (repo_id, module)",
    "CREATE INDEX IF NOT EXISTS idx_views_origin  ON views (repo_id, origin)",
    """
    CREATE TABLE IF NOT EXISTS actions (
        repo_id      TEXT NOT NULL,
        xml_id       TEXT NOT NULL,
        module       TEXT NOT NULL,
        origin       TEXT NOT NULL,
        name         TEXT,
        model        TEXT,
        view_id      TEXT,
        domain       TEXT,
        source_file  TEXT NOT NULL,
        source_line  INTEGER NOT NULL,
        PRIMARY KEY (repo_id, xml_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_actions_model  ON actions (repo_id, model)",
    "CREATE INDEX IF NOT EXISTS idx_actions_module ON actions (repo_id, module)",
    """
    CREATE TABLE IF NOT EXISTS menus (
        repo_id      TEXT NOT NULL,
        xml_id       TEXT NOT NULL,
        module       TEXT NOT NULL,
        origin       TEXT NOT NULL,
        name         TEXT,
        action       TEXT,
        parent_id    TEXT,
        source_file  TEXT NOT NULL,
        source_line  INTEGER NOT NULL,
        PRIMARY KEY (repo_id, xml_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_menus_action  ON menus (repo_id, action)",
    "CREATE INDEX IF NOT EXISTS idx_menus_parent  ON menus (repo_id, parent_id)",
    "CREATE INDEX IF NOT EXISTS idx_menus_module  ON menus (repo_id, module)",
    """
    CREATE TABLE IF NOT EXISTS analysis_cache (
        repo_id             TEXT NOT NULL,
        module_name         TEXT NOT NULL,
        content_fingerprint TEXT NOT NULL,
        kb_generated_at     TEXT NOT NULL,
        payload_json        JSONB NOT NULL,
        cached_at           TEXT NOT NULL,
        PRIMARY KEY (repo_id, module_name, content_fingerprint)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS loc_cache (
        repo_id             TEXT NOT NULL,
        addon_path          TEXT NOT NULL,
        content_fingerprint TEXT NOT NULL,
        loc_json            JSONB NOT NULL,
        cached_at           TEXT NOT NULL,
        PRIMARY KEY (repo_id, addon_path, content_fingerprint)
    )
    """,
]


class PostgresBackend:
    """Shared, multi-tenant Postgres storage — one table set, many repo_ids."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def connect(self) -> Any:
        import psycopg  # noqa: PLC0415 — optional dependency, only needed here
        from psycopg.rows import dict_row  # noqa: PLC0415

        # dict_row so callers can index rows by column name, matching sqlite3.Row.
        con = psycopg.connect(self._dsn, row_factory=dict_row)
        with con.cursor() as cur:
            for stmt in self.ddl_statements():
                cur.execute(stmt)
        con.commit()
        return con

    def ddl_statements(self) -> List[str]:
        return DDL_STATEMENTS

    def upsert_sql(self, table: str, columns: Sequence[str], conflict_columns: Sequence[str]) -> str:
        cols = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        update_cols = [c for c in columns if c not in conflict_columns]
        if update_cols:
            updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in update_cols)
            conflict_clause = f"ON CONFLICT ({', '.join(conflict_columns)}) DO UPDATE SET {updates}"
        else:
            # Every column is part of the conflict target — nothing to update.
            conflict_clause = f"ON CONFLICT ({', '.join(conflict_columns)}) DO NOTHING"
        return f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) {conflict_clause}"

    def placeholder(self) -> str:
        return "%s"
