# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: store.py — oops_engine/store.py

"""Persistence layer for the Odoo KB, backend-agnostic (SQLite / Postgres).

Every data table is scoped by ``repo_id`` — a shared database can hold rows for
many independent repositories at once. Writes are ``DELETE WHERE repo_id=?`` +
insert (never a full drop/recreate), so writing one ``repo_id`` never touches
another's rows. The local CLI's project KB file holds two ``repo_id``s side by
side: the project's own (see ``oops_engine.identity.local_repo_id``) and the
Odoo-core rows copied in from the global KB (``"odoo-core-{version}"``) —
``KBReader`` is opened with both to reproduce the old "one merged file" query
results.

Dialect differences (connection, DDL, upsert syntax, placeholder style) live
entirely behind ``oops_engine.backends.Backend`` — this module never imports
``sqlite3``/``psycopg`` directly. Every function/class here accepts either a
bare ``Path`` (wrapped in ``SQLiteBackend`` automatically, preserving today's
local-CLI call sites unchanged) or an explicit ``Backend`` instance (what
``oops-engine-scan`` constructs for Postgres).

Schema (v10)
------------
repo_meta     (repo_id, key, value)          -- per-repo_id generated_at/schema_version/etc
sources       (repo_id, origin, path)
modules       (repo_id, name, origin, depends,        -- depends is a JSON array string
               application, app,                      -- application flag + owning app
               depth, load_index)                      -- NULL until compute_load_order() runs
symbols       (repo_id, model, name, kind, origin, module, source_file, source_line,
               source_end_line, field_type, section,
               import_index,                -- file position in __init__.py import order
               attrs_json,                  -- JSON object of full field attributes (fields only)
               has_super)                   -- 1 if method calls super().<attr>(), NULL for fields
              source_end_line: last source line of the definition (nullable —
              fields may omit it)
field_refs    (repo_id, model, field_name, module, kwarg, target_method)
model_origins (repo_id, model, module, origin, role, model_type,
               inherit_json, inherits_json, source_file, source_line,
               description,
               import_index)               -- file position in __init__.py import order
              role: 'create' | 'extend' | 'prototype'
              model_type: 'model' | 'transient' | 'abstract'
              description: literal _description string (nullable)
views         (repo_id, xml_id, module, origin, name, model, view_type, inherit_id,
               mode, source_file, source_line, source_end_line,
               fields_json, buttons_json)
              mode: 'primary' | 'extension'
              view_type: NULL during pass 1, 'unresolved' if pass 2 fails
              source_end_line: closing-element line (nullable)
actions       (repo_id, xml_id, module, origin, name, model, view_id, domain,
               source_file, source_line)
menus         (repo_id, xml_id, module, origin, name, action, parent_id,
               source_file, source_line)
analysis_cache (repo_id, module_name, content_fingerprint, kb_generated_at,
                payload_json, cached_at)
               -- cached ModuleSummary.to_cache_dict() JSON, keyed by a content
               -- fingerprint of the module's own source chained with its
               -- dependencies' fingerprints (oops_engine.fingerprint). NOT in
               -- _DATA_TABLES: a KB rebuild alone no longer invalidates it —
               -- only a change to the module's (or a dependency's) own files
               -- does. write_cached_analysis() prunes stale fingerprints for
               -- the same (repo_id, module_name) on each write, keeping one
               -- row per module.
loc_cache      (repo_id, addon_path, content_fingerprint, loc_json, cached_at)
               -- cached get_addon_loc() result, keyed the same way; written
               -- and pruned by write_cached_loc().

Indexes
-------
idx_symbols_lookup      on symbols(repo_id, model, name, kind)
idx_symbols_module      on symbols(repo_id, module)
idx_modules_origin      on modules(repo_id, origin)
idx_field_refs_target   on field_refs(repo_id, model, target_method)
idx_model_origins_model on model_origins(repo_id, model)
idx_model_origins_role  on model_origins(repo_id, model, role)
idx_views_model         on views(repo_id, model)
idx_views_inherit       on views(repo_id, inherit_id)
idx_views_module        on views(repo_id, module)
idx_views_origin        on views(repo_id, origin)
idx_actions_model       on actions(repo_id, model)
idx_actions_module      on actions(repo_id, module)
idx_menus_action        on menus(repo_id, action)
idx_menus_parent        on menus(repo_id, parent_id)
idx_menus_module        on menus(repo_id, module)
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

from oops.core.compat import Any, Dict, List, Optional, Sequence
from oops.core.logger import log
from oops.core.models import Result
from oops_engine.backends.base import Backend
from oops_engine.backends.sqlite import SQLiteBackend

# ---------------------------------------------------------------------------
# Schema versioning
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 10  # v10: every table scoped by repo_id; meta -> repo_meta

BackendOrPath = Union[Path, Backend]


def _resolve_backend(target: BackendOrPath) -> Backend:
    """Wrap a bare path in SQLiteBackend; pass an explicit Backend through."""
    if isinstance(target, (str, Path)):
        return SQLiteBackend(Path(target))
    return target


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

_DATA_TABLES = (
    "views",
    "actions",
    "menus",
    "field_refs",
    "symbols",
    "model_origins",
    "modules",
    "sources",
    "repo_meta",
    # analysis_cache/loc_cache are content-fingerprint-keyed, not kb_generated_at
    # -keyed — a KB rebuild alone must not invalidate them. See module docstring.
)

# (table, columns, conflict_columns) for the 7 tables scan results populate.
_UPSERT_SPECS = {
    "modules": (
        ("repo_id", "name", "origin", "depends", "application", "app", "depth", "load_index"),
        ("repo_id", "name"),
    ),
    "symbols": (
        (
            "repo_id", "model", "name", "kind", "origin", "module", "source_file", "source_line",
            "source_end_line", "field_type", "section", "import_index", "attrs_json", "has_super",
        ),
        ("repo_id", "model", "name", "kind", "module"),
    ),
    "field_refs": (
        ("repo_id", "model", "field_name", "module", "kwarg", "target_method"),
        ("repo_id", "model", "field_name", "module", "kwarg"),
    ),
    "model_origins": (
        (
            "repo_id", "model", "module", "origin", "role", "model_type",
            "inherit_json", "inherits_json", "source_file", "source_line",
            "description", "import_index",
        ),
        ("repo_id", "model", "module"),
    ),
    "views": (
        (
            "repo_id", "xml_id", "module", "origin", "name", "model", "view_type", "inherit_id",
            "mode", "source_file", "source_line", "source_end_line", "fields_json", "buttons_json",
        ),
        ("repo_id", "xml_id"),
    ),
    "actions": (
        (
            "repo_id", "xml_id", "module", "origin", "name", "model", "view_id", "domain",
            "source_file", "source_line",
        ),
        ("repo_id", "xml_id"),
    ),
    "menus": (
        (
            "repo_id", "xml_id", "module", "origin", "name", "action", "parent_id",
            "source_file", "source_line",
        ),
        ("repo_id", "xml_id"),
    ),
}


def _bool_or_none(value: Any) -> Optional[bool]:
    """Coerce a truthy/int/bool/None value to a real bool (or None) for the
    ``application``/``has_super`` BOOLEAN columns — SQLite accepts bools as
    0/1 transparently, but Postgres's BOOLEAN column rejects a bare int."""
    return None if value is None else bool(value)


