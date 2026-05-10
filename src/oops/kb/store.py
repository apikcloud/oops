# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: store.py — oops/kb/store.py

"""SQLite persistence layer for the Odoo KB.

Two databases, same schema:
- kb_global.db   : Odoo community + enterprise, generated once per version.
- kb_project.db  : global + third-party + apik, scoped to a project.

Schema (v2)
-----------
meta      (key, value)
sources   (origin, path)
modules   (name, origin, depends)      -- depends is a JSON array string
symbols   (model, name, kind, origin, module, source_file, source_line,
           field_type, section)
field_refs (model, field_name, module, kwarg, target_method)

Indexes
-------
idx_symbols_lookup  on symbols(model, name, kind)
idx_symbols_module  on symbols(module)
idx_modules_origin  on modules(origin)
idx_field_refs_target on field_refs(model, target_method)
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from oops.utils.compat import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Schema versioning
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 2  # bumped from implicit v1 (no field_type / section / field_refs)

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    origin TEXT NOT NULL PRIMARY KEY,
    path   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS modules (
    name    TEXT NOT NULL PRIMARY KEY,
    origin  TEXT NOT NULL,
    depends TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_modules_origin ON modules (origin);

CREATE TABLE IF NOT EXISTS symbols (
    model       TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    kind        TEXT    NOT NULL,           -- 'field' | 'method'
    origin      TEXT    NOT NULL,
    module      TEXT    NOT NULL,
    source_file TEXT    NOT NULL,
    source_line INTEGER NOT NULL,
    field_type  TEXT,                       -- e.g. 'Boolean' / NULL for methods
    section     TEXT,                       -- canonical section name / NULL for fields
    PRIMARY KEY (model, name, kind, module)
);
CREATE INDEX IF NOT EXISTS idx_symbols_lookup ON symbols (model, name, kind);
CREATE INDEX IF NOT EXISTS idx_symbols_module ON symbols (module);

CREATE TABLE IF NOT EXISTS field_refs (
    model         TEXT NOT NULL,
    field_name    TEXT NOT NULL,
    module        TEXT NOT NULL,
    kwarg         TEXT NOT NULL,            -- 'compute' | 'inverse' | 'search' | 'default' | 'selection'
    target_method TEXT NOT NULL,
    PRIMARY KEY (model, field_name, module, kwarg)
);
CREATE INDEX IF NOT EXISTS idx_field_refs_target ON field_refs (model, target_method);
"""


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open (and initialise if new) a KB SQLite database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.executescript(_DDL)
    con.commit()
    return con


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def write_global_kb(
    db_path: Path,
    odoo_version: str,
    sources: Dict[str, str],
    scan_results: List[Dict[str, Any]],
) -> None:
    """Write (or overwrite) a global KB database.

    Args:
        db_path:      destination .db file (created if absent).
        odoo_version: e.g. '17.0'.
        sources:      { origin: absolute_path_string }.
        scan_results: list of ScanResult dicts from scanner.scan_tier().
    """
    _write_kb(
        db_path=db_path,
        layer="global",
        odoo_version=odoo_version,
        project=None,
        scope=None,
        sources=sources,
        scan_results=scan_results,
    )


def write_project_kb(
    db_path: Path,
    odoo_version: str,
    project: str,
    scope: List[str],
    sources: Dict[str, str],
    scan_results: List[Dict[str, Any]],
) -> None:
    """Write (or overwrite) a project KB database.

    Args:
        db_path:      destination .db file.
        odoo_version: e.g. '17.0'.
        project:      project slug string.
        scope:        sorted list of module names in scope.
        sources:      { origin: absolute_path_string }.
        scan_results: list of ScanResult dicts (global already merged in by caller).
    """
    _write_kb(
        db_path=db_path,
        layer="project",
        odoo_version=odoo_version,
        project=project,
        scope=scope,
        sources=sources,
        scan_results=scan_results,
    )


