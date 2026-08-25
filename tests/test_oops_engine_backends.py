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
from pathlib import Path

import pytest
from oops_engine.backends.sqlite import SQLiteBackend
from oops_engine.store import KBReader, write_kb

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