def _row_values(table: str, repo_id: str, row: Dict[str, Any]) -> tuple:
    """Build a value tuple matching _UPSERT_SPECS[table]'s column order."""
    if table == "modules":
        name, data = row["_name"], row["_data"]
        return (repo_id, name, data["origin"], json.dumps(data["depends"]),
                _bool_or_none(data.get("application", 0)), data.get("app"),
                data.get("depth"), data.get("load_index"))
    if table == "symbols":
        return (
            repo_id, row["model"], row["name"], row["kind"], row["origin"], row["module"],
            row["source_file"], row["source_line"], row.get("source_end_line"),
            row.get("field_type"), row.get("section"), row.get("import_index"),
            row.get("attrs_json"), _bool_or_none(row.get("has_super")),
        )
    if table == "field_refs":
        return (repo_id, row["model"], row["field_name"], row["module"], row["kwarg"], row["target_method"])
    if table == "model_origins":
        return (
            repo_id, row["model"], row["module"], row["origin"], row["role"],
            row.get("model_type", "model"), row.get("inherit_json", "[]"), row.get("inherits_json", "{}"),
            row["source_file"], row["source_line"], row.get("description"), row.get("import_index"),
        )
    if table == "views":
        return (
            repo_id, row["xml_id"], row["module"], row["origin"], row.get("name"), row.get("model"),
            row.get("view_type"), row.get("inherit_id"), row["mode"], row["source_file"], row["source_line"],
            row.get("source_end_line"), row.get("fields_json", "[]"), row.get("buttons_json", "[]"),
        )
    if table == "actions":
        return (
            repo_id, row["xml_id"], row["module"], row["origin"], row.get("name"), row.get("model"),
            row.get("view_id"), row.get("domain"), row["source_file"], row["source_line"],
        )
    if table == "menus":
        return (
            repo_id, row["xml_id"], row["module"], row["origin"], row.get("name"), row.get("action"),
            row.get("parent_id"), row["source_file"], row["source_line"],
        )
    raise ValueError(f"Unknown upsert table: {table}")  # pragma: no cover — internal invariant