def _write_kb(
    db_path: Path,
    layer: str,
    odoo_version: str,
    project: Optional[str],
    scope: Optional[List[str]],
    sources: Dict[str, str],
    scan_results: List[Dict[str, Any]],
) -> None:
    """Internal: write all KB data to db_path, replacing any previous content."""
    con = _connect(db_path)

    with con:
        # Schema may have evolved: drop and re-create all data tables so column
        # additions always land on existing on-disk databases.
        for table in ("field_refs", "symbols", "modules", "sources", "meta"):
            con.execute(f"DROP TABLE IF EXISTS {table}")
        con.executescript(_DDL)

        # --- meta ---
        meta_rows = [
            ("layer", layer),
            ("odoo_version", odoo_version),
            ("schema_version", str(SCHEMA_VERSION)),
            ("generated_at", datetime.now(timezone.utc).isoformat()),
        ]
        if project:
            meta_rows.append(("project", project))
        if scope is not None:
            meta_rows.append(("scope", json.dumps(scope)))
        con.executemany("INSERT INTO meta (key, value) VALUES (?, ?)", meta_rows)

        # --- sources ---
        con.executemany(
            "INSERT INTO sources (origin, path) VALUES (?, ?)",
            sources.items(),
        )

        # --- modules + symbols + field_refs from all scan results ---
        for result in scan_results:
            for mod_name, mod_data in result.get("modules", {}).items():
                con.execute(
                    """
                    INSERT OR REPLACE INTO modules (name, origin, depends)
                    VALUES (?, ?, ?)
                    """,
                    (
                        mod_name,
                        mod_data["origin"],
                        json.dumps(mod_data["depends"]),
                    ),
                )

            for sym in result.get("symbols", []):
                con.execute(
                    """
                    INSERT OR REPLACE INTO symbols
                        (model, name, kind, origin, module, source_file, source_line,
                         field_type, section)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sym["model"],
                        sym["name"],
                        sym["kind"],
                        sym["origin"],
                        sym["module"],
                        sym["source_file"],
                        sym["source_line"],
                        sym.get("field_type"),
                        sym.get("section"),
                    ),
                )

            for ref in result.get("field_refs", []):
                con.execute(
                    """
                    INSERT OR REPLACE INTO field_refs
                        (model, field_name, module, kwarg, target_method)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        ref["model"],
                        ref["field_name"],
                        ref["module"],
                        ref["kwarg"],
                        ref["target_method"],
                    ),
                )

    con.close()
    _log_stats(db_path)


def _log_stats(db_path: Path) -> None:
    con = _connect(db_path)
    n_mod = con.execute("SELECT COUNT(*) FROM modules").fetchone()[0]
    n_sym = con.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
    n_fld = con.execute("SELECT COUNT(*) FROM symbols WHERE kind='field'").fetchone()[0]
    n_mth = con.execute("SELECT COUNT(*) FROM symbols WHERE kind='method'").fetchone()[0]
    n_refs = con.execute("SELECT COUNT(*) FROM field_refs").fetchone()[0]
    con.close()
    logging.info(
        "KB written → %s  [%d modules | %d symbols: %d fields, %d methods | %d field_refs]",
        db_path,
        n_mod,
        n_sym,
        n_fld,
        n_mth,
        n_refs,
    )


# ---------------------------------------------------------------------------
# Read helpers (used by refactor.py and resolve.py)
# ---------------------------------------------------------------------------


