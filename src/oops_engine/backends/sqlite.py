# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: sqlite.py — oops_engine/backends/sqlite.py

"""SQLite backend — today's local-CLI behavior, byte-for-byte."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from oops.core.compat import List, Sequence

# ---------------------------------------------------------------------------
# DDL — see oops_engine.store's module docstring for the schema shape.
# ---------------------------------------------------------------------------

DDL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS repo_meta (
    repo_id TEXT NOT NULL,
    key     TEXT NOT NULL,
    value   TEXT NOT NULL,
    PRIMARY KEY (repo_id, key)
);

CREATE TABLE IF NOT EXISTS sources (
    repo_id TEXT NOT NULL,
    origin  TEXT NOT NULL,
    path    TEXT NOT NULL,
    PRIMARY KEY (repo_id, origin)
);

CREATE TABLE IF NOT EXISTS modules (
    repo_id     TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    origin      TEXT    NOT NULL,
    depends     TEXT    NOT NULL DEFAULT '[]',
    application INTEGER NOT NULL DEFAULT 0,
    app         TEXT,
    depth       INTEGER,
    load_index  INTEGER,
    PRIMARY KEY (repo_id, name)
);
CREATE INDEX IF NOT EXISTS idx_modules_origin ON modules (repo_id, origin);

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
    attrs_json  TEXT,
    has_super   INTEGER,
    PRIMARY KEY (repo_id, model, name, kind, module)
);
CREATE INDEX IF NOT EXISTS idx_symbols_lookup ON symbols (repo_id, model, name, kind);
CREATE INDEX IF NOT EXISTS idx_symbols_module ON symbols (repo_id, module);

CREATE TABLE IF NOT EXISTS field_refs (
    repo_id       TEXT NOT NULL,
    model         TEXT NOT NULL,
    field_name    TEXT NOT NULL,
    module        TEXT NOT NULL,
    kwarg         TEXT NOT NULL,
    target_method TEXT NOT NULL,
    PRIMARY KEY (repo_id, model, field_name, module, kwarg)
);
CREATE INDEX IF NOT EXISTS idx_field_refs_target ON field_refs (repo_id, model, target_method);

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
);
CREATE INDEX IF NOT EXISTS idx_model_origins_model ON model_origins (repo_id, model);
CREATE INDEX IF NOT EXISTS idx_model_origins_role  ON model_origins (repo_id, model, role);

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
    fields_json  TEXT NOT NULL DEFAULT '[]',
    buttons_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (repo_id, xml_id)
);
CREATE INDEX IF NOT EXISTS idx_views_model   ON views (repo_id, model);
CREATE INDEX IF NOT EXISTS idx_views_inherit ON views (repo_id, inherit_id);
CREATE INDEX IF NOT EXISTS idx_views_module  ON views (repo_id, module);
CREATE INDEX IF NOT EXISTS idx_views_origin  ON views (repo_id, origin);

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
);
CREATE INDEX IF NOT EXISTS idx_actions_model  ON actions (repo_id, model);
CREATE INDEX IF NOT EXISTS idx_actions_module ON actions (repo_id, module);

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
);
CREATE INDEX IF NOT EXISTS idx_menus_action  ON menus (repo_id, action);
CREATE INDEX IF NOT EXISTS idx_menus_parent  ON menus (repo_id, parent_id);
CREATE INDEX IF NOT EXISTS idx_menus_module  ON menus (repo_id, module);

CREATE TABLE IF NOT EXISTS analysis_cache (
    repo_id             TEXT NOT NULL,
    module_name         TEXT NOT NULL,
    content_fingerprint TEXT NOT NULL,
    kb_generated_at     TEXT NOT NULL,
    payload_json        TEXT NOT NULL,
    cached_at           TEXT NOT NULL,
    PRIMARY KEY (repo_id, module_name, content_fingerprint)
);

CREATE TABLE IF NOT EXISTS loc_cache (
    repo_id             TEXT NOT NULL,
    addon_path          TEXT NOT NULL,
    content_fingerprint TEXT NOT NULL,
    loc_json            TEXT NOT NULL,
    cached_at           TEXT NOT NULL,
    PRIMARY KEY (repo_id, addon_path, content_fingerprint)
);
"""


# Tables that existed before schema v10 (repo_id scoping) — a KB file written
# by an older `oops` release has these without a `repo_id` column. `CREATE
# TABLE IF NOT EXISTS` is a no-op on a table that already exists, so an old
# file's physical schema never catches up on its own; _reset_if_legacy_schema()
# drops them so the DDL below recreates them on the current schema. `repo_meta`
# and `analysis_cache` never existed pre-v10, so there is nothing to drop there.
_LEGACY_TABLES = (
    "meta", "sources", "modules", "symbols", "field_refs",
    "model_origins", "views", "actions", "menus",
)


def _reset_if_legacy_schema(con: sqlite3.Connection) -> None:
    """Drop pre-v10 tables from an existing KB file so DDL recreates them fresh.

    Local KB files (project cache, global cache) are disposable — regenerated
    by `build_project_kb()`/`oops misc build-kb` — so dropping and letting the
    caller's write rebuild them is safe and requires no data migration.
    """
    cols = {row[1] for row in con.execute("PRAGMA table_info(modules)")}
    if not cols or "repo_id" in cols:
        return  # brand-new file, or already on the current schema
    for table in _LEGACY_TABLES:
        con.execute(f"DROP TABLE IF EXISTS {table}")
    con.commit()


def _reset_stale_analysis_cache(con: sqlite3.Connection) -> None:
    """Drop analysis_cache if it predates the content_fingerprint key — disposable, safe to drop."""
    cols = {row[1] for row in con.execute("PRAGMA table_info(analysis_cache)")}
    if cols and "content_fingerprint" not in cols:
        con.execute("DROP TABLE IF EXISTS analysis_cache")
        con.commit()


class SQLiteBackend:
    """Local single-file SQLite storage — today's behavior, byte-for-byte."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        """Open (and initialise if new) the KB SQLite database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        _reset_if_legacy_schema(con)
        _reset_stale_analysis_cache(con)
        con.executescript(DDL)
        con.commit()
        return con

    def ddl_statements(self) -> List[str]:
        return [DDL]

    def upsert_sql(self, table: str, columns: Sequence[str], conflict_columns: Sequence[str]) -> str:
        del conflict_columns  # SQLite's OR REPLACE needs no explicit conflict target
        cols = ", ".join(columns)
        placeholders = ", ".join("?" for _ in columns)
        return f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({placeholders})"

    def placeholder(self) -> str:
        return "?"

    def exists(self) -> bool:
        return self.db_path.exists()