def write_kb(
    db_path: BackendOrPath,
    repo_id: str,
    odoo_version: str,
    scan_results: List[Dict[str, Any]],
    sources: Dict[str, str],
    *,
    project: Optional[str] = None,
    scope: Optional[List[str]] = None,
) -> Result[dict]:
    """Write (or overwrite) one ``repo_id``'s rows. Never touches other repo_ids' rows.

    Args:
        db_path:      destination — a bare path (SQLite, created if absent) or
            an explicit ``Backend`` instance (e.g. ``PostgresBackend``).
        repo_id:      identifies which repository these rows belong to. Every
            row written by this call carries this ``repo_id`` — a shared,
            multi-tenant database can hold many independent calls' rows in
            the same tables without collision.
        odoo_version: e.g. '17.0'.
        scan_results: list of ScanResult dicts from scanner.scan_tier()/scan_module().
        sources:      { origin: absolute_path_string }.
        project:      optional project slug string (local CLI use only).
        scope:        optional sorted list of module names in scope (local CLI use only).
    """
    backend = _resolve_backend(db_path)
    ph = backend.placeholder()
    kb_result: "Result[dict]" = Result()
    con = backend.connect()
    try:
        with con:
            cur = con.cursor()
            # Scope every write to repo_id: delete this repo's old rows, then
            # insert its new ones. Other repo_ids' rows are never touched.
            for table in _DATA_TABLES:
                cur.execute(f"DELETE FROM {table} WHERE repo_id = {ph}", (repo_id,))

            # --- repo_meta ---
            meta_rows = [
                (repo_id, "odoo_version", odoo_version),
                (repo_id, "schema_version", str(SCHEMA_VERSION)),
                (repo_id, "generated_at", datetime.now(timezone.utc).isoformat()),
            ]
            if project:
                meta_rows.append((repo_id, "project", project))
            if scope is not None:
                meta_rows.append((repo_id, "scope", json.dumps(scope)))
            cur.executemany(
                f"INSERT INTO repo_meta (repo_id, key, value) VALUES ({ph}, {ph}, {ph})", meta_rows
            )

            # --- sources ---
            cur.executemany(
                f"INSERT INTO sources (repo_id, origin, path) VALUES ({ph}, {ph}, {ph})",
                [(repo_id, origin, path) for origin, path in sources.items()],
            )

            # --- modules + symbols + field_refs + model_origins + views/actions/menus ---
            upsert_cache: Dict[str, str] = {}

            def _upsert(table: str, row: Dict[str, Any]) -> None:
                if table not in upsert_cache:
                    columns, conflict_columns = _UPSERT_SPECS[table]
                    upsert_cache[table] = backend.upsert_sql(table, columns, conflict_columns)
                cur.execute(upsert_cache[table], _row_values(table, repo_id, row))

            for scan in scan_results:
                for mod_name, mod_data in scan.get("modules", {}).items():
                    _upsert("modules", {"_name": mod_name, "_data": mod_data})
                for sym in scan.get("symbols", []):
                    _upsert("symbols", sym)
                for ref in scan.get("field_refs", []):
                    _upsert("field_refs", ref)
                for orig in scan.get("model_origins", []):
                    _upsert("model_origins", orig)
                for view in scan.get("views", []):
                    _upsert("views", view)
                for action in scan.get("actions", []):
                    _upsert("actions", action)
                for menu in scan.get("menus", []):
                    _upsert("menus", menu)
    except Exception as exc:  # noqa: BLE001 — dialect-specific DB errors vary; report, don't crash the caller
        kb_result.add_error(f"KB write failed: {exc}")
        return kb_result
    finally:
        con.close()

    stats = _get_stats(backend, repo_id)
    kb_result.merge(stats)
    kb_result.data = stats.data
    return kb_result


def update_module_load_order(
    db_path: BackendOrPath, repo_ids: Sequence[str], load_result: Dict[str, Any]
) -> None:
    """Stamp depth and load_index onto each module row after initial write.

    A module's row may belong to any of the given ``repo_ids`` (e.g. a local
    project KB holds both the project's own repo_id and the copied-in
    Odoo-core repo_id in the same file) — this updates whichever one actually
    has that module's row.

    Args:
        db_path: Path or Backend for the KB database.
        repo_ids: The repo_ids whose module rows may be updated.
        load_result: dict mapping module_name → (depth, load_index).
    """
    backend = _resolve_backend(db_path)
    ph = backend.placeholder()
    placeholders = ",".join(ph for _ in repo_ids)
    con = backend.connect()
    try:
        with con:
            cur = con.cursor()
            cur.executemany(
                f"UPDATE modules SET depth={ph}, load_index={ph} "
                f"WHERE repo_id IN ({placeholders}) AND name={ph}",
                [(depth, load_index, *repo_ids, name) for name, (depth, load_index) in load_result.items()],
            )
    finally:
        con.close()