class KBReader:
    """Read-only interface to a KB SQLite database.

    Usage:
        kb = KBReader(Path(".oops-cache/kb_project.db"))
        entries = kb.get_symbol("sale.order", "action_confirm", "method")
        modules = kb.get_modules()
    """

    def __init__(self, db_path: Path) -> None:
        if not db_path.exists():
            raise FileNotFoundError(f"KB database not found: {db_path}")
        self._con = sqlite3.connect(str(db_path))
        self._con.row_factory = sqlite3.Row

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> "KBReader":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # --- meta ---

    def get_meta(self) -> Dict[str, str]:
        """Return all meta key/value pairs."""
        rows = self._con.execute("SELECT key, value FROM meta").fetchall()
        return {r["key"]: r["value"] for r in rows}

    # --- modules ---

    def get_modules(self) -> Dict[str, Dict[str, Any]]:
        """Return all modules as { name: {origin, depends: [str,...]} }."""
        rows = self._con.execute("SELECT name, origin, depends FROM modules").fetchall()
        return {
            r["name"]: {
                "origin": r["origin"],
                "depends": json.loads(r["depends"]),
            }
            for r in rows
        }

    def module_exists(self, name: str) -> bool:
        row = self._con.execute("SELECT 1 FROM modules WHERE name = ?", (name,)).fetchone()
        return row is not None

    # --- symbols ---

    def get_symbol(
        self,
        model: str,
        name: str,
        kind: str,
    ) -> List[Dict[str, Any]]:
        """Return all KB entries for a symbol (may span multiple modules).

        Args:
            model: dotted model name, e.g. 'sale.order'.
            name:  field or method name.
            kind:  'field' or 'method'.

        Returns:
            List of dicts with keys: origin, module, source_file, source_line,
            field_type, section. Empty list if symbol is not found.
        """
        rows = self._con.execute(
            """
            SELECT origin, module, source_file, source_line, field_type, section
            FROM   symbols
            WHERE  model = ? AND name = ? AND kind = ?
            ORDER  BY origin  -- stable ordering; resolve.py re-sorts by depends
            """,
            (model, name, kind),
        ).fetchall()
        return [dict(r) for r in rows]

    def symbol_exists(self, model: str, name: str, kind: str) -> bool:
        """Return True if the symbol exists in any upstream module."""
        row = self._con.execute(
            "SELECT 1 FROM symbols WHERE model=? AND name=? AND kind=?",
            (model, name, kind),
        ).fetchone()
        return row is not None

    def model_exists(self, model: str) -> bool:
        """Return True if any upstream module defines or extends this model."""
        row = self._con.execute("SELECT 1 FROM symbols WHERE model = ? LIMIT 1", (model,)).fetchone()
        return row is not None

    def get_model_symbols(
        self,
        model: str,
        kind: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return all symbols defined on a model across all upstream modules.

        Args:
            model: dotted model name.
            kind:  optional filter — 'field' or 'method'.
        """
        if kind:
            rows = self._con.execute(
                """
                SELECT name, kind, origin, module, source_file, source_line,
                       field_type, section
                FROM   symbols
                WHERE  model = ? AND kind = ?
                ORDER  BY name
                """,
                (model, kind),
            ).fetchall()
        else:
            rows = self._con.execute(
                """
                SELECT name, kind, origin, module, source_file, source_line,
                       field_type, section
                FROM   symbols
                WHERE  model = ?
                ORDER  BY kind, name
                """,
                (model,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_sources(self) -> Dict[str, str]:
        """Return { origin: path } for all indexed source roots."""
        rows = self._con.execute("SELECT origin, path FROM sources").fetchall()
        return {r["origin"]: r["path"] for r in rows}

    # --- field_refs ---

    def get_field_refs_for_method(
        self, model: str, target_method: str
    ) -> List[Dict[str, Any]]:
        """Return [{module, field_name, kwarg}, ...] for fields referencing this method."""
        rows = self._con.execute(
            """
            SELECT module, field_name, kwarg
            FROM   field_refs
            WHERE  model = ? AND target_method = ?
            ORDER  BY module, kwarg, field_name
            """,
            (model, target_method),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_field_refs_for_field(
        self, model: str, field_name: str, module: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return [{kwarg, target_method, module}, ...] for kwargs of this field."""
        if module is None:
            rows = self._con.execute(
                "SELECT kwarg, target_method, module FROM field_refs "
                "WHERE model=? AND field_name=? ORDER BY module, kwarg",
                (model, field_name),
            ).fetchall()
        else:
            rows = self._con.execute(
                "SELECT kwarg, target_method, module FROM field_refs "
                "WHERE model=? AND field_name=? AND module=? ORDER BY kwarg",
                (model, field_name, module),
            ).fetchall()
        return [dict(r) for r in rows]
