# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_oops_engine_backends.py — tests/test_oops_engine_backends.py

"""Dual-backend round-trip: the same write_kb/KBReader code path against both
SQLiteBackend (always) and PostgresBackend (only when a live Postgres is
reachable — set OOPS_TEST_POSTGRES_DSN, or run the default
``postgresql://postgres:test@localhost:5433/oops_test`` used in development;
skipped otherwise, e.g. in CI environments with no Postgres available).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest
from oops_engine.backends.sqlite import SQLiteBackend
from oops_engine.store import KBReader, write_cached_analysis, write_kb

_DEFAULT_TEST_DSN = "postgresql://postgres:test@localhost:5433/oops_test"


def _make_scan(module_name: str, model: str = "res.partner") -> dict:
    return {
        "modules": {module_name: {"origin": "custom", "depends": []}},
        "symbols": [
            {
                "model": model,
                "name": "name",
                "kind": "field",
                "origin": "custom",
                "module": module_name,
                "source_file": f"{module_name}/models/x.py",
                "source_line": 10,
                "has_super": None,
            }
        ],
        "field_refs": [],
        "model_origins": [],
        "views": [],
        "actions": [],
        "menus": [],
    }


def _postgres_backend():
    """Return a live PostgresBackend, or None if psycopg/a server isn't available."""
    try:
        import psycopg  # noqa: F401
    except ImportError:
        return None

    from oops_engine.backends.postgres import PostgresBackend

    dsn = os.environ.get("OOPS_TEST_POSTGRES_DSN", _DEFAULT_TEST_DSN)
    backend = PostgresBackend(dsn)
    try:
        con = backend.connect()
    except Exception:  # noqa: BLE001 — any connection failure means "skip"
        return None
    with con.cursor() as cur:
        for table in (
            "views", "actions", "menus", "field_refs", "symbols",
            "model_origins", "modules", "sources", "repo_meta",
        ):
            cur.execute(f"DELETE FROM {table}")
    con.commit()
    con.close()
    return backend


def _round_trip(backend) -> None:
    """The same repo_id-isolation exercise, run against whichever backend."""
    write_kb(
        backend, "a", "17.0", [_make_scan("module_a")], sources={"custom": "/repo-a"},
    )
    write_kb(
        backend, "b", "17.0", [_make_scan("module_b")], sources={"custom": "/repo-b"},
    )

    with KBReader(backend, repo_ids=["a"]) as kb:
        assert set(kb.get_modules()) == {"module_a"}
    with KBReader(backend, repo_ids=["b"]) as kb:
        assert set(kb.get_modules()) == {"module_b"}
    with KBReader(backend, repo_ids=["a", "b"]) as kb:
        assert set(kb.get_modules()) == {"module_a", "module_b"}
        entries = kb.get_symbol("res.partner", "name", "field")
        assert {e["module"] for e in entries} == {"module_a", "module_b"}

    # Re-writing "a" with an empty scan must not touch "b"'s rows.
    write_kb(backend, "a", "17.0", [], sources={})
    with KBReader(backend, repo_ids=["a"]) as kb:
        assert kb.get_modules() == {}
    with KBReader(backend, repo_ids=["b"]) as kb:
        assert "module_b" in kb.get_modules()


class TestDualBackendRoundTrip:
    def test_sqlite_backend(self, tmp_path: Path) -> None:
        backend = SQLiteBackend(tmp_path / "kb.db")
        _round_trip(backend)

    def test_postgres_backend(self) -> None:
        backend = _postgres_backend()
        if backend is None:
            pytest.skip("No live Postgres reachable (set OOPS_TEST_POSTGRES_DSN) — skipping Postgres backend test")
        _round_trip(backend)


class TestLegacySchemaMigration:
    """A KB file written by a pre-v10 `oops` release has `modules` etc. without
    a `repo_id` column. `CREATE TABLE IF NOT EXISTS` is a no-op on a table that
    already exists, so opening such a file must not silently leave it on the
    old schema — that produces `sqlite3.OperationalError: no such column:
    repo_id` the moment any repo_id-scoped query runs (regression: real
    project/global KB cache files from before this schema predate the
    `analyze`/`serve`/dashboard `doc` flow crashing with that error)."""

    def _make_legacy_kb(self, db_path: Path) -> None:
        con = sqlite3.connect(str(db_path))
        try:
            con.executescript(
                """
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE sources (origin TEXT PRIMARY KEY, path TEXT NOT NULL);
                CREATE TABLE modules (
                    name TEXT PRIMARY KEY, origin TEXT NOT NULL,
                    depends TEXT NOT NULL DEFAULT '[]',
                    application INTEGER NOT NULL DEFAULT 0, app TEXT
                );
                CREATE TABLE symbols (model TEXT, name TEXT, kind TEXT, origin TEXT, module TEXT);
                """
            )
            con.execute(
                "INSERT INTO meta (key, value) VALUES ('schema_version', '7')"
            )
            con.execute(
                "INSERT INTO modules (name, origin, depends) VALUES ('legacy_mod', 'odoo', '[]')"
            )
            con.commit()
        finally:
            con.close()

    def test_write_kb_heals_a_legacy_schema_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        self._make_legacy_kb(db_path)
        backend = SQLiteBackend(db_path)

        result = write_kb(backend, "a", "17.0", [_make_scan("module_a")], sources={"custom": "/repo-a"})
        assert result.ok, result.errors

        with KBReader(backend, repo_ids=["a"]) as kb:
            assert set(kb.get_modules()) == {"module_a"}

    def test_kbreader_heals_a_legacy_schema_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        self._make_legacy_kb(db_path)
        backend = SQLiteBackend(db_path)

        with KBReader(backend, repo_ids=["whatever"]) as kb:
            assert kb.get_modules() == {}


class TestAnalysisCacheMigration:
    """A KB file with the pre-content-fingerprint analysis_cache table (keyed
    only by kb_generated_at) must be dropped and recreated on the current
    schema — the cache is disposable, so no data migration is needed, only
    don't crash on the old column shape."""

    def _make_legacy_cache_kb(self, db_path: Path) -> None:
        con = sqlite3.connect(str(db_path))
        try:
            con.executescript(
                """
                CREATE TABLE analysis_cache (
                    repo_id TEXT NOT NULL,
                    module_name TEXT NOT NULL,
                    kb_generated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    cached_at TEXT NOT NULL,
                    PRIMARY KEY (repo_id, module_name, kb_generated_at)
                );
                """
            )
            con.execute(
                "INSERT INTO analysis_cache VALUES ('a', 'mod', 'gen-1', '{}', 'now')"
            )
            con.commit()
        finally:
            con.close()

    def test_stale_analysis_cache_dropped_and_recreated(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        self._make_legacy_cache_kb(db_path)
        backend = SQLiteBackend(db_path)

        con = backend.connect()  # triggers _reset_stale_analysis_cache
        cols = {row[1] for row in con.execute("PRAGMA table_info(analysis_cache)")}
        rows = con.execute("SELECT COUNT(*) FROM analysis_cache").fetchone()
        con.close()

        assert "content_fingerprint" in cols
        assert rows[0] == 0  # the stale row is gone, not migrated

    def test_write_cached_analysis_works_after_migration(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        self._make_legacy_cache_kb(db_path)
        backend = SQLiteBackend(db_path)

        write_cached_analysis(backend, "a", "mod", "fp-1", "gen-2", {"x": 1})
        with KBReader(backend, repo_ids=["a"]) as kb:
            assert kb.get_cached_analysis("mod", "fp-1") == {"x": 1}