def _get_stats(backend_or_path: BackendOrPath, repo_id: str) -> Result[dict]:
    backend = _resolve_backend(backend_or_path)
    ph = backend.placeholder()
    result = Result()
    con = backend.connect()
    try:
        cur = con.cursor()

        def _count(sql: str) -> int:
            cur.execute(sql, (repo_id,))
            row = cur.fetchone()
            return row[0] if not isinstance(row, dict) else next(iter(row.values()))

        n_mod = _count(f"SELECT COUNT(*) FROM modules WHERE repo_id={ph}")
        n_sym = _count(f"SELECT COUNT(*) FROM symbols WHERE repo_id={ph}")
        n_fld = _count(f"SELECT COUNT(*) FROM symbols WHERE repo_id={ph} AND kind='field'")
        n_mth = _count(f"SELECT COUNT(*) FROM symbols WHERE repo_id={ph} AND kind='method'")
        n_refs = _count(f"SELECT COUNT(*) FROM field_refs WHERE repo_id={ph}")
        n_orig = _count(f"SELECT COUNT(*) FROM model_origins WHERE repo_id={ph}")
        n_views = _count(f"SELECT COUNT(*) FROM views WHERE repo_id={ph}")
        n_actions = _count(f"SELECT COUNT(*) FROM actions WHERE repo_id={ph}")
        n_menus = _count(f"SELECT COUNT(*) FROM menus WHERE repo_id={ph}")
    finally:
        con.close()

    log.debug(
        "KB written → %s [repo_id=%s]  [%d modules | %d symbols: %d fields, %d methods | "
        "%d field_refs | %d model_origins | %d views | %d actions | %d menus]",
        getattr(backend, "db_path", backend),
        repo_id,
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
        "file": getattr(backend, "db_path", None),
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


def discover_repo_ids(db_path: BackendOrPath) -> List[str]:
    """Return every distinct repo_id present in a KB file.

    For call sites that accept an arbitrary pre-built KB path (e.g. `oops
    refactor --kb <path>`) and have no other way to know which repo_id(s) it
    holds.
    """
    backend = _resolve_backend(db_path)
    con = backend.connect()
    try:
        cur = con.cursor()
        cur.execute("SELECT DISTINCT repo_id FROM repo_meta")
        rows = cur.fetchall()
        return [row[0] if not isinstance(row, dict) else row["repo_id"] for row in rows]
    finally:
        con.close()


def write_cached_analysis(
    db_path: BackendOrPath,
    repo_id: str,
    module_name: str,
    content_fingerprint: str,
    kb_generated_at: str,
    payload: Dict[str, Any],
) -> None:
    """Cache one module's computed analysis (a `ModuleSummary.to_cache_dict()` payload).

    Args:
        db_path:              destination — a bare path or an explicit Backend.
        repo_id:              repo_id this analysis was computed for.
        module_name:          module technical name.
        content_fingerprint:  chained content fingerprint (own source + resolved
            dependencies', see `oops_engine.fingerprint`) — the cache key. A
            change to the module's own files or a dependency's produces a
            different fingerprint, so the previous row is a guaranteed miss.
        kb_generated_at:      the KB's `generated_at` meta value at analysis
            time — kept as a plain (non-key) column for observability.
        payload:               JSON-safe dict, e.g. from `ModuleSummary.to_cache_dict()`.
    """
    backend = _resolve_backend(db_path)
    ph = backend.placeholder()
    upsert = backend.upsert_sql(
        "analysis_cache",
        ("repo_id", "module_name", "content_fingerprint", "kb_generated_at", "payload_json", "cached_at"),
        ("repo_id", "module_name", "content_fingerprint"),
    )
    con = backend.connect()
    try:
        with con:
            cur = con.cursor()
            # content_fingerprint is no longer invalidated by a KB rebuild, so
            # prune this module's other fingerprints or rows accumulate
            # unbounded across edits — keep only the one just written.
            cur.execute(
                f"DELETE FROM analysis_cache WHERE repo_id = {ph} AND module_name = {ph} "
                f"AND content_fingerprint != {ph}",
                (repo_id, module_name, content_fingerprint),
            )
            cur.execute(
                upsert,
                (
                    repo_id,
                    module_name,
                    content_fingerprint,
                    kb_generated_at,
                    json.dumps(payload),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
    finally:
        con.close()


def write_cached_loc(
    db_path: BackendOrPath,
    repo_id: str,
    addon_path: str,
    content_fingerprint: str,
    loc: Dict[str, Any],
) -> None:
    """Cache one addon's computed LOC breakdown (a `LocStats`-shaped dict).

    Args:
        db_path:              destination — a bare path or an explicit Backend.
        repo_id:              repo_id this addon was scanned under.
        addon_path:            resolved absolute addon directory path — stable
            identity for an addon regardless of which submodule/symlink tier
            it's found through.
        content_fingerprint:  the addon directory's content fingerprint (see
            `oops_engine.fingerprint`) — the cache key.
        loc:                   JSON-safe dict, e.g. `dataclasses.asdict(LocStats(...))`.
    """
    backend = _resolve_backend(db_path)
    ph = backend.placeholder()
    upsert = backend.upsert_sql(
        "loc_cache",
        ("repo_id", "addon_path", "content_fingerprint", "loc_json", "cached_at"),
        ("repo_id", "addon_path", "content_fingerprint"),
    )
    con = backend.connect()
    try:
        with con:
            cur = con.cursor()
            # Same prune rationale as write_cached_analysis: keep one row per addon.
            cur.execute(
                f"DELETE FROM loc_cache WHERE repo_id = {ph} AND addon_path = {ph} "
                f"AND content_fingerprint != {ph}",
                (repo_id, addon_path, content_fingerprint),
            )
            cur.execute(
                upsert,
                (repo_id, addon_path, content_fingerprint, json.dumps(loc), datetime.now(timezone.utc).isoformat()),
            )
    finally:
        con.close()


def get_cached_loc(
    db_path: BackendOrPath,
    repo_id: str,
    addon_path: str,
    content_fingerprint: str,
) -> Optional[Dict[str, Any]]:
    """Return a cached LOC breakdown dict, or None on a cache miss.

    Standalone (not `KBReader`-bound) — unlike `get_cached_analysis`, this is
    called from `oops addons list`, which must work against a project with no
    prior KB build. `SQLiteBackend.connect()` creates the file (and applies
    the DDL) if it doesn't exist yet; `KBReader` requires it to already exist.

    Args:
        db_path:              a bare path or an explicit Backend.
        repo_id:               repo_id this addon was scanned under.
        addon_path:            resolved absolute addon directory path.
        content_fingerprint:  the addon directory's current content
            fingerprint (see `oops_engine.fingerprint`) — the cache key.
    """
    backend = _resolve_backend(db_path)
    ph = backend.placeholder()
    con = backend.connect()
    try:
        cur = con.cursor()
        cur.execute(
            f"SELECT loc_json FROM loc_cache WHERE repo_id = {ph} AND addon_path = {ph} "
            f"AND content_fingerprint = {ph}",
            (repo_id, addon_path, content_fingerprint),
        )
        row = cur.fetchone()
    finally:
        con.close()
    return json.loads(row["loc_json"]) if row else None


# ---------------------------------------------------------------------------
# Read helpers (used by refactor.py and resolve.py)
# ---------------------------------------------------------------------------


class KBReader:
    """Read-only interface to a KB database, scoped to a list of repo_ids.

    Every data-table read searches across all given ``repo_ids`` (so a
    project's own rows and separately-scanned Odoo-core rows can be queried
    together without a file-level merge step). ``get_meta()`` is the one
    exception — it answers for a single repo_id (defaulting to the first one
    given), since meta keys like ``generated_at`` mean different things for
    different repo_ids sharing the same file.

    Use as a context manager or call ``close()`` explicitly when done::

        with KBReader(Path(".oops-cache/kb.db"), repo_ids=["my-project"]) as kb:
            entries = kb.get_symbol("sale.order", "action_confirm", "method")
            modules = kb.get_modules()

    ``db_path`` may also be an explicit ``Backend`` instance (e.g.
    ``PostgresBackend``) instead of a bare path.
    """

    def __init__(self, db_path: BackendOrPath, repo_ids: Sequence[str]) -> None:
        if isinstance(db_path, (str, Path)):
            sqlite_backend = SQLiteBackend(Path(db_path))
            if not sqlite_backend.exists():
                raise FileNotFoundError(f"KB database not found: {db_path}")
            backend: Backend = sqlite_backend
        else:
            backend = db_path
        if not repo_ids:
            raise ValueError("KBReader requires at least one repo_id")
        self._repo_ids: List[str] = list(repo_ids)
        self._backend = backend
        self._con = backend.connect()
        self._ph = backend.placeholder()

    def _placeholders(self) -> str:
        return ",".join(self._ph for _ in self._repo_ids)

    def _exec(self, sql: str, params: "Sequence[Any]" = ()) -> Any:
        """Execute a ``?``-placeholder query, translated to this backend's dialect."""
        if self._ph != "?":
            sql = sql.replace("?", self._ph)
        cur = self._con.cursor()
        cur.execute(sql, tuple(params))
        return cur

    def close(self) -> None:
        """Close the underlying DB connection."""
        self._con.close()

    def __enter__(self) -> "KBReader":
        """Return self for use as a context manager."""
        return self

    def __exit__(self, *_: Any) -> None:
        """Close the connection on context-manager exit."""
        self.close()

    # --- meta ---

    def get_meta(self, repo_id: Optional[str] = None) -> Dict[str, str]:
        """Return meta key/value pairs for one repo_id.

        Args:
            repo_id: Which repo_id's meta to read. Defaults to the first
                repo_id this reader was opened with — by convention, the
                "primary"/local one when reading a local project KB.

        Returns:
            Dict mapping meta key to its string value.
        """
        rid = repo_id if repo_id is not None else self._repo_ids[0]
        rows = self._exec("SELECT key, value FROM repo_meta WHERE repo_id = ?", (rid,)).fetchall()
        return {r["key"]: r["value"] for r in rows}

    def get_cached_analysis(self, module_name: str, content_fingerprint: str) -> Optional[Dict[str, Any]]:
        """Return a cached `ModuleSummary.to_cache_dict()` payload, or None on a cache miss.

        Args:
            module_name:          module technical name.
            content_fingerprint:  the module's current chained content
                fingerprint (see `oops_engine.fingerprint`) — the cache key,
                so an edit to the module's own files or a dependency's is a
                guaranteed miss, independent of KB rebuilds.
        """
        row = self._exec(
            f"""
            SELECT payload_json FROM analysis_cache
            WHERE repo_id IN ({self._placeholders()}) AND module_name = ? AND content_fingerprint = ?
            """,
            (*self._repo_ids, module_name, content_fingerprint),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    # --- modules ---

    def get_modules(self) -> Dict[str, Dict[str, Any]]:
        """Return all modules indexed by name, across every configured repo_id.

        Returns:
            Mapping of module name to ``{"origin": str, "depends": [str, ...],
            "application": bool, "app": Optional[str]}``.
        """
        rows = self._exec(
            f"SELECT name, origin, depends, application, app FROM modules WHERE repo_id IN ({self._placeholders()})",
            self._repo_ids,
        ).fetchall()
        return {
            r["name"]: {
                "origin": r["origin"],
                "depends": json.loads(r["depends"]),
                "application": bool(r["application"]),
                "app": r["app"],
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
        row = self._exec(
            f"SELECT 1 FROM modules WHERE repo_id IN ({self._placeholders()}) AND name = ?",
            (*self._repo_ids, name),
        ).fetchone()
        return row is not None

    def get_module_app(self, module: str) -> Optional[str]:
        """Return the owning application for a module, or None if none.

        Args:
            module: Module technical name.

        Returns:
            Owning app technical name, or None.
        """
        row = self._exec(
            f"SELECT app FROM modules WHERE repo_id IN ({self._placeholders()}) AND name = ?",
            (*self._repo_ids, module),
        ).fetchone()
        return row["app"] if row else None

    def is_application(self, module: str) -> bool:
        """Return True if the module is itself an Odoo application.

        Args:
            module: Module technical name.

        Returns:
            True if application=1 in the KB, False otherwise.
        """
        row = self._exec(
            f"SELECT application FROM modules WHERE repo_id IN ({self._placeholders()}) AND name = ?",
            (*self._repo_ids, module),
        ).fetchone()
        return bool(row["application"]) if row else False

    def get_model_inherits(self, model: str) -> List[str]:
        """Return the union of _inherits parent model names across all model_origins rows.

        Args:
            model: Dotted model name.

        Returns:
            Sorted list of parent model names from _inherits declarations.
        """
        rows = self._exec(
            f"SELECT inherits_json FROM model_origins WHERE repo_id IN ({self._placeholders()}) AND model = ?",
            (*self._repo_ids, model),
        ).fetchall()
        parents: set = set()
        for r in rows:
            try:
                d = json.loads(r["inherits_json"] or "{}")
                parents.update(d.keys())
            except (ValueError, TypeError):
                pass
        return sorted(parents)

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
            source_end_line, field_type, section. Empty list if symbol is not found.
        """
        rows = self._exec(
            f"""
            SELECT origin, module, source_file, source_line, source_end_line,
                   field_type, section, has_super
            FROM   symbols
            WHERE  repo_id IN ({self._placeholders()}) AND model = ? AND name = ? AND kind = ?
            ORDER  BY origin  -- stable ordering; resolve.py re-sorts by depends
            """,
            (*self._repo_ids, model, name, kind),
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
        row = self._exec(
            f"SELECT 1 FROM symbols WHERE repo_id IN ({self._placeholders()}) AND model=? AND name=? AND kind=?",
            (*self._repo_ids, model, name, kind),
        ).fetchone()
        return row is not None

    def model_exists(self, model: str) -> bool:
        """Return True if any upstream module defines or extends this model.

        Args:
            model: Dotted model name, e.g. ``'sale.order'``.

        Returns:
            True if at least one symbol for the model exists, False otherwise.
        """
        row = self._exec(
            f"SELECT 1 FROM symbols WHERE repo_id IN ({self._placeholders()}) AND model = ? LIMIT 1",
            (*self._repo_ids, model),
        ).fetchone()
        return row is not None

    def get_model_origin(self, model: str, module: str) -> Optional[str]:
        """Return the role of ``module`` for ``model``, or None if absent.

        Args:
            model: Dotted model name.
            module: Module name.

        Returns:
            ``'create'``, ``'extend'``, ``'prototype'``, or ``None``.
        """
        row = self._exec(
            f"SELECT role FROM model_origins WHERE repo_id IN ({self._placeholders()}) AND model = ? AND module = ?",
            (*self._repo_ids, model, module),
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
        row = self._exec(
            f"""SELECT 1 FROM model_origins
            WHERE repo_id IN ({self._placeholders()}) AND model = ? AND role IN ('create', 'prototype') LIMIT 1""",
            (*self._repo_ids, model),
        ).fetchone()
        return row is None

    def get_model_creators(
        self, model: str, by_load_index: bool = False
    ) -> List[Dict[str, Any]]:
        """Return all modules recorded as creators of ``model``.

        Args:
            model: Dotted model name.
            by_load_index: When True, order by load_index ASC (earliest-loaded first)
                instead of the default ``origin, module`` alphabetical order.

        Returns:
            List of ``{"module", "origin", "source_file", "source_line",
            "description"}`` dicts.
        """
        placeholders = self._placeholders()
        if by_load_index:
            rows = self._exec(
                f"""
                SELECT mo.module, mo.origin, mo.source_file, mo.source_line, mo.description
                FROM   model_origins mo
                LEFT JOIN modules m ON mo.module = m.name AND mo.repo_id = m.repo_id
                WHERE  mo.repo_id IN ({placeholders}) AND mo.model = ? AND mo.role IN ('create', 'prototype')
                ORDER  BY m.load_index ASC NULLS LAST, mo.module
                """,
                (*self._repo_ids, model),
            ).fetchall()
        else:
            rows = self._exec(
                f"""
                SELECT module, origin, source_file, source_line, description
                FROM   model_origins
                WHERE  repo_id IN ({placeholders}) AND model = ? AND role IN ('create', 'prototype')
                ORDER  BY origin, module
                """,
                (*self._repo_ids, model),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_model_description(self, model: str) -> Optional[str]:
        """Return the _description of the first creator/prototype row, or None."""
        row = self._exec(
            f"""SELECT description FROM model_origins
            WHERE repo_id IN ({self._placeholders()}) AND model = ? AND role IN ('create','prototype')
                AND description IS NOT NULL
            ORDER BY origin, module LIMIT 1""",
            (*self._repo_ids, model),
        ).fetchone()
        return row["description"] if row else None

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
        placeholders = self._placeholders()
        if kind:
            rows = self._exec(
                f"""
                SELECT name, kind, origin, module, source_file, source_line,
                       source_end_line, field_type, section
                FROM   symbols
                WHERE  repo_id IN ({placeholders}) AND model = ? AND kind = ?
                ORDER  BY name
                """,
                (*self._repo_ids, model, kind),
            ).fetchall()
        else:
            rows = self._exec(
                f"""
                SELECT name, kind, origin, module, source_file, source_line,
                       source_end_line, field_type, section
                FROM   symbols
                WHERE  repo_id IN ({placeholders}) AND model = ?
                ORDER  BY kind, name
                """,
                (*self._repo_ids, model),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_sources(self) -> Dict[str, str]:
        """Return all indexed source roots, across every configured repo_id.

        Returns:
            Mapping of ``origin`` to absolute path string.
        """
        rows = self._exec(
            f"SELECT origin, path FROM sources WHERE repo_id IN ({self._placeholders()})",
            self._repo_ids,
        ).fetchall()
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
        rows = self._exec(
            f"""
            SELECT module, field_name, kwarg
            FROM   field_refs
            WHERE  repo_id IN ({self._placeholders()}) AND model = ? AND target_method = ?
            ORDER  BY module, kwarg, field_name
            """,
            (*self._repo_ids, model, target_method),
        ).fetchall()
        return [dict(r) for r in rows]

    # --- views / actions / menus ---

    def get_views(self) -> List[Dict[str, Any]]:
        """Return all indexed views, across every configured repo_id.

        Returns:
            List of view dicts with all columns.
        """
        rows = self._exec(
            f"SELECT xml_id, module, origin, name, model, view_type, inherit_id, "
            f"mode, source_file, source_line, source_end_line, fields_json, buttons_json FROM views "
            f"WHERE repo_id IN ({self._placeholders()})",
            self._repo_ids,
        ).fetchall()
        return [dict(r) for r in rows]

    def get_view(self, xml_id: str) -> Optional[Dict[str, Any]]:
        """Return a single view by xml_id, or None if absent.

        Args:
            xml_id: Fully-qualified xml_id (e.g. ``'sale.view_order_form'``).

        Returns:
            Dict with all view columns, or None.
        """
        row = self._exec(
            f"SELECT xml_id, module, origin, name, model, view_type, inherit_id, "
            f"mode, source_file, source_line, source_end_line, fields_json, buttons_json FROM views "
            f"WHERE repo_id IN ({self._placeholders()}) AND xml_id = ?",
            (*self._repo_ids, xml_id),
        ).fetchone()
        return dict(row) if row else None

    def get_actions(self) -> List[Dict[str, Any]]:
        """Return all indexed actions, across every configured repo_id.

        Returns:
            List of action dicts with all columns.
        """
        rows = self._exec(
            f"SELECT xml_id, module, origin, name, model, view_id, domain, source_file, source_line FROM actions "
            f"WHERE repo_id IN ({self._placeholders()})",
            self._repo_ids,
        ).fetchall()
        return [dict(r) for r in rows]

    def get_menus(self) -> List[Dict[str, Any]]:
        """Return all indexed menus, across every configured repo_id.

        Returns:
            List of menu dicts with all columns.
        """
        rows = self._exec(
            f"SELECT xml_id, module, origin, name, action, parent_id, source_file, source_line FROM menus "
            f"WHERE repo_id IN ({self._placeholders()})",
            self._repo_ids,
        ).fetchall()
        return [dict(r) for r in rows]

    def get_module_views(self, module: str) -> List[Dict[str, Any]]:
        """Return all views for the given module.

        Args:
            module: Module name to filter by.

        Returns:
            List of dicts with all view columns.
        """
        rows = self._exec(
            f"SELECT xml_id, module, origin, name, model, view_type, inherit_id, "
            f"mode, source_file, source_line, source_end_line, fields_json, buttons_json "
            f"FROM views WHERE repo_id IN ({self._placeholders()}) AND module = ?",
            (*self._repo_ids, module),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_module_action_count(self, module: str) -> int:
        """Return the number of actions belonging to the given module.

        Args:
            module: Module name.

        Returns:
            Integer count.
        """
        row = self._exec(
            f"SELECT COUNT(*) AS n FROM actions WHERE repo_id IN ({self._placeholders()}) AND module = ?",
            (*self._repo_ids, module),
        ).fetchone()
        return row["n"]

    def get_module_menu_count(self, module: str) -> int:
        """Return the number of menus belonging to the given module.

        Args:
            module: Module name.

        Returns:
            Integer count.
        """
        row = self._exec(
            f"SELECT COUNT(*) AS n FROM menus WHERE repo_id IN ({self._placeholders()}) AND module = ?",
            (*self._repo_ids, module),
        ).fetchone()
        return row["n"]

    def get_modules_with_depends(self) -> Dict[str, List[str]]:
        """Return all modules and their dependency lists.

        Returns:
            Mapping of module name to list of declared depends.
        """
        rows = self._exec(
            f"SELECT name, depends FROM modules WHERE repo_id IN ({self._placeholders()})",
            self._repo_ids,
        ).fetchall()
        return {r["name"]: json.loads(r["depends"]) for r in rows}

    def get_module_load_order(self) -> Dict[str, tuple]:
        """Return {module_name: (depth, load_index)} from persisted columns.

        Returns:
            Mapping of module name to (depth, load_index); both None when never stamped.
        """
        rows = self._exec(
            f"SELECT name, depth, load_index FROM modules WHERE repo_id IN ({self._placeholders()})",
            self._repo_ids,
        ).fetchall()
        return {r["name"]: (r["depth"], r["load_index"]) for r in rows}

    def get_model_origins_with_order(self, model: str) -> List[Dict[str, Any]]:
        """Return all model_origins rows for a model, joined with module load_index.

        Args:
            model: Dotted model name.

        Returns:
            List of dicts with keys: model, module, origin, role, inherit_json,
            inherits_json, source_file, source_line, import_index, load_index.
        """
        rows = self._exec(
            f"""
            SELECT mo.model, mo.module, mo.origin, mo.role,
                   mo.inherit_json, mo.inherits_json,
                   mo.source_file, mo.source_line,
                   mo.import_index,
                   m.load_index
            FROM model_origins mo
            LEFT JOIN modules m ON mo.module = m.name AND mo.repo_id = m.repo_id
            WHERE mo.repo_id IN ({self._placeholders()}) AND mo.model = ?
            """,
            (*self._repo_ids, model),
        ).fetchall()
        cols = [
            "model", "module", "origin", "role", "inherit_json", "inherits_json",
            "source_file", "source_line", "import_index", "load_index",
        ]
        return [dict(zip(cols, tuple(dict(r).get(c) for c in cols))) for r in rows]

    def get_symbols_by_module_model(self, module: str, model: str) -> List[Dict[str, Any]]:
        """Return all symbols for a given module+model combination.

        Args:
            module: Module name.
            model: Dotted model name.

        Returns:
            List of symbol dicts with name and kind.
        """
        rows = self._exec(
            f"SELECT name, kind FROM symbols WHERE repo_id IN ({self._placeholders()}) AND module=? AND model=?",
            (*self._repo_ids, module, model),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_field_attrs(self, model: str, field_name: str) -> List[Dict[str, Any]]:
        """Return per-layer field attributes for a given model+field.

        Args:
            model: Dotted model name.
            field_name: Field name.

        Returns:
            List of dicts with module, attrs_json, source_file, source_line,
            load_index, import_index, and parsed attrs dict.
        """
        rows = self._exec(
            f"""
            SELECT s.module, s.attrs_json, s.source_file, s.source_line,
                   m.load_index, s.import_index
            FROM symbols s
            LEFT JOIN modules m ON s.module = m.name AND s.repo_id = m.repo_id
            WHERE s.repo_id IN ({self._placeholders()}) AND s.model=? AND s.name=? AND s.kind='field'
            """,
            (*self._repo_ids, model, field_name),
        ).fetchall()
        cols = ["module", "attrs_json", "source_file", "source_line", "load_index", "import_index"]
        result = []
        for r in rows:
            rd = dict(r)
            row = {c: rd.get(c) for c in cols}
            row["attrs"] = json.loads(row["attrs_json"]) if row["attrs_json"] else {}
            result.append(row)
        return result

    def get_method_layers(self, model: str, method_name: str) -> List[Dict[str, Any]]:
        """Return per-layer method info for a given model+method.

        Args:
            model: Dotted model name.
            method_name: Method name.

        Returns:
            List of dicts with module, origin, source_file, source_line, section,
            has_super, load_index, import_index. Unsorted — caller must sort.
        """
        rows = self._exec(
            f"""
            SELECT s.module, s.origin, s.source_file, s.source_line, s.source_end_line,
                   s.section, s.has_super, m.load_index, s.import_index
            FROM symbols s
            LEFT JOIN modules m ON s.module = m.name AND s.repo_id = m.repo_id
            WHERE s.repo_id IN ({self._placeholders()}) AND s.model=? AND s.name=? AND s.kind='method'
            """,
            (*self._repo_ids, model, method_name),
        ).fetchall()
        cols = ["module", "origin", "source_file", "source_line", "source_end_line",
                "section", "has_super", "load_index", "import_index"]
        return [{c: dict(r).get(c) for c in cols} for r in rows]

    def get_method_layers_bulk(
        self, models: List[str]
    ) -> "Dict[tuple, List[Dict[str, Any]]]":
        """Fetch all method layers for a list of models in a single query.

        Args:
            models: List of dotted model names.

        Returns:
            Dict keyed by ``(model, method_name)`` → list of layer dicts.
            Each layer dict has the same shape as ``get_method_layers`` results.
        """
        if not models:
            return {}
        model_placeholders = ",".join(self._ph for _ in models)
        rows = self._exec(
            f"""
            SELECT s.model, s.name, s.module, s.origin, s.source_file, s.source_line,
                   s.source_end_line, s.section, s.has_super, m.load_index, s.import_index
            FROM symbols s
            LEFT JOIN modules m ON s.module = m.name AND s.repo_id = m.repo_id
            WHERE s.repo_id IN ({self._placeholders()}) AND s.kind='method' AND s.model IN ({model_placeholders})
            """,
            (*self._repo_ids, *models),
        ).fetchall()
        cols = ["model", "name", "module", "origin", "source_file", "source_line",
                "source_end_line", "section", "has_super", "load_index", "import_index"]
        result: Dict[tuple, List[Dict[str, Any]]] = {}
        for r in rows:
            row = {c: dict(r).get(c) for c in cols}
            key = (row.pop("model"), row.pop("name"))
            result.setdefault(key, []).append(row)
        return result

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
        placeholders = self._placeholders()
        if module is None:
            rows = self._exec(
                f"SELECT kwarg, target_method, module FROM field_refs "
                f"WHERE repo_id IN ({placeholders}) AND model=? AND field_name=? ORDER BY module, kwarg",
                (*self._repo_ids, model, field_name),
            ).fetchall()
        else:
            rows = self._exec(
                f"SELECT kwarg, target_method, module FROM field_refs "
                f"WHERE repo_id IN ({placeholders}) AND model=? AND field_name=? AND module=? ORDER BY kwarg",
                (*self._repo_ids, model, field_name, module),
            ).fetchall()
        return [dict(r) for r in rows]
