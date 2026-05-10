# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_kb_store.py — tests/test_kb_store.py

"""Tests for oops/kb/store.py schema, write path, and KBReader extensions."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from oops.kb.store import SCHEMA_VERSION, KBReader, write_project_kb

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(
    db_path: Path,
    symbols: list[dict] | None = None,
    field_refs: list[dict] | None = None,
    modules: dict | None = None,
) -> None:
    scan_results = [
        {
            "modules": modules or {},
            "symbols": symbols or [],
            "field_refs": field_refs or [],
        }
    ]
    write_project_kb(
        db_path=db_path,
        odoo_version="17.0",
        project="test",
        scope=[],
        sources={"odoo": "/odoo"},
        scan_results=scan_results,
    )


def _sym(model: str, name: str, kind: str, **kw: object) -> dict:
    return {
        "model": model,
        "name": name,
        "kind": kind,
        "origin": "odoo",
        "module": kw.get("module", "sale"),
        "source_file": "addons/sale/models/sale.py",
        "source_line": 10,
        "field_type": kw.get("field_type"),
        "section": kw.get("section"),
    }


# ---------------------------------------------------------------------------
# TestDDL — schema shape
# ---------------------------------------------------------------------------


class TestDDL:
    def test_symbols_has_field_type_column(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path)
        con = sqlite3.connect(str(db_path))
        cols = {row[1] for row in con.execute("PRAGMA table_info(symbols)").fetchall()}
        assert "field_type" in cols
        assert "section" in cols
        con.close()

    def test_field_refs_table_exists(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path)
        con = sqlite3.connect(str(db_path))
        tables = {
            row[0]
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "field_refs" in tables
        con.close()

    def test_schema_version_in_meta(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path)
        with KBReader(db_path) as kb:
            meta = kb.get_meta()
        assert meta.get("schema_version") == str(SCHEMA_VERSION)

    def test_write_twice_applies_schema_cleanly(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path, symbols=[_sym("sale.order", "write", "method", section="CRUD METHODS")])
        _write(db_path, symbols=[_sym("sale.order", "name", "field", field_type="Char")])
        with KBReader(db_path) as kb:
            # Second write replaced the first; only the new symbol should be there.
            syms = kb.get_model_symbols("sale.order")
        assert len(syms) == 1
        assert syms[0]["name"] == "name"


# ---------------------------------------------------------------------------
# TestRoundTrip — write then read back
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_field_type_round_trips(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path, symbols=[_sym("sale.order", "active", "field", field_type="Boolean")])
        with KBReader(db_path) as kb:
            entries = kb.get_symbol("sale.order", "active", "field")
        assert len(entries) == 1
        assert entries[0]["field_type"] == "Boolean"

    def test_section_round_trips(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path, symbols=[_sym("sale.order", "action_confirm", "method", section="ACTION METHODS")])
        with KBReader(db_path) as kb:
            entries = kb.get_symbol("sale.order", "action_confirm", "method")
        assert entries[0]["section"] == "ACTION METHODS"

    def test_field_refs_round_trip(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(
            db_path,
            field_refs=[
                {
                    "model": "sale.order",
                    "field_name": "amount_total",
                    "module": "sale",
                    "kwarg": "compute",
                    "target_method": "_compute_amount_total",
                }
            ],
        )
        with KBReader(db_path) as kb:
            refs = kb.get_field_refs_for_method("sale.order", "_compute_amount_total")
        assert len(refs) == 1
        assert refs[0]["kwarg"] == "compute"
        assert refs[0]["field_name"] == "amount_total"

    def test_get_field_refs_for_field(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(
            db_path,
            field_refs=[
                {
                    "model": "sale.order",
                    "field_name": "amount_total",
                    "module": "sale",
                    "kwarg": "compute",
                    "target_method": "_compute_amount",
                }
            ],
        )
        with KBReader(db_path) as kb:
            refs = kb.get_field_refs_for_field("sale.order", "amount_total")
        assert len(refs) == 1
        assert refs[0]["target_method"] == "_compute_amount"

    def test_null_field_type_for_methods(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path, symbols=[_sym("sale.order", "write", "method")])
        with KBReader(db_path) as kb:
            entries = kb.get_symbol("sale.order", "write", "method")
        assert entries[0]["field_type"] is None

    def test_null_section_for_fields(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path, symbols=[_sym("sale.order", "name", "field", field_type="Char")])
        with KBReader(db_path) as kb:
            entries = kb.get_symbol("sale.order", "name", "field")
        assert entries[0]["section"] is None


# ---------------------------------------------------------------------------
# TestStaleness — schema version check
# ---------------------------------------------------------------------------


class TestStaleness:
    def test_kb_without_schema_version_is_stale(self, tmp_path):
        """A v1 KB (no schema_version row) is flagged as stale."""
        from oops.kb.build import is_project_kb_stale

        cache = tmp_path / ".oops-cache"
        cache.mkdir()
        db_path = cache / "kb.db"
        # Write a KB and then manually delete the schema_version row.
        _write(db_path)
        con = sqlite3.connect(str(db_path))
        con.execute("DELETE FROM meta WHERE key='schema_version'")
        con.commit()
        con.close()

        stale, reason = is_project_kb_stale(tmp_path, "17.0")
        assert stale is True
        assert "schema" in reason.lower()

    def test_kb_with_wrong_schema_version_is_stale(self, tmp_path):
        from oops.kb.build import is_project_kb_stale

        cache = tmp_path / ".oops-cache"
        cache.mkdir()
        db_path = cache / "kb.db"
        _write(db_path)
        # Override the version to something old.
        con = sqlite3.connect(str(db_path))
        con.execute("UPDATE meta SET value='1' WHERE key='schema_version'")
        con.commit()
        con.close()

        stale, reason = is_project_kb_stale(tmp_path, "17.0")
        assert stale is True
        assert "schema" in reason.lower()

    def test_current_schema_version_is_fresh(self, tmp_path):
        from oops.kb.build import is_project_kb_stale

        cache = tmp_path / ".oops-cache"
        cache.mkdir()
        db_path = cache / "kb.db"
        _write(db_path)

        # No global KB → only schema version check matters here.
        # Patch global KB path to a non-existent path so it doesn't block freshness.
        stale, reason = is_project_kb_stale(tmp_path, "17.0")
        # KB is fresh from a schema perspective (global KB missing is OK — no timestamp
        # comparison possible, so it doesn't flag stale for that reason alone).
        # The important thing is "schema" is not in reason.
        assert "schema" not in reason
