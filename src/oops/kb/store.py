# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: store.py — oops/kb/store.py

"""SQLite persistence layer for the Odoo KB.

Two databases, same schema:
- kb_global.db   : Odoo community + enterprise, generated once per version.
- kb_project.db  : global + third-party + apik, scoped to a project.

Schema (v4)
-----------
meta          (key, value)
sources       (origin, path)
modules       (name, origin, depends)         -- depends is a JSON array string
symbols       (model, name, kind, origin, module, source_file, source_line,
               field_type, section)
field_refs    (model, field_name, module, kwarg, target_method)
model_origins (model, module, origin, role, model_type,
               inherit_json, inherits_json, source_file, source_line)
              role: 'create' | 'extend' | 'prototype'
              model_type: 'model' | 'transient' | 'abstract'
views         (xml_id, module, origin, name, model, view_type, inherit_id,
               mode, source_file, source_line, fields_json, buttons_json)
              mode: 'primary' | 'extension'
              view_type: NULL during pass 1, 'unresolved' if pass 2 fails
actions       (xml_id, module, origin, name, model, view_id, domain,
               source_file, source_line)
menus         (xml_id, module, origin, name, action, parent_id,
               source_file, source_line)

Indexes
-------
idx_symbols_lookup      on symbols(model, name, kind)
idx_symbols_module      on symbols(module)
idx_modules_origin      on modules(origin)
idx_field_refs_target   on field_refs(model, target_method)
idx_model_origins_model on model_origins(model)
idx_model_origins_role  on model_origins(model, role)
idx_views_model         on views(model)
idx_views_inherit       on views(inherit_id)
idx_views_module        on views(module)
idx_views_origin        on views(origin)
idx_actions_model       on actions(model)
idx_actions_module      on actions(module)
idx_menus_action        on menus(action)
idx_menus_parent        on menus(parent_id)
idx_menus_module        on menus(module)
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from oops.core.logger import log
from oops.core.models import Result
from oops.utils.compat import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Schema versioning
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 4  # added views/actions/menus tables

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

CREATE TABLE IF NOT EXISTS model_origins (
    model         TEXT    NOT NULL,
    module        TEXT    NOT NULL,
    origin        TEXT    NOT NULL,
    role          TEXT    NOT NULL,         -- 'create' | 'extend' | 'prototype'
    model_type    TEXT    NOT NULL DEFAULT 'model', -- 'model' | 'transient' | 'abstract'
    inherit_json  TEXT    NOT NULL DEFAULT '[]',
    inherits_json TEXT    NOT NULL DEFAULT '{}',
    source_file   TEXT    NOT NULL,
    source_line   INTEGER NOT NULL,
    PRIMARY KEY (model, module)
);
CREATE INDEX IF NOT EXISTS idx_model_origins_model ON model_origins (model);
CREATE INDEX IF NOT EXISTS idx_model_origins_role  ON model_origins (model, role);

CREATE TABLE IF NOT EXISTS views (
    xml_id       TEXT NOT NULL PRIMARY KEY,
    module       TEXT NOT NULL,
    origin       TEXT NOT NULL,
    name         TEXT,
    model        TEXT,
    view_type    TEXT,
    inherit_id   TEXT,
    mode         TEXT NOT NULL,
    source_file  TEXT NOT NULL,
    source_line  INTEGER NOT NULL,
    fields_json  TEXT NOT NULL DEFAULT '[]',
    buttons_json TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_views_model   ON views (model);
CREATE INDEX IF NOT EXISTS idx_views_inherit ON views (inherit_id);
CREATE INDEX IF NOT EXISTS idx_views_module  ON views (module);
CREATE INDEX IF NOT EXISTS idx_views_origin  ON views (origin);

CREATE TABLE IF NOT EXISTS actions (
    xml_id       TEXT NOT NULL PRIMARY KEY,
    module       TEXT NOT NULL,
    origin       TEXT NOT NULL,
    name         TEXT,
    model        TEXT,
    view_id      TEXT,
    domain       TEXT,
    source_file  TEXT NOT NULL,
    source_line  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_actions_model  ON actions (model);
CREATE INDEX IF NOT EXISTS idx_actions_module ON actions (module);

CREATE TABLE IF NOT EXISTS menus (
    xml_id       TEXT NOT NULL PRIMARY KEY,
    module       TEXT NOT NULL,
    origin       TEXT NOT NULL,
    name         TEXT,
    action       TEXT,
    parent_id    TEXT,
    source_file  TEXT NOT NULL,
    source_line  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_menus_action  ON menus (action);
CREATE INDEX IF NOT EXISTS idx_menus_parent  ON menus (parent_id);
CREATE INDEX IF NOT EXISTS idx_menus_module  ON menus (module);
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
) -> Result[dict]:
    """Write (or overwrite) a global KB database.

    Args:
        db_path:      destination .db file (created if absent).
        odoo_version: e.g. '17.0'.
        sources:      { origin: absolute_path_string }.
        scan_results: list of ScanResult dicts from scanner.scan_tier().
    """
    return _write_kb(
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
) -> Result[dict]:
    """Write (or overwrite) a project KB database.

    Args:
        db_path:      destination .db file.
        odoo_version: e.g. '17.0'.
        project:      project slug string.
        scope:        sorted list of module names in scope.
        sources:      { origin: absolute_path_string }.
        scan_results: list of ScanResult dicts (global already merged in by caller).
    """
    return _write_kb(
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
) -> Result[dict]:
    """Internal: write all KB data to db_path, replacing any previous content."""
    kb_result: "Result[dict]" = Result()
    con = _connect(db_path)
    try:
        with con:
            # Schema may have evolved: drop and re-create all data tables so column
            # additions always land on existing on-disk databases.
            for table in (
                "views",
                "actions",
                "menus",
                "field_refs",
                "symbols",
                "model_origins",
                "modules",
                "sources",
                "meta",
            ):
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
            for scan in scan_results:
                for mod_name, mod_data in scan.get("modules", {}).items():
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

                for sym in scan.get("symbols", []):
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

                for ref in scan.get("field_refs", []):
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

                for orig in scan.get("model_origins", []):
                    con.execute(
                        """
                        INSERT OR REPLACE INTO model_origins
                            (model, module, origin, role, model_type,
                             inherit_json, inherits_json, source_file, source_line)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            orig["model"],
                            orig["module"],
                            orig["origin"],
                            orig["role"],
                            orig.get("model_type", "model"),
                            orig.get("inherit_json", "[]"),
                            orig.get("inherits_json", "{}"),
                            orig["source_file"],
                            orig["source_line"],
                        ),
                    )

                for view in scan.get("views", []):
                    con.execute(
                        """
                        INSERT OR REPLACE INTO views
                            (xml_id, module, origin, name, model, view_type, inherit_id,
                             mode, source_file, source_line, fields_json, buttons_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            view["xml_id"],
                            view["module"],
                            view["origin"],
                            view.get("name"),
                            view.get("model"),
                            view.get("view_type"),
                            view.get("inherit_id"),
                            view["mode"],
                            view["source_file"],
                            view["source_line"],
                            view.get("fields_json", "[]"),
                            view.get("buttons_json", "[]"),
                        ),
                    )

                for action in scan.get("actions", []):
                    con.execute(
                        """
                        INSERT OR REPLACE INTO actions
                            (xml_id, module, origin, name, model, view_id, domain,
                             source_file, source_line)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            action["xml_id"],
                            action["module"],
                            action["origin"],
                            action.get("name"),
                            action.get("model"),
                            action.get("view_id"),
                            action.get("domain"),
                            action["source_file"],
                            action["source_line"],
                        ),
                    )

                for menu in scan.get("menus", []):
                    con.execute(
                        """
                        INSERT OR REPLACE INTO menus
                            (xml_id, module, origin, name, action, parent_id,
                             source_file, source_line)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            menu["xml_id"],
                            menu["module"],
                            menu["origin"],
                            menu.get("name"),
                            menu.get("action"),
                            menu.get("parent_id"),
                            menu["source_file"],
                            menu["source_line"],
                        ),
                    )
    except sqlite3.Error as exc:
        kb_result.add_error(f"KB write failed: {exc}")
        return kb_result

    con.close()
    stats = _get_stats(db_path)
    kb_result.merge(stats)
    kb_result.data = stats.data
    return kb_result


def _get_stats(db_path: Path) -> Result[dict]:
    result = Result()
    con = _connect(db_path)
    n_mod = con.execute("SELECT COUNT(*) FROM modules").fetchone()[0]
    n_sym = con.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
    n_fld = con.execute("SELECT COUNT(*) FROM symbols WHERE kind='field'").fetchone()[0]
    n_mth = con.execute("SELECT COUNT(*) FROM symbols WHERE kind='method'").fetchone()[0]
    n_refs = con.execute("SELECT COUNT(*) FROM field_refs").fetchone()[0]
    n_orig = con.execute("SELECT COUNT(*) FROM model_origins").fetchone()[0]
    n_views = con.execute("SELECT COUNT(*) FROM views").fetchone()[0]
    n_actions = con.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
    n_menus = con.execute("SELECT COUNT(*) FROM menus").fetchone()[0]
    con.close()
    log.debug(
        "KB written → %s  [%d modules | %d symbols: %d fields, %d methods | "
        "%d field_refs | %d model_origins | %d views | %d actions | %d menus]",
        db_path,
        n_mod,
        n_sym,
        n_fld,
        n_mth,
        n_refs,
        n_orig,
        n_views,
        n_actions,
        n_menus,
    )

    result.data = {
        "file": db_path,
        "modules": n_mod,
        "symbols": n_sym,
        "fields": n_fld,
        "methods": n_mth,
        "field_refs": n_refs,
        "model_origins": n_orig,
        "views": n_views,
        "actions": n_actions,
        "menus": n_menus,
    }

    return result


# ---------------------------------------------------------------------------
# Read helpers (used by refactor.py and resolve.py)
# ---------------------------------------------------------------------------


class KBReader:
    """Read-only interface to a KB SQLite database.

    Use as a context manager or call ``close()`` explicitly when done::

        with KBReader(Path(".oops-cache/kb_project.db")) as kb:
            entries = kb.get_symbol("sale.order", "action_confirm", "method")
            modules = kb.get_modules()
    """

    def __init__(self, db_path: Path) -> None:
        if not db_path.exists():
            raise FileNotFoundError(f"KB database not found: {db_path}")
        self._con = sqlite3.connect(str(db_path))
        self._con.row_factory = sqlite3.Row

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._con.close()

    def __enter__(self) -> "KBReader":
        """Return self for use as a context manager."""
        return self

    def __exit__(self, *_: Any) -> None:
        """Close the connection on context-manager exit."""
        self.close()

    # --- meta ---

    def get_meta(self) -> Dict[str, str]:
        """Return all meta key/value pairs.

        Returns:
            Dict mapping meta key to its string value.
        """
        rows = self._con.execute("SELECT key, value FROM meta").fetchall()
        return {r["key"]: r["value"] for r in rows}

    # --- modules ---

    def get_modules(self) -> Dict[str, Dict[str, Any]]:
        """Return all modules indexed by name.

        Returns:
            Mapping of module name to ``{"origin": str, "depends": [str, ...]}``.
        """
        rows = self._con.execute("SELECT name, origin, depends FROM modules").fetchall()
        return {
            r["name"]: {
                "origin": r["origin"],
                "depends": json.loads(r["depends"]),
            }
            for r in rows
        }

    def module_exists(self, name: str) -> bool:
        """Return True if the named module is present in the KB.

        Args:
            name: Module name to look up.

        Returns:
            True if the module exists, False otherwise.
        """
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
        """Return True if the symbol exists in any upstream module.

        Args:
            model: Dotted model name, e.g. ``'sale.order'``.
            name: Symbol name.
            kind: ``'field'`` or ``'method'``.

        Returns:
            True if at least one upstream entry matches, False otherwise.
        """
        row = self._con.execute(
            "SELECT 1 FROM symbols WHERE model=? AND name=? AND kind=?",
            (model, name, kind),
        ).fetchone()
        return row is not None

    def model_exists(self, model: str) -> bool:
        """Return True if any upstream module defines or extends this model.

        Args:
            model: Dotted model name, e.g. ``'sale.order'``.

        Returns:
            True if at least one symbol for the model exists, False otherwise.
        """
        row = self._con.execute("SELECT 1 FROM symbols WHERE model = ? LIMIT 1", (model,)).fetchone()
        return row is not None

    def get_model_origin(self, model: str, module: str) -> Optional[str]:
        """Return the role of ``module`` for ``model``, or None if absent.

        Args:
            model: Dotted model name.
            module: Module name.

        Returns:
            ``'create'``, ``'extend'``, ``'prototype'``, or ``None``.
        """
        row = self._con.execute(
            "SELECT role FROM model_origins WHERE model = ? AND module = ?",
            (model, module),
        ).fetchone()
        return row["role"] if row else None

    def is_model_creator(self, model: str, module: str) -> bool:
        """Return True if ``module`` is a creator (or prototype source) of ``model``.

        Falls back to True when neither ``module`` nor any other module has a
        ``model_origins`` creator entry for the model — safe assumption for modules
        that were not included in the KB scan.

        Args:
            model: Dotted model name.
            module: The module being analysed.

        Returns:
            True when this module created the model, False when it only extends it.
        """
        role = self.get_model_origin(model, module)
        if role is not None:
            return role in ("create", "prototype")
        row = self._con.execute(
            "SELECT 1 FROM model_origins WHERE model = ? AND role IN ('create', 'prototype') LIMIT 1",
            (model,),
        ).fetchone()
        return row is None

    def get_model_creators(self, model: str) -> List[Dict[str, Any]]:
        """Return all modules recorded as creators of ``model``.

        Args:
            model: Dotted model name.

        Returns:
            List of ``{"module", "origin", "source_file", "source_line"}`` dicts.
        """
        rows = self._con.execute(
            """
            SELECT module, origin, source_file, source_line
            FROM   model_origins
            WHERE  model = ? AND role IN ('create', 'prototype')
            ORDER  BY origin, module
            """,
            (model,),
        ).fetchall()
        return [dict(r) for r in rows]

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
        """Return all indexed source roots.

        Returns:
            Mapping of ``origin`` to absolute path string.
        """
        rows = self._con.execute("SELECT origin, path FROM sources").fetchall()
        return {r["origin"]: r["path"] for r in rows}

    # --- field_refs ---

    def get_field_refs_for_method(self, model: str, target_method: str) -> List[Dict[str, Any]]:
        """Return field references that target a specific method.

        Args:
            model: Dotted model name.
            target_method: Method name to look up.

        Returns:
            List of ``{"module": str, "field_name": str, "kwarg": str}`` dicts,
            sorted by module, kwarg, and field name.
        """
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

    # --- views / actions / menus ---

    def get_views(self) -> List[Dict[str, Any]]:
        """Return all indexed views.

        Returns:
            List of view dicts with all columns.
        """
        rows = self._con.execute(
            "SELECT xml_id, module, origin, name, model, view_type, inherit_id, "
            "mode, source_file, source_line, fields_json, buttons_json FROM views"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_view(self, xml_id: str) -> Optional[Dict[str, Any]]:
        """Return a single view by xml_id, or None if absent.

        Args:
            xml_id: Fully-qualified xml_id (e.g. ``'sale.view_order_form'``).

        Returns:
            Dict with all view columns, or None.
        """
        row = self._con.execute(
            "SELECT xml_id, module, origin, name, model, view_type, inherit_id, "
            "mode, source_file, source_line, fields_json, buttons_json FROM views "
            "WHERE xml_id = ?",
            (xml_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_actions(self) -> List[Dict[str, Any]]:
        """Return all indexed actions.

        Returns:
            List of action dicts with all columns.
        """
        rows = self._con.execute(
            "SELECT xml_id, module, origin, name, model, view_id, domain, source_file, source_line FROM actions"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_menus(self) -> List[Dict[str, Any]]:
        """Return all indexed menus.

        Returns:
            List of menu dicts with all columns.
        """
        rows = self._con.execute(
            "SELECT xml_id, module, origin, name, action, parent_id, source_file, source_line FROM menus"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_module_views(self, module: str) -> List[Dict[str, Any]]:
        """Return all views for the given module.

        Args:
            module: Module name to filter by.

        Returns:
            List of dicts with keys: xml_id, mode, view_type, inherit_id, source_file.
        """
        rows = self._con.execute(
            "SELECT xml_id, mode, view_type, inherit_id, source_file "
            "FROM views WHERE module = ?",
            (module,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_module_action_count(self, module: str) -> int:
        """Return the number of actions belonging to the given module.

        Args:
            module: Module name.

        Returns:
            Integer count.
        """
        return self._con.execute(
            "SELECT COUNT(*) FROM actions WHERE module = ?", (module,)
        ).fetchone()[0]

    def get_module_menu_count(self, module: str) -> int:
        """Return the number of menus belonging to the given module.

        Args:
            module: Module name.

        Returns:
            Integer count.
        """
        return self._con.execute(
            "SELECT COUNT(*) FROM menus WHERE module = ?", (module,)
        ).fetchone()[0]

    def get_field_refs_for_field(
        self, model: str, field_name: str, module: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return kwargs and target methods referenced by a field.

        Args:
            model: Dotted model name.
            field_name: Field name to look up.
            module: Optional module filter; when given, only entries from that
                module are returned.

        Returns:
            List of ``{"kwarg": str, "target_method": str, "module": str}`` dicts.
        """
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
